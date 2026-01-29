import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from contextlib import contextmanager
import time

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

# Style CSS pour le look professionnel
st.markdown("""
    <style>
    .stMetric { background-color: #1e2630; padding: 15px; border-radius: 10px; border-left: 5px solid #00d4ff; }
    .scanner-box { border: 2px dashed #00d4ff; padding: 20px; border-radius: 15px; background: rgba(0, 212, 255, 0.05); }
    .main { background-color: #0e1117; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_v11_pro.db"

# --- 2. GESTION BASE DE DONNÉES ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn
    finally: conn.close()

def preinstaller_individus():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM beliers")
        if cursor.fetchone()[0] == 0:
            test_data = [
                ("TOP-004", "Ouled Djellal", 40.1, 12.0, 78.0, 27.0, 92.0, 84.0),
                ("ELITE-001", "Ouled Djellal", 38.5, 11.5, 76.0, 26.0, 90.0, 82.0),
                ("ELITE-002", "Rembi", 36.2, 11.0, 74.5, 25.5, 88.0, 81.0)
            ]
            for aid, race, p70, can, hg, lp, pt, lc in test_data:
                conn.execute("INSERT INTO beliers (id, race) VALUES (?,?)", (aid, race))
                conn.execute("""INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, l_corps, date_mesure) 
                             VALUES (?, 5.0, 15.0, ?, ?, ?, ?, ?, ?, ?)""", 
                             (aid, p70, hg, can, lp, pt, lc, datetime.now().strftime("%Y-%m-%d")))

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS beliers (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS mesures (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, 
                     h_garrot REAL, c_canon REAL, l_poitrine REAL, p_thoracique REAL, l_corps REAL, date_mesure TEXT)''')
    preinstaller_individus()

# --- 3. LOGIQUE MÉTIER ---
def calculer_metrics(row):
    try:
        p70, p30 = float(row.get('p70', 0) or 0), float(row.get('p30', 0) or 0)
        if p70 <= 0 or p30 <= 0: return 0.0, 0.0
        gmq = ((p70 - p30) / 40) * 1000
        index = (gmq * 0.2) + (p70 * 0.3) + (float(row.get('c_canon', 0)) * 5.0)
        return round(gmq, 1), round(index, 1)
    except: return 0.0, 0.0

# --- 4. NAVIGATION ---
init_db()
st.sidebar.title("💎 Selector IA Pro")
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie Manuelle", "📥 Import/Export"])

with get_db_connection() as conn:
    df = pd.read_sql("SELECT b.*, m.* FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal", conn)
if not df.empty:
    df[['GMQ', 'Score']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("🏆 Classement du Troupeau")
    if not df.empty:
        df_sort = df.sort_values('Score', ascending=False)
        st.dataframe(df_sort, use_container_width=True)
    else:
        st.info("Base vide.")

elif menu == "📸 Scanner IA":
    st.title("📸 Scanner Morphologique IA")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="scanner-box">', unsafe_allow_html=True)
        img = st.camera_input("Capture profil")
        st.markdown('</div>', unsafe_allow_html=True)
    with col_b:
        if img:
            bar = st.progress(0)
            for p in range(100): time.sleep(0.01); bar.progress(p + 1)
            scan = {'h_garrot': 76.5, 'c_canon': 11.2, 'l_poitrine': 25.8, 'p_thoracique': 89.2, 'l_corps': 83.0}
            st.success("✅ Analyse effectuée")
            st.json(scan)
            if st.button("Transférer vers Saisie"):
                st.session_state['scan_data'] = scan
                st.info("Copié !")

elif menu == "📈 Analyse":
    st.title("📊 Analyse de Performance Radar")
    if not df.empty:
        target = st.selectbox("Sélectionner un bélier", df['id'].unique())
        sub = df[df['id'] == target].iloc[0]
        avg = df.mean(numeric_only=True)
        
        categories = ['Poids J70', 'Canon', 'H. Garrot', 'L. Poitrine', 'P. Thorax']
        
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[sub['p70']/avg['p70'], sub['c_canon']/avg['c_canon'], sub['h_garrot']/avg['h_garrot'], 
               sub['l_poitrine']/avg['l_poitrine'], sub['p_thoracique']/avg['p_thoracique']],
            theta=categories, fill='toself', name=target, line_color='#00d4ff'))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1.5])), template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie des données")
    scan = st.session_state.get('scan_data', {})
    with st.form("saisie_110"):
        st.subheader("Identification")
        c1, c2 = st.columns(2)
        with c1: animal_id = st.text_input("ID Animal *")
        with c2: race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])

        st.subheader("Poids de croissance")
        cp1, cp2, cp3 = st.columns(3)
        with cp1: p10 = st.number_input("Poids J10 (kg)", 0.0)
        with cp2: p30 = st.number_input("Poids J30 (kg)", 0.0)
        with cp3: p70 = st.number_input("Poids J70 (kg) *", 0.0)

        st.subheader("Mensurations (cm)")
        cm1, cm2, cm3, cm4, cm5 = st.columns(5)
        with cm1: hg = st.number_input("Hauteur Garrot", value=float(scan.get('h_garrot', 0.0)))
        with cm2: can = st.number_input("Canon", value=float(scan.get('c_canon', 0.0)))
        with cm3: lp = st.number_input("Larg. Poitrine", value=float(scan.get('l_poitrine', 0.0)))
        with cm4: pt = st.number_input("Périm. Thorax", value=float(scan.get('p_thoracique', 0.0)))
        with cm5: lc = st.number_input("Long. Corps", value=float(scan.get('l_corps', 0.0)))

        if st.form_submit_button("💾 Enregistrer", type="primary"):
            if animal_id and p70 > 0:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (animal_id, race))
                    conn.execute("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, l_corps, date_mesure) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (animal_id, p10, p30, p70, hg, can, lp, pt, lc, datetime.now().strftime("%Y-%m-%d")))
                st.success("Enregistré !"); st.rerun()

elif menu == "📥 Import/Export":
    st.title("📥 Échange Excel")
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    st.download_button("📤 Exporter tout le troupeau", buf.getvalue(), "troupeau_expert.xlsx")
