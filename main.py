import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION & STYLE ---
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

# --- 2. FONCTIONS SCIENTIFIQUES & DÉMO ---
def calculer_metrics(row, mode="Viande"):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if (row['p70'] > 0 and row['p30'] > 0) else 0
    rendement = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    if mode == "Viande":
        index = (gmq * 0.15) + (rendement * 0.55) + (row['p70'] * 0.3)
    else:
        index = (row['c_canon'] * 4.0) + (row['h_garrot'] * 0.3) + (gmq * 0.03)
    return round(gmq, 1), round(rendement, 1), round(index, 2)

def generer_donnees_demo(n=500):
    conn = get_db_connection()
    c = conn.cursor()
    races = ["Ouled Djellal", "Rembi", "Hamra"]
    for i in range(n):
        a_id = f"DEMO-{1000 + i}"
        race = random.choice(races)
        date_n = (datetime.now() - timedelta(days=random.randint(100, 600))).strftime('%Y-%m-%d')
        p10 = round(random.uniform(3.5, 6.5), 1)
        p30 = round(p10 * 2.5 + random.uniform(-1, 1), 1)
        p70 = round(p30 * 1.8 + random.uniform(-2, 2), 1)
        cc = round(7 + (p70 * 0.1) + random.uniform(-0.5, 0.5), 1)
        hg = round(60 + (p70 * 0.4) + random.uniform(-2, 2), 1)
        pt = round(hg * 1.2, 1)
        lp = round(cc * 2, 1)
        c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (a_id, race, date_n, "Viande", "2 Dents"))
        c.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (a_id, p10, p30, p70, hg, 80.0, pt, lp, cc))
    conn.commit()
    conn.close()

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, dentition TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION & SIDEBAR ---
st.sidebar.title("💎 Selector Ultra")
if st.sidebar.button("🚀 GÉNÉRER 500 SUJETS"):
    generer_donnees_demo(500)
    st.sidebar.success("500 sujets créés !")
    st.rerun()

if st.sidebar.button("🗑️ VIDER LA BASE"):
    conn = get_db_connection()
    conn.execute("DELETE FROM beliers"); conn.execute("DELETE FROM mesures"); conn.commit()
    st.sidebar.warning("Base vidée.")
    st.rerun()

st.sidebar.divider()
obj_selection = st.sidebar.selectbox("🎯 Objectif de Sélection", ["Viande", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📈 Analyse Scientifique", "✍️ Saisie Manuelle", "📥 Import/Export"])

# Chargement données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x, obj_selection)), axis=1)

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("📊 Registre du Troupeau")
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Effectif Total", len(df))
        c2.metric("GMQ Moyen", f"{df['GMQ'].mean().round(1)} g/j")
        c3.metric("Moyenne Canon", f"{df['c_canon'].mean().round(2)} cm")
        
        st.dataframe(df[['id', 'race', 'p70', 'c_canon', 'GMQ', 'Index']].sort_values('Index', ascending=False), use_container_width=True)
    else:
        st.info("La base est vide. Utilisez le bouton 'Générer' à gauche pour tester.")

elif menu == "📈 Analyse Scientifique":
    st.title("🔬 Laboratoire d'Analyse")
    if df.empty:
        st.warning("Aucune donnée disponible.")
    else:
        # Matrice
        cols_ana = ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'l_poitrine', 'c_canon', 'GMQ']
        st.subheader("📊 Influence des variables")
        fig_corr = px.imshow(df[cols_ana].corr(), text_auto=True, color_continuous_scale='RdBu_r')
        st.plotly_chart(fig_corr, use_container_width=True)

        # Top Impacts
        st.divider()
        st.subheader("🏆 Classement des impacts sur le Poids Final (J70)")
        influences = df[cols_ana].corr()['p70'].abs().drop('p70').sort_values(ascending=False)
        
        noms_clairs = {'c_canon': '🦴 Canon', 'p_thoracique': '🫁 Thorax', 'h_garrot': '📏 Hauteur', 'p30': '📈 Poids J30', 'l_poitrine': '🥩 Poitrine', 'p10': '🍼 Poids J10', 'GMQ': '🚀 Croissance'}
        rank_df = pd.DataFrame({"Critère": [noms_clairs.get(x, x) for x in influences.index], "Force (%)": (influences.values * 100).round(1)})
        
        col_t, col_g = st.columns([1, 2])
        col_t.table(rank_df)
        col_g.plotly_chart(px.bar(rank_df, x="Force (%)", y="Critère", orientation='h', color="Force (%)"), use_container_width=True)

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie de Précision")
    with st.form("form_complet"):
        c1, c2 = st.columns(2)
        with c1:
            m_id = st.text_input("ID Animal")
            m_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            m_methode = st.radio("Âge :", ["Date", "Dents"])
            m_val = st.date_input("Date") if m_methode == "Date" else st.selectbox("Dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            p10, p30, p70 = st.number_input("Poids J10"), st.number_input("Poids J30"), st.number_input("Poids J70")
        with c2:
            hg, pt, lp, lc, cc = st.number_input("Hauteur Garrot"), st.number_input("Périm. Thoracique"), st.number_input("Largeur Poitrine"), st.number_input("Long. Corps"), st.number_input("Circonf. Canon")
        
        if st.form_submit_button("💾 Enregistrer"):
            conn = get_db_connection()
            conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, m_race, str(m_val), obj_selection, str(m_val)))
            conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, lc, pt, lp, cc))
            conn.commit()
            st.success("Enregistré !"); st.rerun()

elif menu == "📥 Import/Export":
    st.title("📥 Gestion des données")
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False)
    st.download_button("📥 Télécharger le registre Excel", data=towrite, file_name="registre.xlsx")
