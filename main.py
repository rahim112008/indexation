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
    .alert-card { padding: 10px; background-color: #331a00; border-left: 5px solid #ff9900; color: #ffcc00; margin-bottom: 5px; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ultra_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE HYBRIDE & CALCULS ---
def estimer_age_dents(dentition):
    mapping = {
        "Dents de lait": "6-12 mois",
        "2 Dents": "14-22 mois",
        "4 Dents": "22-28 mois",
        "6 Dents": "28-36 mois",
        "8 Dents (Pleine)": "+36 mois"
    }
    return mapping.get(dentition, "Inconnu")

def calculer_metrics(row, mode="Viande"):
    # GMQ 30-70 : La référence absolue
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if (row['p70'] > 0 and row['p30'] > 0) else 0
    # Rendement estimé
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
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, dentition TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                  l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("💎 Selector Ultra")
obj_selection = st.sidebar.selectbox("🎯 Objectif de Sélection", ["Viande", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "✍️ Saisie Manuelle", "📈 Stats Croissance", "📥 Import/Export"])

conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x, obj_selection)), axis=1)

# --- PAGE : DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("📊 État du Troupeau (1000 têtes)")
    if not df.empty:
        today = datetime.now().date()
        st.subheader("🔔 Alertes de Pesées")
        for _, r in df.iterrows():
            try:
                d_n = datetime.strptime(r['date_naiss'], '%Y-%m-%d').date()
                if today >= (d_n + timedelta(days=10)) and r['p10'] <= 0:
                    st.markdown(f'<div class="alert-card">⚖️ J10 : {r["id"]}</div>', unsafe_allow_html=True)
                if today >= (d_n + timedelta(days=30)) and r['p30'] <= 0:
                    st.markdown(f'<div class="alert-card">⚖️ J30 : {r["id"]}</div>', unsafe_allow_html=True)
                if today >= (d_n + timedelta(days=70)) and r['p70'] <= 0:
                    st.markdown(f'<div class="alert-card">⚠️ J70 : {r["id"]}</div>', unsafe_allow_html=True)
            except: pass

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Effectif Total", len(df))
        c2.metric("GMQ Moyen", f"{df['GMQ'].mean().round(1)} g/j")
        c3.metric("Rendement Max", f"{df['Rendement'].max()}%")
        c4.metric("Élite Score", df['Index'].max())
        
        st.dataframe(df[['id', 'race', 'p10', 'p30', 'p70', 'GMQ', 'Index']], use_container_width=True)

# --- PAGE : SAISIE MANUELLE ---
elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie de Précision")
    with st.form("form_complet"):
        c1, c2 = st.columns(2)
        with c1:
            m_id = st.text_input("ID Animal")
            m_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            methode_age = st.radio("Méthode âge :", ["Exact (Date)", "Dents"])
            if methode_age == "Exact (Date)":
                m_date = st.date_input("Date Naissance")
                m_dents = "Calendrier"
            else:
                m_dents = st.selectbox("Dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
                m_date = f"Est. {estimer_age_dents(m_dents)}"
            
            st.divider()
            st.subheader("⚖️ Pesées (10 - 30 - 70 jours)")
            p10 = st.number_input("Poids J10 (kg)", 0.0)
            p30 = st.number_input("Poids J30 (kg)", 0.0)
            p70 = st.number_input("Poids J70 (kg)", 0.0)
        with c2:
            st.subheader("📏 Mensurations")
            hg = st.number_input("Hauteur Garrot (cm)", 0.0)
            pt = st.number_input("Périmètre Thoracique (cm)", 0.0)
            lp = st.number_input("Largeur Poitrine (cm)", 0.0)
            cc = st.number_input("Canon (cm)", 0.0)
        
        if st.form_submit_button("💾 Enregistrer"):
            if m_id:
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, m_race, str(m_date), obj_selection, m_dents))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, 80.0, pt, lp, cc))
                conn.commit()
                st.success(f"Enregistré : {m_id}")
                st.rerun()

# --- PAGE : STATISTIQUES ---
elif menu == "📈 Stats Croissance":
    st.title("📈 Évolution de la Croissance")
    if not df.empty:
        fig_gmq = px.histogram(df, x="GMQ", nbins=20, title="Distribution du GMQ (Vitesse de croissance)")
        st.plotly_chart(fig_gmq, use_container_width=True)
        
        fig_scatter = px.scatter(df, x="p30", y="p70", color="race", size="Index", title="Corrélation Poids J30 vs J70")
        st.plotly_chart(fig_scatter, use_container_width=True)

# --- PAGE : IMPORT / EXPORT ---
elif menu == "📥 Import/Export":
    st.title("📥 Gestion Excel")
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False)
    st.download_button("📥 Télécharger la base complète", data=towrite, file_name="troupeau_complet.xlsx")
