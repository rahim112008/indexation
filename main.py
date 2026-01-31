import streamlit as st
import pandas as pd
import sqlite3
import time
import numpy as np
from datetime import datetime

# =================================================================
# 1. CONFIGURATION ET STYLE VISUEL (ECHO-LIKE INTERFACE)
# =================================================================
st.set_page_config(page_title="Expert Ovin Pro v2.8", layout="wide", page_icon="🐏")

def apply_echo_style():
    st.markdown("""
        <style>
        /* Style Interface Sombre Haute Précision */
        .main { background-color: #050505; color: #00FF41; } /* Vert Matrix/Echo */
        .sidebar .sidebar-content { background-color: #111; border-right: 1px solid #00FF41; }
        .stMetric { background-color: #111; border: 1px solid #00FF41; border-radius: 5px; padding: 10px; }
        
        /* Personnalisation des barres de progression pour l'Echo */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #00FF41, #008F11);
        }
        
        /* Design des cartes Echo-like dans la sidebar */
        .echo-card {
            background-color: #1a1a1a;
            border-left: 5px solid #00FF41;
            padding: 10px;
            margin-bottom: 10px;
            font-family: 'Courier New', Courier, monospace;
        }
        </style>
        """, unsafe_allow_html=True)

apply_echo_style()

# =================================================================
# 2. LOGIQUE DE PRÉDICTION TISSULAIRE (SIMULATION ÉCHO)
# =================================================================
def predict_tissues_echo(canon, thorax, longueur, poids):
    """
    Algorithme de simulation échographique :
    - L'os est extrait du ratio Canon/Poids
    - Le muscle (viande) est extrait du volume Thoracique
    - Le gras est calculé par l'indice de couverture
    """
    if canon == 0 or thorax == 0:
        return 0, 0, 0
    
    # Constantes biométriques pour la race Ouled Djellal
    indice_os = (canon * 2.15)
    indice_muscle = (thorax / 1.52)
    
    # Calcul des pourcentages
    pct_os = round(indice_os, 1)
    pct_viande = round(indice_muscle, 1)
    pct_gras = round(max(2.0, 100 - (pct_os + pct_viande)), 1)
    
    return pct_viande, pct_gras, pct_os

# =================================================================
# 3. GESTION DE LA BASE DE DONNÉES
# =================================================================
def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, age TEXT, sexe TEXT,
                pn REAL, p10 REAL, p30 REAL, p70 REAL,
                h REAL, c REAL, t REAL, l REAL,
                viande REAL, gras REAL, os REAL,
                gmq REAL, date_reg DATETIME
            )
        """)
        conn.commit()

# =================================================================
# 4. INTERFACE PRINCIPALE
# =================================================================
def main():
    init_db()
    
    # Chargement des données
    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- SIDEBAR : FONCTION ECHO-LIKE ---
    st.sidebar.title("📟 ECHO-SCAN V1")
    st.sidebar.markdown("---")
    
    if not df.empty:
        st.sidebar.subheader("🎯 Estimation Tissulaire (Moy)")
        
        # Récupération des dernières moyennes pour l'écho
        avg_v = df['viande'].mean()
        avg_g = df['gras'].mean()
        avg_o = df['os'].mean()

        # Affichage style "Écran de contrôle"
        st.sidebar.markdown(f"""
        <div class="echo-card">
            <span style="color:#00FF41">▶ MUSCLE (VIANDE)</span><br>
            <b style="font-size:20px">{avg_v:.1f} %</b>
        </div>
        """, unsafe_allow_html=True)
        st.sidebar.progress(avg_v/100)

        st.sidebar.markdown(f"""
        <div class="echo-card">
            <span style="color:#00FF41">▶ STRUCTURE OSSEUSE</span><br>
            <b style="font-size:20px">{avg_o:.1f} %</b>
        </div>
        """, unsafe_allow_html=True)
        st.sidebar.progress(avg_o/100)

        st.sidebar.markdown(f"""
        <div class="echo-card">
            <span style="color:#00FF41">▶ ADIPOSITÉ (GRAS)</span><br>
            <b style="font-size:20px">{avg_g:.1f} %</b>
        </div>
        """, unsafe_allow_html=True)
        st.sidebar.progress(avg_g/100)
    else:
        st.sidebar.warning("Echo : En attente de données...")

    st.sidebar.markdown("---")
    menu = st.sidebar.radio("MENU", ["📊 Dashboard", "📸 Scanner", "✍️ Saisie/GMQ", "🔧 Admin"])

    # --- CONTENU DES ONGLETS ---
    if menu == "📊 Dashboard":
        st.title("📊 Analyse du Troupeau")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Effectif", len(df))
            c2.metric("GMQ Moyen", f"{df['gmq'].mean():.0f} g/j")
            c3.metric("Rendement Estimé", f"{df['viande'].mean():.1f}%")
            st.divider()
            st.dataframe(df, use_container_width=True)

    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan")
        img = st.camera_input("Scanner")
        if img:
            st.success("Analyse Biomtrique en cours...")
            # Simulation des résultats du scanner
            res = {"h": 74.0, "c": 8.8, "t": 87.0, "l": 85.0}
            st.session_state['last_scan'] = res
            st.json(res)

    elif menu == "✍️ Saisie/GMQ":
        st.title("✍️ Saisie & Calculs")
        scan = st.session_state.get('last_scan', {})
        
        with st.form("form_global"):
            col1, col2 = st.columns(2)
            id_a = col1.text_input("ID Animal")
            p70 = col2.number_input("Poids au Sevrage (kg)", value=25.0)
            
            # Récupération des données scan
            h = st.number_input("Hauteur", value=float(scan.get('h', 0.0)))
            c = st.number_input("Canon", value=float(scan.get('c', 0.0)))
            t = st.number_input("Thorax", value=float(scan.get('t', 0.0)))
            l = st.number_input("Longueur", value=float(scan.get('l', 0.0)))
            
            if st.form_submit_button("💾 ANALYSER & SAUVEGARDER"):
                v, g, o = predict_tissues_echo(c, t, l, p70)
                gmq = ((p70 - 4.0) / 70) * 1000 # Calcul simplifié
                
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (id_a, "Lait", "Mâle", 4.0, 8.0, 15.0, p70, h, c, t, l, v, g, o, gmq, datetime.now()))
                st.success("Analyse terminée et enregistrée !")
                st.rerun()

    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🗑️ Vider la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
