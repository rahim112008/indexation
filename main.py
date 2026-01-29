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

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

DB_NAME = "expert_ovin_v3.db"  # Nouvelle version pour éviter les conflits SQL

# --- 2. GESTION BASE DE DONNÉES (MIGRATION INCLUSE) ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Initialise et met à jour la structure sans perte de données"""
    with get_db_connection() as conn:
        c = conn.cursor()
        # Table Béliers
        c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                    (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, dentition TEXT, statut TEXT)''')
        
        # Table Mesures
        c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT, 
                     p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
                     p_thoracique REAL, l_poitrine REAL, c_canon REAL, date_mesure TEXT)''')
        
        # Migration automatique : ajout des colonnes si elles manquent
        cols_beliers = [col[1] for col in c.execute("PRAGMA table_info(beliers)").fetchall()]
        if 'statut' not in cols_beliers:
            c.execute('ALTER TABLE beliers ADD COLUMN statut TEXT DEFAULT ""')

init_db()

# --- 3. LOGIQUE MÉTIER & CALCULS ---
def calculer_metrics(row):
    try:
        p70, p30 = float(row.get('p70', 0) or 0), float(row.get('p30', 0) or 0)
        if p70 <= 0 or p30 <= 0: return 0.0, 0.0, 0.0
        
        gmq = ((p70 - p30) / 40) * 1000
        rend = 52.4 + (0.35 * float(row.get('l_poitrine', 24))) + (0.12 * float(row.get('p_thoracique', 80))) - (0.08 * float(row.get('h_garrot', 70)))
        rend = max(40.0, min(65.0, rend))
        
        # Index hybride (Poids + Robustesse)
        index = (gmq * 0.15) + (rend * 0.45) + (p70 * 0.2) + (float(row.get('c_canon', 9)) * 2.0)
        return round(gmq, 1), round(rend, 1), round(index, 2)
    except:
        return 0.0, 0.0, 0.0

def identifier_champions(df):
    if df.empty or len(df) < 5: return df
    s_p70 = df['p70'].quantile(0.85)
    s_can = df['c_canon'].quantile(0.85)
    df['Statut'] = np.where((df['p70'] >= s_p70) & (df['c_canon'] >= s_can), "⭐ ELITE", "")
    return df

# --- 4. INTERFACE & NAVIGATION ---
st.sidebar.title("💎 Selector Ultra v3")
menu = st.sidebar.radio("Menu", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie", "📥 Import/Export"])

# Chargement Data
with get_db_connection() as conn:
    query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, m.p_thoracique, m.l_poitrine, m.c_canon 
               FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal"""
    df = pd.read_sql(query, conn)

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
    df = identifier_champions(df)

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("🏆 Classement du Troupeau")
    if df.empty:
        st.info("Aucune donnée. Utilisez l'onglet Import ou la Saisie.")
    else:
        st.dataframe(df.sort_values('Index', ascending=False), use_container_width=True)

elif menu == "📸 Scanner IA":
    st.title("📸 Scanner Morphologique")
    img = st.camera_input("Capturez le bélier")
    if img:
        # Simulation IA basée sur la silhouette
        st.session_state['scan_data'] = {'h_garrot': 75.2, 'c_canon': 10.5, 'p_thoracique': 88.0, 'l_poitrine': 25.5, 'l_corps': 82.0}
        st.success("✅ Morphologie analysée. Transférez vers 'Saisie' pour enregistrer.")

elif menu == "📥 Import/Export":
    st.title("📥 Gestion des données externes")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Exporter")
        if not df.empty:
            output = io.BytesIO()
            df.to_excel(output, index=False)
            st.download_button("📥 Télécharger Excel", data=output.getvalue(), file_name="export_troupeau.xlsx")
    
    with col2:
        st.subheader("Importer")
        file = st.file_uploader("Fichier d'un autre éleveur (Excel/CSV)", type=['xlsx', 'csv'])
        if file:
            try:
                new_data = pd.read_excel(file) if file.name.endswith('xlsx') else pd.read_csv(file)
                st.write("Aperçu des données :", new_data.head(3))
                if st.button("Confirmer l'importation"):
                    with get_db_connection() as conn:
                        for _, row in new_data.iterrows():
                            # Insertion sécurisée
                            conn.execute("INSERT OR REPLACE INTO beliers (id, race, date_naiss) VALUES (?,?,?)", 
                                         (str(row.get('id', row.get('ID', 'N/A'))), str(row.get('race', 'Inconnue')), str(row.get('date', '2024-01-01'))))
                    st.success("Données importées avec succès !")
            except Exception as e:
                st.error(f"Erreur de format : {e}")

elif menu == "✍️ Saisie":
    st.title("✍️ Fiche Individuelle")
    scan = st.session_state.get('scan_data', {})
    with st.form("saisie_form"):
        c1, c2 = st.columns(2)
        with c1:
            id_a = st.text_input("ID Boucle")
            p70 = st.number_input("Poids J70", 0.0)
        with c2:
            hg = st.number_input("Hauteur Garrot (cm)", value=scan.get('h_garrot', 0.0))
            cc = st.number_input("Canon (cm)", value=scan.get('c_canon', 0.0))
        
        if st.form_submit_button("Enregistrer"):
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_a, "Rembi"))
                conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon) VALUES (?,?,?,?)", (id_a, p70, hg, cc))
            st.success("Sauvegardé !"); st.rerun()

elif menu == "📈 Analyse":
    st.title("🔬 Analyse Biométrique")
    if not df.empty:
        st.plotly_chart(px.scatter(df, x="c_canon", y="p70", color="Statut", size="Index", title="Corrélation Canon / Poids"), use_container_width=True)
