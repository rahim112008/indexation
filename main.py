import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Élite - Demo", layout="wide")

DB_NAME = "elevage_elite.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# ============================================================
# 1. INITIALISATION ET INJECTION DES DONNÉES DE TEST
# ============================================================

def init_db_with_data():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Création des tables
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, sexe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p_naiss REAL, p10 REAL, p30 REAL, p70 REAL,
                  h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL)''')
    
    # Vérification si la base est vide
    c.execute("SELECT COUNT(*) FROM beliers")
    if c.fetchone()[0] == 0:
        races = ["Rembi", "Ouled Djellal", "Hamra", "Berbère"]
        for i in range(1, 21):
            id_a = f"ELITE-{2024}-{i:03d}"
            race = races[i % len(races)]
            
            # 1. Identité
            c.execute("INSERT INTO beliers VALUES (?, ?, ?, ?)", 
                     (id_a, race, "2024-01-10", "Mâle"))
            
            # 2. Mesures simulées avec variations naturelles
            p_n = round(np.random.uniform(3.8, 4.5), 1)
            p10 = p_n + round(np.random.uniform(2.8, 3.5), 1)
            p30 = p10 + round(np.random.uniform(6.0, 8.0), 1)
            p70 = p30 + round(np.random.uniform(12.0, 16.0), 1)
            
            h_g = round(np.random.uniform(62, 78))
            l_c = round(np.random.uniform(72, 88))
            p_t = round(np.random.uniform(85, 105))
            c_c = round(np.random.uniform(8.5, 11.0), 1)
            
            c.execute('''INSERT INTO mesures VALUES (?,?,?,?,?,?,?,?,?)''', 
                     (id_a, p_n, p10, p30, p70, h_g, l_c, p_t, c_c))
        
        conn.commit()
        st.success("✅ Base de données initialisée avec 20 individus de test.")
    
    conn.close()

# ============================================================
# 2. LOGIQUE DE CALCULS SCIENTIFIQUES
# ============================================================

def calculer_indices(row):
    # GMQ 30-70 (Critère majeur de sélection)
    gmq_30_70 = ((row['p70'] - row['p30']) / 40) * 1000
    
    # Estimation Viande (Basée sur le volume corporel et poids)
    # Formule : (Poids * Coeff) + (Conformation * Coeff)
    viande = (row['p70'] * 0.48) + (row['p_thoracique'] * 0.05)
    gras = (row['p70'] * 0.12)
    
    # SCORE D'ÉLITE FINAL (Indexation)
    # Pondération : 40% Croissance, 40% Morphologie, 20% Rendement Viande
    score_morpho = (row['h_garrot'] * 0.2 + row['l_corps'] * 0.5 + row['p_thoracique'] * 0.3)
    index_final = (gmq_30_70 * 0.04) + (score_morpho * 0.3) + (viande * 0.3)
    
    return round(gmq_30_70, 1), round(viande, 2), round(index_final, 2)

# ============================================================
# 3. INTERFACE UTILISATEUR
# ============================================================

init_db_with_data()

st.title("🐏 BélierSelector Pro - Système d'Indexation")

# Chargement des données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

# Application des calculs sur toute la base
df[['GMQ_30_70', 'Viande_estim', 'Score_Elite']] = df.apply(
    lambda x: pd.Series(calculer_indices(x)), axis=1
)

# --- AFFICHAGE ---
tab1, tab2, tab3 = st.tabs(["🏆 Classement Élite", "📊 Analyse Statistique", "📋 Base de Données"])

with tab1:
    st.subheader("Classement des meilleurs reproducteurs")
    top_5 = df.sort_values(by="Score_Elite", ascending=False).head(10)
    st.dataframe(top_5[['id', 'race', 'Score_Elite', 'GMQ_30_70', 'Viande_estim']], use_container_width=True)

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.write("Distribution du Score d'Élite")
        st.bar_chart(df.groupby('race')['Score_Elite'].mean())
    with col2:
        st.write("Corrélation Poids J70 / Circonférence Canon")
        st.scatter_chart(df, x="p70", y="c_canon", color="race")

with tab3:
    st.subheader("Données brutes de la base SQL")
    st.write(df)
