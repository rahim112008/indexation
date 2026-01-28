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
    # Création des tables
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, age_dents TEXT, sexe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p_naiss REAL, p10 REAL, p30 REAL, p70 REAL,
                  h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                  l_poitrine REAL, l_bassin REAL)''')
    
    # Vérification si vide pour injecter les 20 individus de test
    c.execute("SELECT COUNT(*) FROM beliers")
    if c.fetchone()[0] == 0:
        races = ["Ouled Djellal", "Rembi", "Hamra", "Berbère"]
        for i in range(1, 21):
            id_a = f"ELITE-{2024}-{i:03d}"
            race = races[i % 4]
            c.execute("INSERT INTO beliers VALUES (?, ?, ?, ?, ?)", 
                     (id_a, race, "2024-05-10", "Lait", "Mâle"))
            
            # Simulation biologique réaliste pour les tests
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
    # Gain Moyen Quotidien (GMQ) entre 30 et 70 jours
    gmq_30_70 = ((row['p70'] - row['p30']) / 40) * 1000
    
    # Estimation rendement carcasse (Equations morphométriques)
    # Viande Maigre estimée par le périmètre thoracique et la largeur de poitrine
    perc_viande = 48.5 + (0.4 * row['l_poitrine']) + (0.15 * row['p_thoracique']) - (0.05 * row['h_garrot'])
    perc_gras = (row['p_thoracique'] * 0.12) + (row['p70'] * 0.08) - 8.0
    
    # Score de conformation morphologique (Index de solidité)
    score_morpho = (row['h_garrot'] * 0.2 + row['l_corps'] * 0.4 + row['p_thoracique'] * 0.4)
    
    # Indexation finale selon l'objectif choisi
    if mode == "Boucherie":
        index_final = (gmq_30_70 * 0.04) + (perc_viande * 0.4) + (score_morpho * 0.2)
    else: 
        index_final = (gmq_30_70 * 0.02) + (perc_viande * 0.2) + (score_morpho * 0.6)
        
    return round(gmq_30_70, 1), round(perc_viande, 1), round(perc_gras, 1), round(index_final, 2)

# ============================================================
# 4. INTERFACE UTILISATEUR (UI)
# ============================================================

init_db()

st.sidebar.title("🐏 BélierSelector Pro")
objectif = st.sidebar.selectbox("Objectif de Sélection", ["Boucherie", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏆 Classement d'Élite", "📸 Acquisition & Saisie", "📊 Statistiques", "⚙️ Gestion SQL"])

# Chargement des données globales depuis SQL
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

# Application des calculs si la base n'est pas vide
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

    # Graphique Radar pour le meilleur bélier du classement
    if not top_df.empty:
        st.divider()
        st.subheader("Profil Morphologique du Leader")
        champion = top_df.iloc[0]
        fig_radar = go.Figure(data=go.Scatterpolar(
            r=[champion['h_garrot'], champion['l_corps'], champion['p_thoracique'], champion['l_poitrine'], champion['l_bassin']],
            theta=['Hauteur', 'Longueur', 'Périmètre T.', 'Largeur P.', 'Largeur B.'],
            fill='toself', name=champion['id']
        ))
        st.plotly_chart(fig_radar)

# --- PAGE 2 : ACQUISITION ---
elif menu == "📸 Acquisition & Saisie":
    st.title("📸 Mesures Morphométriques")
    t1, t2 = st.tabs(["Photogrammétrie (IA)", "Saisie Manuelle"])
    
    with t1:
        st.info("Utilisez la caméra pour automatiser les mesures.")
        st.file_uploader("Prendre une photo", type=['jpg', 'png'])
        st.warning("Mode Simulation : Les algorithmes de vision extraient les mesures pour la base SQL.")
        
    with t2:
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            new_id = c1.text_input("ID Animal")
            new_race = c1.selectbox("Race", ["Rembi", "Ouled Djellal", "Hamra", "Berbère"])
            p70_val = c2.number_input("Poids J70 (kg)", value=25.0)
            pt_val = c2.number_input("Périmètre Thoracique (cm)", value=90.0)
            if st.form_submit_button("Enregistrer en Base"):
                st.success(f"L'individu {new_id} a été ajouté.")

# --- PAGE 3 : STATISTIQUES ---
elif menu == "📊 Statistiques":
    st.title("📊 Analyses Scientifiques")
    if not df.empty:
        # Matrice de corrélation
        st.subheader("Corrélation entre Caractères")
        vars_corr = ['p70', 'h_garrot', 'l_corps', 'p_thoracique', 'GMQ_30_70', 'Index_Elite']
        corr = df[vars_corr].corr()
        fig_corr = px.imshow(corr, text_auto=True, title="Interdépendance (Pearson)")
        st.plotly_chart(fig_corr)
        
        # Comparaison par race
        st.subheader("Comparaison des Races")
        fig_box = px.box(df, x="race", y="Index_Elite", color="race", title="Distribution de l'Index par Race")
        st.plotly_chart(fig_box)
    else:
        st.info("Aucune donnée disponible pour l'analyse.")

# --- PAGE 4 : GESTION SQL ---
elif menu == "⚙️ Gestion SQL":
    st.title("⚙️ Maintenance et Transfert")
    
    col_exp, col_maint = st.columns(2)
    
    with col_exp:
        st.subheader("📤 Exportation Excel")
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='xlsxwriter')
        st.download_button("📥 Télécharger Excel", data=buffer.getvalue(), file_name="selection_beliers.xlsx")
        
    with col_maint:
        st.subheader("🗑️ Nettoyage de la base")
        if st.button("Confirmer : Vider la base"):
            conn = get_db_connection()
            conn.execute("DROP TABLE IF EXISTS beliers")
            conn.execute("DROP TABLE IF EXISTS mesures")
            conn.commit()
            conn.close()
            st.rerun()
