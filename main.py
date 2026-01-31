import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
import time
from PIL import Image

# ==========================================
# CONFIGURATION & BASE DE DONNÉES
# ==========================================
DB_NAME = "expert_ovin_pro.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=20)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, race TEXT, sexe TEXT, date_naiss TEXT, dentition TEXT,
                p10 REAL, p30 REAL, p70 REAL,
                h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                pct_muscle REAL, pct_gras REAL, index_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

# ==========================================
# MOTEUR DE SCANNER IA (LOGIQUE DE CALIBRATION)
# ==========================================
def simuler_analyse_ia(image_file, methode="Upload"):
    """
    Simule l'analyse de l'image. 
    L'IA cherche l'étalon de 100cm pour calibrer les pixels.
    """
    with st.spinner(f"Analyse du fichier via {methode}... Détection de l'étalon 1m"):
        time.sleep(2) # Simulation du temps de calcul IA
        
        # Ici l'algorithme calcule : Ratio = 100cm / (nombre de pixels de l'étalon)
        # Puis multiplie les segments détectés par ce ratio.
        mesures = {
            'h_garrot': round(72.5 + np.random.uniform(-1, 1), 1),
            'l_corps': round(84.0 + np.random.uniform(-1, 1), 1),
            'p_thoracique': round(88.5 + np.random.uniform(-1, 1), 1),
            'c_canon': round(8.2 + np.random.uniform(-0.2, 0.2), 1)
        }
        return mesures

# ==========================================
# INTERFACE STREAMLIT
# ==========================================
def main():
    st.set_page_config(page_title="Expert Ovin Pro", layout="wide")
    init_db()
    
    st.sidebar.title("🐏 Expert Selector")
    menu = st.sidebar.radio("Navigation", [
        "📊 Dashboard", 
        "📸 Scanner IA (Direct/Fichier)", 
        "📟 Echo-Like Analysis", 
        "✍️ Saisie Manuelle"
    ])

    # --- MODULE SCANNER (AVEC IMPORT DE FICHIER) ---
    if menu == "📸 Scanner IA (Direct/Fichier)":
        st.title("📸 Scanner Morphologique IA")
        st.markdown("""> **Standard de mesure :** L'animal doit être de profil avec l'étalon de **1 mètre** visible au sol.""")
        
        tab1, tab2 = st.tabs(["📁 Importer un fichier", "📷 Prendre une photo"])
        
        source_image = None
        methode = ""

        with tab1:
            uploaded_file = st.file_uploader("Choisir une image d'animal (JPG/PNG)", type=['jpg', 'jpeg', 'png'])
            if uploaded_file:
                source_image = uploaded_file
                methode = "Fichier"

        with tab2:
            camera_file = st.camera_input("Scanner en direct")
            if camera_file:
                source_image = camera_file
                methode = "Caméra"

        if source_image:
            st.image(source_image, caption="Image prête pour analyse", width=400)
            
            if st.button("🚀 LANCER L'ANALYSE BIOMÉTRIQUE"):
                res = simuler_analyse_ia(source_image, methode)
                st.session_state['last_scan'] = res
                
                st.success("✅ Analyse terminée avec succès !")
                
                # Affichage des résultats du scanner
                cols = st.columns(4)
                cols[0].metric("H. Garrot", f"{res['h_garrot']} cm")
                cols[1].metric("L. Corps", f"{res['l_corps']} cm")
                cols[2].metric("P. Thorax", f"{res['p_thoracique']} cm")
                cols[3].metric("Tour Canon", f"{res['c_canon']} cm")
                
                
                
                if st.button("📝 Transférer ces mesures vers la fiche"):
                    st.info("Mesures mémorisées. Allez dans 'Saisie Manuelle' pour compléter l'ID et les poids.")

    # --- MODULE SAISIE (RÉCUPÈRE LES DONNÉES DU SCANNER) ---
    elif menu == "✍️ Saisie Manuelle":
        st.title("✍️ Enregistrement de l'Animal")
        
        # Récupération des mesures du scanner si elles existent
        scan = st.session_state.get('last_scan', {})
        
        with st.form("form_complet"):
            c1, c2 = st.columns(2)
            with c1:
                id_a = st.text_input("ID de l'animal *")
                sexe = st.selectbox("Sexe", ["Bélier", "Brebis"])
                dentition = st.selectbox("Dentition", ["Lait", "2 Dents", "4 Dents", "6 Dents", "Pleine Bouche"])
            with c2:
                p10 = st.number_input("Poids J10 (kg)", value=0.0)
                p30 = st.number_input("Poids J30 (kg)", value=0.0)
                p70 = st.number_input("Poids J70 (kg)", value=0.0)
            
            st.subheader("Mensurations (Remplies par scanner)")
            m1, m2, m3, m4 = st.columns(4)
            h = m1.number_input("H. Garrot (cm)", value=scan.get('h_garrot', 0.0))
            l = m2.number_input("L. Corps (cm)", value=scan.get('l_corps', 0.0))
            t = m3.number_input("P. Thorax (cm)", value=scan.get('p_thoracique', 0.0))
            c = m4.number_input("T. Canon (cm)", value=scan.get('c_canon', 0.0))
            
            if st.form_submit_button("💾 SAUVEGARDER DANS LA BASE"):
                if id_a:
                    # Calcul rapide Echo-like pour le stockage
                    muscle = (t / (c * h)) * 10
                    with get_db_connection() as conn:
                        conn.execute('''INSERT OR REPLACE INTO beliers 
                            (id, sexe, dentition, p10, p30, p70, h_garrot, l_corps, p_thoracique, c_canon, pct_muscle)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)''', 
                            (id_a, sexe, dentition, p10, p30, p70, h, l, t, c, muscle))
                    st.success(f"Animal {id_a} enregistré.")
                else:
                    st.error("L'ID est obligatoire.")

    # --- AUTRES MODULES (DASHBOARD & ECHO) ---
    elif menu == "📊 Dashboard":
        st.title("📊 Performances du Troupeau")
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT * FROM beliers", conn)
        if not df.empty:
            st.dataframe(df)
            fig = px.bar(df, x='id', y='p70', title="Poids à J70 par Animal", color='pct_muscle')
            st.plotly_chart(fig)
        else:
            st.info("Aucune donnée enregistrée.")

    elif menu == "📟 Echo-Like Analysis":
        st.title("📟 Simulation Échographique")
        st.info("Sélectionnez un animal dans le dashboard pour voir sa composition.")

if __name__ == "__main__":
    main()
