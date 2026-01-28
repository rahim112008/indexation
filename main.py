import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- CONFIGURATION ET STYLE ---
st.set_page_config(page_title="BélierSelector Pro Élite", layout="wide", page_icon="🐏")

# --- 1. ARCHITECTURE DE LA BASE DE DONNÉES ---
DB_NAME = "selection_genetique.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Table des Béliers
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, sexe TEXT)''')
    # Table des Mesures (Croissance et Morphométrie combinées pour simplifier le script)
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, date_mesure TEXT, 
                  p_naiss REAL, p10 REAL, p30 REAL, p70 REAL,
                  h_garrot REAL, l_corps REAL, h_corps REAL, p_thoracique REAL, c_canon REAL,
                  l_poitrine REAL, l_bassin REAL, l_tete REAL,
                  FOREIGN KEY(id_animal) REFERENCES beliers(id))''')
    conn.commit()
    conn.close()

# --- 2. LOGIQUE DE CALCUL (SCORES & COMPOSITION) ---
def calculer_metrics(row):
    # Calcul des GMQ (en grammes/jour)
    gmq_0_10 = ((row['p10'] - row['p_naiss']) / 10) * 1000 if row['p10'] else 0
    gmq_10_30 = ((row['p30'] - row['p10']) / 20) * 1000 if row['p30'] and row['p10'] else 0
    gmq_30_70 = ((row['p70'] - row['p30']) / 40) * 1000 if row['p70'] and row['p30'] else 0
    
    # Estimation Composition Corporelle (Algorithme prédictif)
    # Ratio basé sur le volume corporel vs Poids
    volume_index = (row['l_corps'] * row['p_thoracique'] * row['h_garrot']) / 1000
    viande_estim = (row['p70'] * 0.45) + (row['l_corps'] * 0.1) # Coefficient de musculature
    gras_estim = (row['p70'] * 0.15) # Estimation simplifiée du tissu adipeux
    
    # Score Morphologique (Indice de conformation)
    score_morpho = (row['h_garrot'] * 0.3 + row['l_corps'] * 0.4 + row['p_thoracique'] * 0.3)
    
    # SCORE D'ÉLITE (INDEXATION FINALE)
    # Pondération : 30% GMQ 30-70, 40% Morpho, 20% Viande, 10% Poids J70
    indice_elite = (gmq_30_70 * 0.03) + (score_morpho * 0.4) + (viande_estim * 0.2) + (row['p70'] * 0.1)
    
    return round(gmq_30_70, 1), round(viande_estim, 2), round(indice_elite, 2)

# --- 3. INTERFACE UTILISATEUR (UI) ---
init_db()
st.sidebar.title("🧬 Sélection Génétique")
menu = st.sidebar.radio("Navigation", ["Tableau de Bord", "Saisie des Mesures", "Analyse Statistique", "Gestion SQL"])

# --- PAGE : TABLEAU DE BORD ---
if menu == "Tableau de Bord":
    st.title("🏆 Indexation des Béliers d'Élite")
    
    conn = get_db_connection()
    df = pd.read_sql('''SELECT * FROM beliers INNER JOIN mesures ON beliers.id = mesures.id_animal''', conn)
    conn.close()

    if not df.empty:
        # Application des calculs
        df[['GMQ_30_70', 'Viande_Kg', 'Score_Elite']] = df.apply(
            lambda x: pd.Series(calculer_metrics(x)), axis=1
        )
        
        # Top 5 Béliers
        st.subheader("🥇 Top 5 Sujets d'Élite")
        top_df = df.sort_values(by="Score_Elite", ascending=False).head(5)
        st.table(top_df[['id', 'race', 'Score_Elite', 'GMQ_30_70', 'Viande_Kg']])

        # Visualisation
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(df, x="l_corps", y="p70", size="Score_Elite", color="race", 
                             title="Corrélation : Longueur vs Poids J70")
            st.plotly_chart(fig)
        with col2:
            fig_hist = px.histogram(df, x="Score_Elite", nbins=10, title="Distribution de l'Indice d'Élite", color_discrete_sequence=['gold'])
            st.plotly_chart(fig_hist)
    else:
        st.info("Aucune donnée disponible. Veuillez saisir des mesures.")

