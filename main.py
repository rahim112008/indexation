import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
from datetime import datetime, timedelta
from contextlib import contextmanager
import io
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Master", layout="wide", page_icon="🐏")

# On utilise un nouveau nom de fichier pour éviter les erreurs de colonnes des versions précédentes
DB_NAME = "expert_ovin_final_v4.db"

# --- 2. GESTION BASE DE DONNÉES ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        # Table Béliers : 6 colonnes
        c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                    (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, 
                     objectif TEXT, dentition TEXT, statut TEXT DEFAULT '')''')
        
        # Table Mesures : 10 colonnes
        c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                    (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                     l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL, 
                     date_mesure TEXT)''')
init_db()

# --- 3. LOGIQUE MÉTIER ---
def calculer_metrics(row):
    try:
        p70 = float(row.get('p70', 0) or 0)
        p30 = float(row.get('p30', 0) or 0)
        if p70 <= 0 or p30 <= 0: return 0.0, 0.0, 0.0
        
        gmq = ((p70 - p30) / 40) * 1000
        # Index combinant Croissance et Robustesse (Canon)
        # On donne un fort coefficient au canon (x5) car c'est un critère de race
        index = (gmq * 0.20) + (p70 * 0.40) + (float(row.get('c_canon', 0)) * 5.0)
        rendement = 52.4 + (0.35 * float(row.get('l_poitrine', 24))) - (0.08 * float(row.get('h_garrot', 70)))
        return round(gmq, 1), round(rendement, 1), round(index, 2)
    except: return 0.0, 0.0, 0.0

# --- 4. NAVIGATION SIDEBAR ---
st.sidebar.title("💎 Selector Master")
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie", "📥 Import/Export"])

# Chargement global des données
with get_db_connection() as conn:
    query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, m.p_thoracique, m.l_poitrine, m.c_canon 
               FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal"""
    df = pd.read_sql(query, conn)

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
    # Marquage ELITE ⭐ (Top 15% du troupeau)
    s_p70 = df['p70'].quantile(0.85) if len(df) > 5 else 999
    s_can = df['c_canon'].quantile(0.85) if len(df) > 5 else 999
    df['statut'] = np.where((df['p70'] >= s_p70) & (df['c_canon'] >= s_can), "⭐ ELITE", "")

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("🏆 Classement du Troupeau")
    if df.empty:
        st.info("Aucune donnée. Commencez par saisir un animal ou importer un Excel.")
    else:
        st.dataframe(df.sort_values('Index', ascending=False), use_container_width=True)

elif menu == "📸 Scanner IA":
    st.title("📸 Scanner Morphologique")
    st.write("Alignez l'animal de profil.")
    img = st.camera_input("Prendre une photo")
    if img:
        # Simulation des mesures extraites par l'IA
        st.session_state['scan_data'] = {'h_garrot': 74.0, 'c_canon': 10.2, 'p_thoracique': 88.5, 'l_poitrine': 25.0, 'l_corps': 81.0}
        st.success("✅ Analyse terminée. Les mesures sont prêtes dans l'onglet Saisie.")

elif menu == "📥 Import/Export":
    st.title("📥 Échange de Données")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Partage")
        # Création du modèle vide
        tmp_cols = ['id', 'race', 'date_naiss', 'p10', 'p30', 'p70', 'h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'c_canon']
        buffer_mod = io.BytesIO()
        pd.DataFrame(columns=tmp_cols).to_excel(buffer_mod, index=False)
        st.download_button("📄 Télécharger le Modèle Vide", data=buffer_mod.getvalue(), file_name="MODELE_COLLECTE.xlsx")
        
        if not df.empty:
            buffer_exp = io.BytesIO()
            df.to_excel(buffer_exp, index=False)
            st.download_button("📥 Exporter mes données", data=buffer_exp.getvalue(), file_name="mon_troupeau.xlsx")

    with col2:
        st.subheader("📥 Importer")
        up = st.file_uploader("Charger un fichier Excel", type=['xlsx'])
        if up:
            new_df = pd.read_excel(up)
            if st.button(f"Importer {len(new_df)} lignes"):
                with get_db_connection() as conn:
                    for _, r in new_df.iterrows():
                        aid = str(r['id'])
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race, date_naiss) VALUES (?,?,?)", (aid, str(r.get('race', 'Rembi')), str(r.get('date_naiss', ''))))
                        conn.execute("INSERT OR REPLACE INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon) VALUES (?,?,?,?,?,?)", (aid, r.get('p10',0), r.get('p30',0), r.get('p70',0), r.get('h_garrot',0), r.get('c_canon',0)))
                st.success("Importation réussie !"); time.sleep(1); st.rerun()

elif menu == "✍️ Saisie":
    st.title("✍️ Fiche Individuelle")
    scan = st.session_state.get('scan_data', {})
    with st.form("saisie_directe"):
        c1, c2 = st.columns(2)
        with c1:
            id_a = st.text_input("ID Boucle *")
            race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            p70 = st.number_input("Poids J70 (kg) *", 0.0)
        with c2:
            cc = st.number_input("Tour de Canon (cm)", value=scan.get('c_canon', 0.0))
            hg = st.number_input("Hauteur Garrot (cm)", value=scan.get('h_garrot', 0.0))
        
        if st.form_submit_button("💾 Enregistrer l'animal"):
            if id_a and p70 > 0:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race, date_naiss, objectif, dentition) VALUES (?,?,'','Sélection','2 Dents')", (id_a, race))
                    conn.execute("INSERT INTO mesures (id_animal, p70, c_canon, h_garrot, date_mesure) VALUES (?,?,?,?,?)", (id_a, p70, cc, hg, datetime.now().strftime("%Y-%m-%d")))
                st.success("Données enregistrées !"); time.sleep(1); st.rerun()
            else:
                st.error("L'ID et le Poids J70 sont obligatoires.")

elif menu == "📈 Analyse":
    st.title("🔬 Analyse des Performances")
    if not df.empty:
        st.plotly_chart(px.scatter(df, x="c_canon", y="p70", color="statut", size="Index", hover_name="id", title="Performance par Circonférence de Canon"), use_container_width=True)
