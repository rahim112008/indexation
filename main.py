import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
from datetime import datetime
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Expert Selector 500", layout="wide", page_icon="🐏")

DB_NAME = "expert_ultra_500.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- INITIALISATION BASE ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, age_info TEXT, methode_age TEXT, objectif TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                  l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- NAVIGATION ---
st.sidebar.title("💎 Selector 500")
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "✍️ Saisie (Manuel/Auto)", "📈 Analyse 500 têtes", "📥 Export"])

# --- PAGE SAISIE (AVEC CANON) ---
if menu == "✍️ Saisie (Manuel/Auto)":
    st.title("✍️ Enregistrement de l'individu")
    
    with st.form("form_global"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🆔 Identification")
            m_id = st.text_input("ID Boucle (Ex: DZ-2024-001)")
            m_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            
            st.divider()
            st.subheader("🗓️ Détermination de l'âge")
            m_methode = st.radio("Méthode :", ["Exact (Mois)", "Dents"])
            if m_methode == "Exact (Mois)":
                m_val = st.number_input("Nombre de mois", 1, 120, 12)
            else:
                m_val = st.selectbox("Dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])

        with col2:
            st.subheader("⚖️ Pesées (kg)")
            p10 = st.number_input("Poids J10", 0.0)
            p30 = st.number_input("Poids J30", 0.0)
            p70 = st.number_input("Poids J70", 0.0)
            
            st.divider()
            st.subheader("📏 Mensurations (cm)")
            hg = st.number_input("Hauteur Garrot", 0.0)
            pt = st.number_input("Périmètre Thoracique", 0.0)
            
            # --- CHAMP CANON ---
            st.markdown("### 🦴 Solidité du Canon")
            
            cc = st.number_input("Circonférence du Canon (cm)", 0.0, help="Mesurer le tour de l'os au point le plus fin")

        if st.form_submit_button("💾 Enregistrer dans la base"):
            if m_id:
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, m_race, str(m_val), m_methode, "Sélection"))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, 0, pt, 0, cc))
                conn.commit()
                st.success(f"L'animal {m_id} a été ajouté !")
            else:
                st.error("L'ID est obligatoire.")

# --- PAGE DASHBOARD ---
elif menu == "🏠 Dashboard":
    st.title("📋 Registre des 500 Sujets")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    
    if not df.empty:
        # Calcul rapide du GMQ pour le tableau
        df['GMQ'] = ((df['p70'] - df['p30']) / 40) * 1000
        st.dataframe(df[['id', 'race', 'age_info', 'c_canon', 'p70', 'GMQ']], use_container_width=True)
    else:
        st.info("Aucune donnée pour le moment.")

# --- PAGE EXPORT ---
elif menu == "📥 Export":
    st.title("📥 Sauvegarde Excel")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    if not df.empty:
        output = io.BytesIO()
        df.to_excel(output, index=False)
        st.download_button("📥 Télécharger le registre (Excel)", data=output.getvalue(), file_name="registre_troupeau.xlsx")
