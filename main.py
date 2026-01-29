import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .stMetric { background-color: #111111; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { color: #00ff00 !important; }
    .alert-card { padding: 10px; background-color: #331a00; border-left: 5px solid #ff9900; color: #ffcc00; margin-bottom: 5px; border-radius: 5px; }
    .certificat-gold { border: 5px double #d4af37; background-color: #fffdf5; padding: 30px; text-align: center; color: #000; border-radius: 20px; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ultra_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. CALCULS ---
def calculer_metrics(row, mode="Viande"):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if (row['p70'] and row['p30']) else 0
    rendement = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    if mode == "Viande":
        index = (gmq * 0.15) + (rendement * 0.55) + (row['p70'] * 0.3)
    else:
        index = (row['c_canon'] * 0.45) + (row['h_garrot'] * 0.25) + (gmq * 0.3)
    return round(gmq, 1), round(rendement, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                  l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("💎 Selector Ultra")
obj_selection = st.sidebar.selectbox("🎯 Objectif de Sélection", ["Viande", "Rusticité"])
menu = st.sidebar.radio("Navigation", 
    ["🏠 Dashboard & Alertes", "📸 Scanner IA (Masse)", "✍️ Saisie Manuelle", "🔬 Statistiques", "🏆 Duel & Élite", "📥 Import / Export"])

conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x, obj_selection)), axis=1)

# --- PAGES ---
if menu == "🏠 Dashboard & Alertes":
    st.title("📊 État de la Reproductrice")
    if not df.empty:
        # Alertes Pesées
        today = datetime.now().date()
        st.subheader("🔔 Alertes de Pesées")
        for _, r in df.iterrows():
            d_n = datetime.strptime(r['date_naiss'], '%Y-%m-%d').date()
            if today >= d_n + timedelta(days=70) and r['p70'] <= 0:
                st.markdown(f'<div class="alert-card">⚖️ Pesée J70 REQUISE : {r["id"]}</div>', unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Individus", len(df))
        c2.metric("GMQ Moyen", f"{df['GMQ'].mean().round(1)} g/j")
        c3.metric("Rendement Max", f"{df['Rendement'].max()}%")
        st.dataframe(df[['id', 'race', 'Index', 'GMQ', 'Rendement']], use_container_width=True)
    else:
        st.info("Aucune donnée. Commencez par la saisie.")

elif menu == "📸 Scanner IA (Masse)":
    st.title("📸 Scanner Intelligent")
    
    cam = st.camera_input("Scanner")
    if cam:
        id_auto = f"SCAN-{np.random.randint(1000, 9999)}"
        with st.form("ia_val"):
            st.success(f"ID détecté : {id_auto}")
            id_f = st.text_input("Confirmer ID", id_auto)
            p70 = st.number_input("Poids J70", value=35.0)
            if st.form_submit_button("Enregistrer"):
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_f, "Rembi", str(datetime.now().date()), obj_selection))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (id_f, 0, 15.0, p70, 72.0, 80.0, 95.0, 22.0, 9.5))
                conn.commit()
                st.rerun()

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie Manuelle Complète")
    with st.form("form_manuel"):
        col1, col2 = st.columns(2)
        with col1:
            m_id = st.text_input("ID Animal (Boucle)")
            m_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            m_date = st.date_input("Date de Naissance")
            m_p30 = st.number_input("Poids J30 (kg)", 0.0)
            m_p70 = st.number_input("Poids J70 (kg)", 0.0)
        with col2:
            m_hg = st.number_input("Hauteur Garrot (cm)", 0.0)
            m_lc = st.number_input("Longueur Corps (cm)", 0.0)
            m_pt = st.number_input("Périmètre Thoracique (cm)", 0.0)
            m_lp = st.number_input("Largeur Poitrine (cm)", 0.0)
            m_cc = st.number_input("Circonférence Canon (cm)", 0.0)
        
        if st.form_submit_button("💾 Enregistrer dans la base"):
            if m_id:
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (m_id, m_race, str(m_date), obj_selection))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, 0, m_p30, m_p70, m_hg, m_lc, m_pt, m_lp, m_cc))
                conn.commit()
                st.success(f"Animal {m_id} enregistré avec succès !")
            else:
                st.error("L'ID est obligatoire.")

elif menu == "🔬 Statistiques":
    st.title("🔬 Corrélations Morphologiques")
    if not df.empty:
        corr = df[['h_garrot', 'l_corps', 'p_thoracique', 'GMQ', 'Rendement']].corr()
        fig = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r')
        st.plotly_chart(fig, use_container_width=True)
        

elif menu == "🏆 Duel & Élite":
    st.title("🏆 Sélection de l'Élite")
    if len(df) >= 2:
        id1 = st.selectbox("Bélier A", df['id'].unique(), index=0)
        id2 = st.selectbox("Bélier B", df['id'].unique(), index=1)
        b1, b2 = df[df['id']==id1].iloc[0], df[df['id']==id2].iloc[0]
        
        fig = go.Figure()
        metrics = ['h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'c_canon']
        fig.add_trace(go.Scatterpolar(r=[b1[m] for m in metrics], theta=metrics, fill='toself', name=id1))
        fig.add_trace(go.Scatterpolar(r=[b2[m] for m in metrics], theta=metrics, fill='toself', name=id2))
        st.plotly_chart(fig)
        

elif menu == "📥 Import / Export":
    st.title("📥 Gestion Excel")
    if not df.empty:
        towrite = io.BytesIO()
        df.to_excel(towrite, index=False)
        st.download_button("📥 Télécharger la base Excel", data=towrite, file_name="troupeau.xlsx")