# --- PAGE : SAISIE DES MESURES ---
elif menu == "Saisie des Mesures":
    st.title("📏 Caractérisation Morpho-métrique")
    
    tab_cam, tab_man = st.tabs(["📸 Mode Caméra (IA)", "⌨️ Saisie Manuelle"])
    
    with tab_cam:
        st.warning("⚙️ Analyse par Computer Vision simulée")
        img = st.file_uploader("Prendre une photo du bélier (Profil)", type=['jpg', 'jpeg', 'png'])
        if img:
            st.image(img, caption="Traitement des points morphométriques...", width=400)
            st.info("L'algorithme détecte : Hauteur au garrot, Longueur du corps et Périmètre.")

    with tab_man:
        with st.form("form_mesures"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("**Identité**")
                id_a = st.text_input("ID Animal (ex: B-2024-01)")
                race = st.selectbox("Race", ["Rembi", "Ouled Djellal", "Hamra", "Berbère"])
            with c2:
                st.write("**Croissance (Kg)**")
                p_n = st.number_input("Poids Naissance", 1.0, 8.0, 4.0)
                p10 = st.number_input("Poids J10", 3.0, 15.0, 7.0)
                p30 = st.number_input("Poids J30", 8.0, 25.0, 12.0)
                p70 = st.number_input("Poids J70", 15.0, 45.0, 22.0)
            with c3:
                st.write("**Morphométrie (cm)**")
                h_g = st.number_input("Hauteur Garrot", 40, 100, 65)
                l_c = st.number_input("Longueur Corps", 40, 120, 75)
                p_t = st.number_input("Périmètre Thoracique", 50, 130, 85)
                c_c = st.number_input("C. Canon", 5.0, 15.0, 9.0)
            
            if st.form_submit_button("Enregistrer le Phénotype"):
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO beliers VALUES (?, ?, ?, ?)", (id_a, race, str(datetime.now().date()), "Mâle"))
                    cur.execute("INSERT INTO mesures (id_animal, date_mesure, p_naiss, p10, p30, p70, h_garrot, l_corps, p_thoracique, c_canon) VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                (id_a, str(datetime.now().date()), p_n, p10, p30, p70, h_g, l_c, p_t, c_c))
                    conn.commit()
                    conn.close()
                    st.success(f"Données enregistrées pour {id_a} !")
                except Exception as e:
                    st.error(f"Erreur : {e}")

# --- PAGE : ANALYSE STATISTIQUE ---
elif menu == "Analyse Statistique":
    st.title("📊 Analyses Scientifiques")
    conn = get_db_connection()
    df = pd.read_sql('''SELECT * FROM beliers INNER JOIN mesures ON beliers.id = mesures.id_animal''', conn)
    conn.close()

    if not df.empty:
        df[['GMQ_30_70', 'Viande_Kg', 'Score_Elite']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
        
        st.subheader("📈 Statistiques Descriptives")
        st.write(df[['p70', 'h_garrot', 'l_corps', 'GMQ_30_70', 'Score_Elite']].describe())

        st.subheader("🧬 Comparaison par Race")
        race_avg = df.groupby('race')[['Score_Elite', 'GMQ_30_70']].mean()
        st.bar_chart(race_avg)

# --- PAGE : GESTION SQL ---
elif menu == "Gestion SQL":
    st.title("⚙️ Administration des Données")
    
    col_exp, col_imp = st.columns(2)
    
    with col_exp:
        st.subheader("📤 Exportation")
        conn = get_db_connection()
        full_df = pd.read_sql("SELECT * FROM beliers INNER JOIN mesures ON beliers.id = mesures.id_animal", conn)
        conn.close()
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            full_df.to_excel(writer, index=False, sheet_name='Base_Elite')
        
        st.download_button(label="Télécharger Base Excel", data=output.getvalue(), file_name="selection_genetique_export.xlsx")

    with col_imp:
        st.subheader("🗑️ Nettoyage")
        if st.button("Réinitialiser la Base de Données"):
            conn = get_db_connection()
            conn.execute("DROP TABLE IF EXISTS beliers")
            conn.execute("DROP TABLE IF EXISTS mesures")
            conn.commit()
            conn.close()
            st.warning("Base de données effacée.")
