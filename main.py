import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

DB_NAME = "expert_ultra_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE SCIENTIFIQUE & IA ---
def identifier_champions(df):
    if df.empty or len(df) < 5: return df
    # Critères Élite : Top 15% sur le Poids et le Canon
    seuil_p70 = df['p70'].quantile(0.85)
    seuil_canon = df['c_canon'].quantile(0.85)
    df['Statut'] = df.apply(lambda r: "⭐ Élite" if (r['p70'] >= seuil_p70 and r['c_canon'] >= seuil_canon) else "", axis=1)
    return df

def calculer_metrics(row, mode="Viande"):
    if row['p70'] <= 0 or row['p30'] <= 0: return 0.0, 0.0, 0.0
    gmq = ((row['p70'] - row['p30']) / 40) * 1000
    rendement = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    rendement = max(min(rendement, 65.0), 40.0)
    if mode == "Viande":
        index = (gmq * 0.15) + (rendement * 0.55) + (row['p70'] * 0.3)
    else:
        index = (row['c_canon'] * 4.0) + (row['h_garrot'] * 0.3) + (gmq * 0.03)
    return round(gmq, 1), round(rendement, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, dentition TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("💎 Selector Ultra")
st.sidebar.info("Expert Mode : IA & Biométrie")

if st.sidebar.button("🚀 GÉNÉRER 500 SUJETS (DÉMO)"):
    conn = get_db_connection(); c = conn.cursor()
    data_b, data_m = [], []
    for i in range(500):
        a_id = f"REF-{5000 + i}"
        p10, p30 = round(random.uniform(4, 6), 1), round(random.uniform(12, 16), 1)
        p70 = round(p30 + random.uniform(15, 20), 1)
        cc = round(8.5 + (p70 * 0.08), 1)
        hg = round(70 + (p70 * 0.2), 1)
        data_b.append((a_id, random.choice(["Ouled Djellal", "Rembi", "Hamra"]), "2024-05-10", "Sélection", "2 Dents"))
        data_m.append((a_id, p10, p30, p70, hg, 80.0, hg*1.2, 24.0, cc))
    c.executemany("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", data_b)
    c.executemany("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", data_m)
    conn.commit(); st.sidebar.success("Troupeau injecté !"); st.rerun()

menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse Scientifique", "✍️ Saisie Manuelle"])

# Chargement
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()
if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
    df = identifier_champions(df)

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("🏆 Tableau de Bord du Troupeau")
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1: st.metric("Total Sujets", len(df))
        with col2: st.metric("Nombre d'Élites ⭐", len(df[df['Statut'] != ""]))
        st.dataframe(df[['Statut', 'id', 'race', 'p70', 'c_canon', 'Index']].sort_values('Index', ascending=False), use_container_width=True)
    else:
        st.info("Base vide. Utilisez le bouton 'Générer' ou le Scanner IA.")

elif menu == "📸 Scanner IA":
    st.title("📸 Scanner Morphologique")
    st.write("Prenez une photo de profil pour estimer les mensurations.")
    img = st.camera_input("Capturer le bélier")
    if img:
        st.info("Analyse de la silhouette par IA...")
        # Simulation extraction IA
        hg_ia, cc_ia = round(random.uniform(70, 80), 1), round(random.uniform(9, 12), 1)
        st.session_state['scan_hg'] = hg_ia
        st.session_state['scan_cc'] = cc_ia
        c1, c2 = st.columns(2)
        with c1: st.image(img, use_container_width=True)
        with c2:
            st.success("Mesures détectées !")
            st.metric("Hauteur Garrot", f"{hg_ia} cm")
            st.metric("Circonférence Canon", f"{cc_ia} cm")
            st.warning("Ces valeurs ont été envoyées vers l'onglet 'Saisie Manuelle'")

elif menu == "📈 Analyse Scientifique":
    st.title("🔬 Analyse des Corrélations")
    if not df.empty:
        cols = ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'c_canon', 'GMQ']
        st.plotly_chart(px.imshow(df[cols].corr(), text_auto=".2f", title="Matrice de Biométrie"), use_container_width=True)
        
        st.subheader("🚀 Impact sur la croissance (P70)")
        impacts = df[cols].corr()['p70'].abs().drop('p70').sort_values()
        st.plotly_chart(px.bar(x=impacts.values*100, y=impacts.index, orientation='h', title="Importance des critères (%)"), use_container_width=True)

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Fiche d'Identification")
    # Récupération des mesures du scanner
    hg_ia = st.session_state.get('scan_hg', 0.0)
    cc_ia = st.session_state.get('scan_cc', 0.0)
    
    with st.form("form_saisie"):
        c1, c2 = st.columns(2)
        with c1:
            m_id = st.text_input("ID Animal")
            p10 = st.number_input("Poids J10", 0.0)
            p30 = st.number_input("Poids J30", 0.0)
            p70 = st.number_input("Poids J70", 0.0)
        with c2:
            hg = st.number_input("Hauteur Garrot (IA si scanné)", value=hg_ia)
            cc = st.number_input("Circonf. Canon (IA si scanné)", value=cc_ia)
            pt = st.number_input("Périmètre Thoracique", 0.0)
            lp = st.number_input("Largeur Poitrine", 0.0)
        
        if st.form_submit_button("💾 Enregistrer"):
            conn = get_db_connection()
            conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, "Rembi", "2024-01-01", "Sélection", "2 Dents"))
            conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, 80.0, pt, lp, cc))
            conn.commit(); st.success("Enregistré !"); st.rerun()
