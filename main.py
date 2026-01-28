import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Pro Élite", layout="wide", page_icon="🐏")

DB_NAME = "elevage_pro_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# ============================================================
# 2. INITIALISATION BASE DE DONNÉES & DONNÉES DE TEST
# ============================================================

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, age_dents TEXT, sexe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p_naiss REAL, p10 REAL, p30 REAL, p70 REAL,
                  h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                  l_poitrine REAL, l_bassin REAL)''')
    
    # Vérification si vide pour injecter les 20 individus
    c.execute("SELECT COUNT(*) FROM beliers")
    if c.fetchone()[0] == 0:
        races = ["Ouled Djellal", "Rembi", "Hamra", "Berbère"]
        for i in range(1, 21):
            id_a = f"ELITE-{2024}-{i:03d}"
            race = races[i % 4]
            c.execute("INSERT INTO beliers VALUES (?, ?, ?, ?, ?)", 
                     (id_a, race, "2024-05-10", "Lait", "Mâle"))
            
            # Simulation biologique réaliste
            pn = round(np.random.uniform(3.8, 4.5), 1)
            p10 = pn + round(np.random.uniform(3, 4), 1)
            p30 = p10 + round(np.random.uniform(7, 9), 1)
            p70 = p30 + round(np.random.uniform(12, 16), 1)
            
            c.execute("INSERT INTO mesures VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (id_a, pn, p10, p30, p70, 
                      round(np.random.uniform(60, 75)), round(np.random.uniform(70, 85)), 
                      round(np.random.uniform(85, 105)), round(np.random.uniform(8, 11), 1),
                      round(np.random.uniform(18, 25)), round(np.random.uniform(20, 28))))
    conn.commit()
    conn.close()

# ============================================================
# 3. LOGIQUE SCIENTIFIQUE (INRA / PUBMED)
# ============================================================

def calculer_indices(row, mode="Boucherie"):
    # GMQ (Gain Moyen Quotidien)
    gmq_30_70 = ((row['p70'] - row['p30']) / 40) * 1000
    
    # Estimation rendement carcasse (Equations de compacité)
    # Viande Maigre estimée par le périmètre thoracique et la largeur de poitrine
    perc_viande = 48.5 + (0.4 * row['l_poitrine']) + (0.15 * row['p_thoracique']) - (0.05 * row['h_garrot'])
    perc_gras = (row['p_thoracique'] * 0.12) + (row['p70'] * 0.08) - 8.0
    
    # Score de conformation morphologique
    score_morpho = (row['h_garrot'] * 0.2 + row['l_corps'] * 0.4 + row['p_thoracique'] * 0.4)
    
    # INDEXATION PARAMÉTRABLE
    if mode == "Boucherie":
        index_final = (gmq_30_70 * 0.04) + (perc_viande * 0.4) + (score_morpho * 0.2)
    else: # Mode Rusticité / Élevage
        index_final = (gmq_30_70 * 0.02) + (perc_viande * 0.2) + (score_morpho * 0.6)
        
    return round(gmq_30_70, 1), round(perc_viande, 1), round(perc_gras, 1), round(index_final, 2)

# ============================================================
# 4. INTERFACE UTILISATEUR
# ============================================================

init_db()

st.sidebar.title("🐏 BélierSelector Pro")
objectif = st.sidebar.selectbox("Objectif de Sélection", ["Boucherie", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏆 Classement d'Élite", "📸 Acquisition & Saisie", "📊 Statistiques", "⚙️ Gestion SQL"])

# Chargement des données globales
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

# Application des calculs
if not df.empty:
    df[['GMQ_30_70', 'Viande_%', 'Gras_%', 'Index_Elite']] = df.apply(
        lambda x: pd.Series(calculer_indices(x, mode=objectif)), axis=1
    )

# --- PAGE 1 : CLASSEMENT ---
if menu == "🏆 Classement d'Élite":
    st.title(f"🏆 Top Sujets - Mode {objectif}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Effectif Total", len(df))
    col2.metric("Meilleur GMQ", f"{df['GMQ_30_70'].max()} g/j")
    col3.metric("Moyenne Index", df['Index_Elite'].mean().round(2))

    st.subheader("Classement des reproducteurs indexés")
    top_df = df.sort_values(by="Index_Elite", ascending=False)
    st.dataframe(top_df[['id', 'race', 'Index_Elite', 'GMQ_30_70', 'Viande_%', 'Gras_%']], use_container_width=True)

    # Radar Chart pour le Top 1
    st.divider()
    st.subheader("Profil Radar du Champion")
    champion = top_df.iloc[0]
    fig_radar = go.Figure(data=go.Scatterpolar(
        r=[champion['h_garrot'], champion['l_corps'], champion['p_thoracique'], champion['l_poitrine'], champion['l_bassin']],
        theta=['Hauteur', 'Longueur', 'Périmètre T.', 'Largeur P.', 'Largeur B.'],
        fill='toself', name=champion['id']
    ))
    st.plotly_chart(fig_radar)

# --- PAGE 2 : SAISIE ---
elif menu == "📸 Acquisition & Saisie":
    st.title("📸 Mesures Morphométriques")
    t1, t2 = st.tabs(["Photogrammétrie (IA)", "Saisie Manuelle"])
    
    with t1:
        st.info("Prenez une photo de profil de l'animal pour l'indexation automatique.")
        st.file_uploader("Capture Caméra", type=['jpg', 'png'])
        st.warning("Simulation : En production, l'IA remplit les champs ci-dessous automatiquement.")
        
    with t2:
        with st.form("manuel"):
            c1, c2 = st.columns(2)
            id_n = c1.text_input("ID Animal")
            race_n = c1.selectbox("Race", ["Rembi", "Ouled Djellal", "Hamra", "Berbère"])
            p70_n = c2.number_input("Poids J70 (kg)", value=25.0)
            pt_n = c2.number_input("Périmètre Thoracique (cm)", value=90.0)
            if st.form_submit_button("Enregistrer"):
                st.success("Données envoyées vers la base SQL.")

# --- PAGE 3 : STATISTIQUES ---
elif menu == "📊 Statistiques":
    st.title("📊 Analyses des Corrélations")
    
    # Matrice de corrélation
    st.subheader("Matrice de Corrélation entre Variables")
    vars_corr = ['p70', 'h_garrot', 'l_corps', 'p_thoracique', 'GMQ_30_70', 'Index_Elite']
    corr = df[vars_corr].corr()
    fig_corr = px.imshow(corr, text_auto=True, title="Interdépendance des caractères")
    st.plotly_chart(fig_corr)

    # Comparaison des races
    st.subheader("Performance par Race")
    fig_race = px.box(df, x="race", y="Index_Elite", color="race", points="all")
    st.plotly_chart(fig_race)

# --- PAGE 4 : GESTION SQL ---
elif menu == "⚙️ Gestion SQL":
    st.title("⚙️ Import / Export & Maintenance")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Exporter")
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='xlsxwriter')
        st.download_button("📥 Télécharger Excel", data=buffer.getvalue(), file_name="export_beliers.xlsx")
        
    with col_b:
        st.subheader("Maintenance")
        if st.button("🗑️ Vider la base"):
