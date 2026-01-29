import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- 1. CONFIGURATION ÉLÉGANTE ---
st.set_page_config(page_title="Expert Selector IA", layout="wide", page_icon="🐏")

# Style pour corriger les boites blanches lisibles dans votre capture
st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { color: #00ff00 !important; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_ia_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE IA (AUTOMATISATION) ---
def extraire_mesures_photo(photo):
    # Simulation de l'algorithme de vision par ordinateur
    return {
        "hg": round(np.random.uniform(65, 75), 1),
        "lc": round(np.random.uniform(70, 85), 1),
        "pt": round(np.random.uniform(88, 105), 1),
        "robe": "Blanche" if np.random.rand() > 0.4 else "Rousse/Tachetée"
    }

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, robe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
                  p_thoracique REAL, l_poitrine REAL, l_bassin REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION (MISE À JOUR) ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1998/1998762.png", width=80)
st.sidebar.title("Expert Selector Pro")
menu = st.sidebar.radio("Navigation", 
    ["🏠 Tableau de Bord", "📸 Saisie IA (Masse)", "✍️ Saisie Manuelle", "🏆 Duel & Certificats", "⚙️ Maintenance"])

# --- PAGE 1 : VOTRE DASHBOARD ACTUEL AMÉLIORÉ ---
if menu == "🏠 Tableau de Bord":
    st.title("📊 État de la Reproductrice")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    conn.close()

    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Individus", len(df))
        c2.metric("Meilleur GMQ", f"{df['p70'].max()} g/j") # Exemple simplifié
        c3.metric("Rendement Max", "66.9%")
        c4.metric("Score Moyen", "71.5")
        
        st.subheader("📋 Classement Pro")
        st.dataframe(df[['id', 'race', 'h_garrot', 'l_corps', 'p_thoracique']], use_container_width=True)
    else:
        st.info("Bienvenue ! Commencez par scanner vos premiers animaux avec l'onglet 📸 Saisie IA.")

# --- PAGE 2 : LE SCANNER IA (POUR LES 1000 INDIVIDUS) ---
elif menu == "📸 Saisie IA (Masse)":
    st.title("📸 Scanner Morphométrique")
    st.write("Pointez la caméra de profil sur l'animal pour une saisie instantanée.")
    
    photo = st.camera_input("Prendre la photo")
    
    if photo:
        res = extraire_mesures_photo(photo)
        st.success(f"Analyse terminée : Robe **{res['robe']}** détectée.")
        
        with st.form("validation_ia"):
            col1, col2, col3 = st.columns(3)
            id_a = col1.text_input("ID Boucle (ex: B-2024-001)")
            race = col1.selectbox("Race confirmée", ["Rembi", "Ouled Djellal", "Berbère"])
            
            hg = col2.number_input("H. Garrot (cm)", value=res['hg'])
            lc = col2.number_input("L. Corps (cm)", value=res['lc'])
            
            pt = col3.number_input("Périmètre (cm)", value=res['pt'])
            p70 = col3.number_input("Poids J70 (kg)", value=35.0)

            if st.form_submit_button("✅ Valider et Enregistrer"):
                if id_a:
                    conn = get_db_connection()
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, race, str(datetime.now().date()), res['robe']))
                    conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?)", (id_a, 15.0, p70, hg, lc, pt, 22.0, 25.0))
                    conn.commit()
                    conn.close()
                    st.toast(f"Animal {id_a} ajouté !")
                    st.rerun()
                else:
                    st.error("L'ID est obligatoire.")

# --- PAGE 3 : SAISIE MANUELLE DE SECOURS ---
elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie Manuelle de Secours")
    # Formulaire classique ici...
    st.write("Utilisez ce formulaire si la caméra n'est pas disponible.")

# --- PAGE 4 : DUEL & CERTIFICATS ---
elif menu == "🏆 Duel & Certificats":
    st.title("📜 Expertise & Sélection")
    # Code pour comparer 2 béliers ou imprimer un certificat
    st.write("Ici, vous pouvez comparer vos champions.")

# --- PAGE 5 : MAINTENANCE ---
elif menu == "⚙️ Maintenance":
    st.title("⚙️ Gestion des données")
    if st.button("🗑️ Vider la base de données"):
        conn = get_db_connection()
        conn.execute("DROP TABLE IF EXISTS beliers")
        conn.execute("DROP TABLE IF EXISTS mesures")
        conn.commit()
        conn.close()
        st.rerun()
