import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

DB_NAME = "expert_ultra_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. FONCTIONS DE CALCUL & DÉMO ---
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
        # Simulation réaliste avec corrélations naturelles
        p10 = round(random.uniform(3.5, 6.5), 1)
        p30 = round(p10 * 2.5 + random.uniform(-1, 1), 1)
        p70 = round(p30 * 1.8 + random.uniform(-2, 2), 1)
        cc = round(7 + (p70 * 0.1) + random.uniform(-0.5, 0.5), 1) # Corrélation Canon/Poids
        hg = round(60 + (p70 * 0.4) + random.uniform(-2, 2), 1)
        pt = round(hg * 1.2, 1)
        lp = round(cc * 2, 1)
        c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (a_id, race, date_n, "Viande", "Dents de lait"))
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
if st.sidebar.button("🚀 Générer 500 Sujets (DÉMO)"):
    generer_donnees_demo(500)
    st.sidebar.success("500 sujets créés !")
    st.rerun()

if st.sidebar.button("🗑️ Vider la base"):
    conn = get_db_connection()
    conn.execute("DELETE FROM beliers"); conn.execute("DELETE FROM mesures"); conn.commit()
    st.sidebar.warning("Base vidée.")
    st.rerun()

menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📈 Analyse Scientifique", "✍️ Saisie Manuelle", "📥 Import/Export"])

# Chargement données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)

# --- PAGE : ANALYSE SCIENTIFIQUE ---
if menu == "📈 Analyse Scientifique":
    st.title("🔬 Laboratoire d'Analyse des Corrélations")
    
    if df.empty:
        st.warning("Veuillez générer ou saisir des données pour voir l'analyse.")
    else:
        # 1. Matrice de Corrélation Globale
        st.subheader("📊 Matrice de Corrélation Globale")
        cols_ana = ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'l_poitrine', 'c_canon', 'GMQ']
        corr = df[cols_ana].corr()
        fig_corr = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r', title="Influence des variables entre elles")
        st.plotly_chart(fig_corr, use_container_width=True)
        

        st.divider()

        # 2. Analyse Séparée par Poids
        st.subheader("🔍 Analyse détaillée par stade de croissance")
        tab1, tab2, tab3 = st.tabs(["🍼 Corrélation J10", "🌾 Corrélation J30", "⚖️ Corrélation J70"])
        
        with tab1:
            st.write("Le poids à 10 jours dépend principalement de la valeur laitière de la mère.")
            var_x = st.selectbox("Comparer P10 avec :", ['c_canon', 'h_garrot', 'p_thoracique'], key="j10")
            fig1 = px.scatter(df, x=var_x, y="p10", color="race", trendline="ols", title=f"Lien entre {var_x} et Poids J10")
            st.plotly_chart(fig1, use_container_width=True)

        with tab2:
            st.write("Le poids à 30 jours montre le démarrage de l'autonomie de l'agneau.")
            var_x2 = st.selectbox("Comparer P30 avec :", ['c_canon', 'h_garrot', 'p_thoracique', 'l_poitrine'], key="j30")
            fig2 = px.scatter(df, x=var_x2, y="p30", color="race", trendline="ols", title=f"Lien entre {var_x2} et Poids J30")
            st.plotly_chart(fig2, use_container_width=True)

        with tab3:
            st.write("À 70 jours, la morphologie (Canon, Poitrine) doit confirmer le poids.")
            var_x3 = st.selectbox("Comparer P70 avec :", ['c_canon', 'h_garrot', 'p_thoracique', 'l_poitrine', 'GMQ'], key="j70")
            fig3 = px.scatter(df, x=var_x3, y="p70", color="race", trendline="ols", title=f"Lien entre {var_x3} et Poids J70")
            st.plotly_chart(fig3, use_container_width=True)
            

# (Les autres sections Dashboard et Saisie restent identiques à votre code précédent)
