import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

# ==========================================
# CONFIGURATION PROFESSIONNELLE & SEUILS
# ==========================================
SEUILS_PRO = {
    'p70_absolu': 22.0,
    'canon_absolu': 7.5,
    'percentile_elite': 0.85,
    'z_score_max': 3.0,
    'ratio_p70_canon_max': 8.0
}

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# GESTION DE LA BASE DE DONNÉES
# ==========================================
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
                id TEXT PRIMARY KEY, 
                race TEXT, 
                date_naiss TEXT, 
                dentition TEXT,
                p10 REAL, p30 REAL, p70 REAL,
                h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                pct_muscle REAL, pct_gras REAL, pct_os REAL,
                gmq REAL, index_final REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

# ==========================================
# MOTEUR DE CALCULS BIOMÉTRIQUES (ECHO-LIKE)
# ==========================================
def calculer_performance(row):
    """Calcule le GMQ et les indices de carcasse (Simule une échographie)"""
    try:
        p70 = float(row.get('p70', 0))
        p30 = float(row.get('p30', 0))
        pt = float(row.get('p_thoracique', 0))
        cc = float(row.get('c_canon', 0))
        hg = float(row.get('h_garrot', 0))
        
        if p70 <= 0 or cc <= 0: return 0, 0, 0, 0, 0
        
        # 1. GMQ (Gain Moyen Quotidien 30-70j)
        gmq = ((p70 - p30) / 40) * 1000 if p30 > 0 else 0
        
        # 2. Composition Tissulaire (Algorithme Hammond modifié)
        # Indice de compacité
        ic = (pt / (cc * hg)) * 100 if hg > 0 else 0
        
        pct_os = round(12 + (cc * 0.5), 1)
        pct_muscle = round(45 + (ic * 0.2), 1)
        pct_gras = round(max(5, 100 - (pct_muscle + pct_os)), 1)
        
        # 3. Index de sélection
        index_val = (pct_muscle * 0.6) + (gmq / 10) - (pct_os * 0.2)
        
        return round(gmq, 1), pct_muscle, pct_gras, pct_os, round(index_val, 1)
    except:
        return 0, 0, 0, 0, 0

