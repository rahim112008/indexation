import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
from datetime import datetime, timedelta
import io

st.set_page_config(page_title="Expert Selector 500", layout="wide")

# --- DATABASE ---
DB_NAME = "expert_ultra_500.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

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

# --- CALCULS ---
def calculer_score(row):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if (row['p70'] > 0 and row['p30'] > 0) else 0
    # Score basé sur la solidité (Canon) et la croissance
    score = (row['c_canon'] * 5) + (gmq * 0.05) + (row['h_garrot'] * 0.2)
    return round(gmq, 1), round(score, 2)

# --- INTERFACE ---
st.sidebar.title("🐏 Menu Test 500")
menu = st.sidebar.radio("Navigation", ["📸 Scanner IA", "✍️ Saisie Manuelle", "📊 Dashboard & Analyse", "📥 Export Excel"])

if menu == "📸 Scanner IA":
    st.title("📸 Simulation de Mesure Automatique")
    st.write("Placez l'animal de profil pour capturer la silhouette.")
    
    # Simulation de détection IA
    cam = st.camera_input("Prendre une photo de l'animal")
    
    if cam:
        st.success("Analyse de l'image en cours...")
        # Simulation des points détectés
        col1, col2 = st.columns(2)
        with col1:
            st.image(cam, caption="Analyse de la silhouette")
        with col2:
            st.metric("Hauteur Garrot détectée", "74 cm")
            st.metric("Canon estimé", "10.5 cm")
            st.metric("Confiance IA", "94%")

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie pour les 500 têtes")
    with st.form("form_500"):
        c1, c2 = st.columns(2)
        with c1:
            m_id = st.text_input("ID Boucle")
            m_methode = st.radio("Âge par :", ["Dents", "Mois exact"])
            if m_methode == "Dents":
                m_val = st.selectbox("Dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            else:
                m_val = st.number_input("Mois", 1, 60)
            
            p10 = st.number_input("Poids J10", 0.0)
            p30 = st.number_input("Poids J30", 0.0)
            p70 = st.number_input("Poids J70", 0.0)
        
        with c2:
            cc = st.number_input("Circonférence Canon (cm)", 0.0)
            hg = st.number_input("Hauteur Garrot (cm)", 0.0)
            pt = st.number_input("Périmètre Thoracique (cm)", 0.0)
            
        if st.form_submit_button("Enregistrer"):
            conn = get_db_connection()
            conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, "Rembi", str(m_val), "Viande", str(m_val)))
            conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, 0, pt, 0, cc))
            conn.commit()
            st.success(f"Animal {m_id} ajouté !")

elif menu == "📊 Dashboard & Analyse":
    st.title("📊 Analyse des Performances")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    
    if not df.empty:
        df[['GMQ', 'Score']] = df.apply(lambda x: pd.Series(calculer_score(x)), axis=1)
        
        st.subheader("Top 10 des meilleurs sujets")
        st.dataframe(df[['id', 'GMQ', 'c_canon', 'Score']].sort_values('Score', ascending=False).head(10))
        
        # Graphique pour voir la distribution des 500 têtes
        fig = px.scatter(df, x="c_canon", y="GMQ", size="p70", hover_name="id", title="Corrélation Canon / Croissance")
        st.plotly_chart(fig, use_container_width=True)

elif menu == "📥 Export Excel":
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False)
    st.download_button("Télécharger le registre complet", data=towrite, file_name="registre_500.xlsx")
