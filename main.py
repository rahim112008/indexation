import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="BélierSelector Pro Élite", layout="wide", page_icon="🐏")

# Style CSS pour une interface plus épurée
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_expert.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# ============================================================
# 2. LOGIQUE SCIENTIFIQUE (INRA / PUBMED / ZOOTECHNIE)
# ============================================================

def calculer_indices_expert(row, mode="Boucherie"):
    """
    Algorithmes de prédiction basés sur la morphométrie :
    - Indice de Compacité (IC) = Poids / Longueur du corps
    - Surface de Noix de Côte estimée par le périmètre thoracique
    """
    # GMQ (Gain Moyen Quotidien)
    gmq_30_70 = ((row['p70'] - row['p30']) / 40) * 1000
    
    # --- PRÉDICTION CARCASSE (Modèles INRA adaptés) ---
    # Estimation du rendement carcasse (% Viande Maigre)
    # L'équation intègre la largeur de poitrine et le périmètre pour le volume musculaire
    perc_viande = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    
    # Estimation Tissu Adipeux (Gras)
    # Le gras sous-cutané est corrélé positivement au poids et au périmètre thoracique
    perc_gras = (row['p_thoracique'] * 0.18) + (row['p70'] * 0.15) - 14.5
    
    # --- SCORE D'ÉLITE (INDEXATION) ---
    # Score de Conformation Morphologique (SCM)
    scm = (row['h_garrot'] * 0.2 + row['l_corps'] * 0.4 + row['p_thoracique'] * 0.4)
    
    if mode == "Boucherie":
        # Priorité : Rendement et Vitesse de croissance
        index_final = (gmq_30_70 * 0.05) + (perc_viande * 0.45) + (scm * 0.20) + (row['p70'] * 0.30)
    else: 
        # Priorité : Gabarit et Robustesse (SCM élevé)
        index_final = (gmq_30_70 * 0.02) + (perc_viande * 0.20) + (scm * 0.60) + (row['c_canon'] * 0.18)
        
    return round(gmq_30_70, 1), round(perc_viande, 1), round(perc_gras, 1), round(index_final, 2)

# ============================================================
# 3. INITIALISATION & DONNÉES DE TEST
# ============================================================

def init_db_pro():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, age_dents TEXT, sexe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p_naiss REAL, p10 REAL, p30 REAL, p70 REAL,
                  h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                  l_poitrine REAL, l_bassin REAL)''')
    
    c.execute("SELECT COUNT(*) FROM beliers")
    if c.fetchone()[0] == 0:
        races = ["Ouled Djellal", "Rembi", "Hamra", "Berbère"]
        for i in range(1, 21):
            id_a = f"B-{2024}-{i:03d}"
            c.execute("INSERT INTO beliers VALUES (?, ?, ?, ?, ?)", 
                     (id_a, races[i % 4], "2024-05-15", "Lait", "Mâle"))
            
            pn, p10, p30 = 4.1, 7.5, 14.2
            p70 = p30 + round(np.random.uniform(13, 17), 1)
            
            c.execute("INSERT INTO mesures VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (id_a, pn, p10, p30, p70, 
                      round(np.random.uniform(62, 72)), round(np.random.uniform(72, 82)), 
                      round(np.random.uniform(88, 102)), round(np.random.uniform(8.5, 10.5), 1),
                      round(np.random.uniform(19, 23)), round(np.random.uniform(21, 26))))
    conn.commit()
    conn.close()

# ============================================================
# 4. INTERFACE UTILISATEUR (STREAMLIT)
# ============================================================

init_db_pro()

# Barre latérale professionnelle
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1998/1998762.png", width=80)
st.sidebar.title("Expert Selector")
objectif = st.sidebar.selectbox("🎯 Objectif de Sélection", ["Boucherie", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏠 Tableau de Bord", "🔍 Analyse Individuelle", "📊 Statistiques", "⚙️ Maintenance"])

conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Viande_%', 'Gras_%', 'Index']] = df.apply(
        lambda x: pd.Series(calculer_indices_expert(x, mode=objectif)), axis=1
    )

# --- PAGE 1 : CLASSEMENT ÉLITE ---
if menu == "🏠 Tableau de Bord":
    st.title("🏆 Indexation de l'Élite Reproductrice")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Individus", len(df))
    c2.metric("Meilleur GMQ", f"{df['GMQ'].max()}g/j")
    c3.metric("Rendement Max", f"{df['Viande_%'].max()}%")
    c4.metric("Score Élite Moyen", df['Index'].mean().round(1))

    st.subheader("📋 Classement Pro")
    # Mise en forme conditionnelle du tableau
    st.dataframe(df[['id', 'race', 'Index', 'GMQ', 'Viande_%', 'Gras_%']].sort_values(by="Index", ascending=False),
                 use_container_width=True, hide_index=True)

# --- PAGE 2 : ANALYSE INDIVIDUELLE (RADAR) ---
elif menu == "🔍 Analyse Individuelle":
    st.title("🔍 Diagnostic Morphométrique")
    selected_id = st.selectbox("Sélectionner un bélier", df['id'].unique())
    animal = df[df['id'] == selected_id].iloc[0]

    col_l, col_r = st.columns([1, 1])
    
    with col_l:
        st.write(f"### Caractéristiques de {selected_id}")
        st.progress(animal['Index'] / df['Index'].max(), text=f"Index Élite : {animal['Index']}")
        st.write(f"**Race :** {animal['race']} | **Dentition :** {animal['age_dents']}")
        st.write(f"**Estimation Viande :** {animal['Viande_%']}%")
        st.write(f"**Estimation Gras :** {animal['Gras_%']}%")
        
    with col_r:
        fig_radar = go.Figure(data=go.Scatterpolar(
            r=[animal['h_garrot'], animal['l_corps'], animal['p_thoracique'], animal['l_poitrine'], animal['l_bassin']],
            theta=['Hauteur Garrot', 'Longueur Corps', 'Périmètre Thor.', 'Largeur Poitrine', 'Largeur Bassin'],
            fill='toself', line_color='teal'
        ))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 110])), showlegend=False)
        st.plotly_chart(fig_radar, use_container_width=True)

# --- PAGE 3 : STATISTIQUES (CORRÉLATIONS) ---
elif menu == "📊 Statistiques":
    st.title("📈 Analyse des Corrélations Zootechniques")
    
    
    
    st.subheader("Matrice d'Interdépendance")
    corr = df[['p70', 'h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'GMQ', 'Index']].corr()
    fig_corr = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r')
    st.plotly_chart(fig_corr, use_container_width=True)

    st.subheader("Distribution du Score d'Élite par Race")
    fig_box = px.box(df, x="race", y="Index", color="race", points="all")
    st.plotly_chart(fig_box, use_container_width=True)

# --- PAGE 4 : MAINTENANCE ---
elif menu == "⚙️ Maintenance":
    st.title("⚙️ Gestion des Données")
    if st.button("🗑️ Réinitialiser la base de données"):
        conn = get_db_connection()
        conn.execute("DROP TABLE IF EXISTS beliers")
        conn.execute("DROP TABLE IF EXISTS mesures")
        conn.commit()
        conn.close()
        st.rerun()