# ==========================================
# INTERFACE STREAMLIT
# ==========================================
def main():
    st.set_page_config(page_title="Expert Ovin Pro", layout="wide")
    init_db()
    
    # --- Sidebar Style Echo-Scan ---
    st.sidebar.title("🐏 EXPERT OVIN PRO")
    st.sidebar.markdown("---")
    
    menu = st.sidebar.radio("Navigation", [
        "📊 Dashboard", 
        "📸 Scanner Biométrique", 
        "📟 Echo-Scan (Composition)", 
        "✍️ Saisie & GMQ",
        "⚙️ Configuration"
    ])

    # Chargement des données
    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- 1. DASHBOARD ---
    if menu == "📊 Dashboard":
        st.title("📊 Tableau de Bord des Performances")
        if df.empty:
            st.info("Aucune donnée enregistrée.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Effectif Total", len(df))
            col2.metric("GMQ Moyen", f"{df['gmq'].mean():.0f} g/j")
            col3.metric("Muscle Moyen", f"{df['pct_muscle'].mean():.1f} %")
            col4.metric("Élite (>85 pts)", len(df[df['index_final'] > 85]))

            st.divider()
            st.subheader("Classement des reproducteurs")
            st.dataframe(df.sort_values('index_final', ascending=False), use_container_width=True)

    # --- 2. SCANNER AVEC ÉTALON 1M ---
    elif menu == "📸 Scanner Biométrique":
        st.title("📸 Analyse par Image (Standard 1 mètre)")
        st.write("Placez l'étalon de **100 cm** à côté de l'animal pour la calibration.")
        
        img_file = st.camera_input("Scanner l'animal")
        
        if img_file:
            with st.spinner("Analyse des pixels et calibration..."):
                time.sleep(2) # Simulation traitement image
                # Simulation de conversion Pixel -> CM via l'étalon
                st.success("Calibration réussie (Étalon 1m détecté)")
                
                col1, col2 = st.columns(2)
                with col1:
                    h_est = st.number_input("Hauteur Garrot (estimée)", value=72.5)
                    l_est = st.number_input("Longueur Corps (estimée)", value=84.0)
                with col2:
                    t_est = st.number_input("Périmètre Thoracique (estimé)", value=88.0)
                    c_est = st.number_input("Diamètre Canon (estimé)", value=8.2)
                
                if st.button("Valider les mesures du Scan"):
                    st.session_state['scan_data'] = {'h':h_est, 'l':l_est, 't':t_est, 'c':c_est}
                    st.toast("Mesures envoyées au module Echo-Scan")

    # --- 3. ECHO-SCAN (COMPOSITION) ---
    elif menu == "📟 Echo-Scan (Composition)":
        st.title("📟 Estimation de la Carcasse (Echo-Vision)")
        
        if df.empty:
            st.warning("Veuillez d'abord saisir des données.")
        else:
            selected_id = st.selectbox("Sélectionner l'animal à analyser", df['id'].tolist())
            animal = df[df['id'] == selected_id].iloc[0]
            
            c1, c2 = st.columns([1, 2])
            
            with c1:
                st.subheader("Ratios Tissulaires")
                fig = go.Figure(go.Pie(
                    labels=['Viande (Muscle)', 'Gras', 'Os'],
                    values=[animal['pct_muscle'], animal['pct_gras'], animal['pct_os']],
                    hole=.4,
                    marker_colors=['#2ecc71', '#f1c40f', '#e74c3c']
                ))
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                st.subheader("Écran de Contrôle Échographique")
                st.write(f"**ID:** {selected_id} | **Race:** {animal['race']}")
                
                # Jauges de performance
                st.write("Densité Musculaire")
                st.progress(int(animal['pct_muscle']))
                
                st.write("Indice de Gras")
                st.progress(int(animal['pct_gras']))
                
                st.metric("Score de Sélection", f"{animal['index_final']} / 100")

    # --- 4. SAISIE & GMQ ---
    elif menu == "✍️ Saisie & GMQ":
        st.title("✍️ Enregistrement & Calcul GMQ")
        
        with st.form("form_saisie"):
            col1, col2 = st.columns(2)
            with col1:
                id_a = st.text_input("ID Animal")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
                p30 = st.number_input("Poids à 30j (kg)", min_value=0.0)
                p70 = st.number_input("Poids à 70j (kg)", min_value=0.0)
            
            with col2:
                # Récupération auto si scan fait
                sd = st.session_state.get('scan_data', {})
                h = st.number_input("Hauteur Garrot (cm)", value=sd.get('h', 0.0))
                c = st.number_input("C. Canon (cm)", value=sd.get('c', 0.0))
                t = st.number_input("P. Thoracique (cm)", value=sd.get('t', 0.0))
                l = st.number_input("Longueur Corps (cm)", value=sd.get('l', 0.0))

            if st.form_submit_button("Calculer & Sauvegarder"):
                gmq, m, g, o, idx = calculer_performance({'p30':p30, 'p70':p70, 'p_thoracique':t, 'c_canon':c, 'h_garrot':h})
                
                with get_db_connection() as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO beliers 
                        (id, race, p30, p70, h_garrot, l_corps, p_thoracique, c_canon, pct_muscle, pct_gras, pct_os, gmq, index_final)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ''', (id_a, race, p30, p70, h, l, t, c, m, g, o, gmq, idx))
                
                st.success(f"Enregistré ! GMQ: {gmq}g/j | Muscle: {m}%")
                time.sleep(1)
                st.rerun()

    # --- 5. CONFIGURATION ---
    elif menu == "⚙️ Configuration":
        st.title("⚙️ Paramètres Système")
        if st.button("Vider toute la base de données"):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM beliers")
            st.warning("Base de données vidée.")
            st.rerun()

if __name__ == "__main__":
    main()
