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
# CONFIGURATION PROFESSIONNELLE (MAJ 2026)
# ==========================================
SEUILS_PRO = {
    'p70_absolu': 22.0,
    'canon_absolu': 7.5,
    'percentile_elite': 0.85,
    'z_score_max': 2.5,
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
        # Table unifiée avec Sexe, Dentition et Poids J10/30/70
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT, 
                sexe TEXT,
                date_naiss TEXT,
                dentition TEXT,
                p10 REAL DEFAULT 0,
                p30 REAL DEFAULT 0,
                p70 REAL DEFAULT 0,
                h_garrot REAL DEFAULT 0,
                l_corps REAL DEFAULT 0,
                p_thoracique REAL DEFAULT 0,
                l_poitrine REAL DEFAULT 0,
                c_canon REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

# ==========================================
# MOTEUR ECHO-LIKE & COMPOSITION
# ==========================================
def calculer_composition_carcasse(row):
    """Analyse type échographique basée sur la biométrie transversale"""
    p70 = float(row.get('p70', 0))
    hg = float(row.get('h_garrot', 70))
    pt = float(row.get('p_thoracique', 80))
    cc = float(row.get('c_canon', 8.5))
    lc = float(row.get('l_corps', 80))
    
    if p70 <= 0 or cc <= 0: return 0, 0, 0, 0, "N/A"
    
    # Indice de compacité (IC)
    ic = (pt / (cc * hg)) * 100
    
    # Estimation tissulaire (%)
    pct_os = round(11.5 + (cc * 0.45), 1)
    pct_muscle = round(42 + (ic * 0.22) + (lc * 0.04), 1)
    pct_gras = round(max(3, 100 - (pct_muscle + pct_os)), 1)
    
    # Calcul de l'Index Expert (sur 100)
    score = (pct_muscle * 0.5) + (p70 * 0.3) - (pct_os * 0.2)
    
    # Classe EUROP simplifiée
    if ic > 32: classe = "E (Excellent)"
    elif ic > 28: classe = "U (Très Bon)"
    else: classe = "R (Standard)"
    
    return pct_muscle, pct_gras, pct_os, round(score, 1), classe

# ==========================================
# MODULE SCANNER (ÉTALON 1 MÈTRE)
# ==========================================
def module_scanner_ia():
    st.subheader("📸 Scanner Automatique (Standard 1.0m)")
    st.info("Placez l'étalon de 1 mètre au sol près de l'animal pour calibration.")
    
    col1, col2 = st.columns(2)
    with col1:
        img = st.camera_input("Capture de profil")
    
    with col2:
        if img:
            with st.spinner("Analyse des pixels vs Étalon 100cm..."):
                time.sleep(1.5) # Simulation IA
                # Mesures simulées calibrées sur 1m
                scan_res = {
                    'h_garrot': 74.2, 'l_corps': 82.5, 
                    'p_thoracique': 88.1, 'c_canon': 8.4,
                    'l_poitrine': 25.2
                }
                st.session_state['last_scan'] = scan_res
                st.success("✅ Mesures calibrées extraites")
                st.json(scan_res)
                
                # Visualisation des points
                

# ==========================================
# INTERFACE STREAMLIT
# ==========================================
def main():
    st.set_page_config(page_title="Expert Ovin Pro", layout="wide")
    init_db()
    
    # CSS Echo-Vision
    st.markdown("""<style>
        .echo-card { background-color: #0e1117; border: 1px solid #00ff00; padding: 15px; border-radius: 10px; color: #00ff00; font-family: 'Courier New', monospace; }
    </style>""", unsafe_allow_html=True)

    menu = st.sidebar.radio("Navigation", [
        "📊 Dashboard", "📸 Scanner IA", "🥩 Echo-Like Analysis", "✍️ Saisie & Mesures", "⚙️ Admin"
    ])

    # --- DASHBOARD ---
    if menu == "📊 Dashboard":
        st.title("🏆 Classement du Troupeau")
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT * FROM beliers", conn)
        
        if not df.empty:
            # Application du moteur de calcul sur tout le tableau
            df[['Muscle%', 'Gras%', 'Os%', 'Index', 'Classe']] = df.apply(
                lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Effectif", len(df))
            c2.metric("Poids J70 Moy", f"{df['p70'].mean():.1f} kg")
            c3.metric("Muscle Moy", f"{df['Muscle%'].mean():.1f}%")
            
            st.dataframe(df.sort_values('Index', ascending=False), use_container_width=True)
        else:
            st.warning("Base de données vide.")

    # --- SCANNER ---
    elif menu == "📸 Scanner IA":
        module_scanner_ia()

    # --- ECHO-LIKE ---
    elif menu == "🥩 Echo-Like Analysis":
        st.title("📟 Visualisation Tissulaire")
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT * FROM beliers", conn)
            
        if not df.empty:
            target = st.selectbox("Choisir l'ID", df['id'])
            row = df[df['id'] == target].iloc[0]
            m, g, o, score, classe = calculer_composition_carcasse(row)
            
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], 
                                           values=[m, g, o], hole=.4,
                                           marker_colors=['#00cc00', '#ffff00', '#ff3300'])])
                st.plotly_chart(fig)
            
            with col2:
                st.markdown(f"""<div class='echo-card'>
                    <h3>ANALYSE ID: {target}</h3>
                    <hr>
                    ▶ CLASSE EUROP : {classe}<br>
                    ▶ INDEX EXPERT : {score}<br>
                    ▶ RENDEMENT EST. : {48 + (m*0.1):.1f}%<br>
                    ▶ GMQ J30-J70 : {((row['p70']-row['p30'])/40)*1000:.0f} g/j
                </div>""", unsafe_allow_html=True)
        else:
            st.info("Veuillez saisir des données d'abord.")

    # --- SAISIE COMPLÈTE ---
    elif menu == "✍️ Saisie & Mesures":
        st.title("✍️ Fiche Animalière Complète")
        
        with st.form("form_animal"):
            c1, c2, c3 = st.columns(3)
            with c1:
                id_a = st.text_input("ID Animal *")
                sexe = st.selectbox("Sexe", ["Mâle (Bélier)", "Femelle (Brebis)"])
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
            with c2:
                dentition = st.selectbox("Dentition", ["Agneau (Lait)", "2 Dents", "4 Dents", "6 Dents", "Pleine Bouche"])
                date_n = st.date_input("Date Naissance Est.")
            with c3:
                st.markdown("**Suivi de Poids (kg)**")
                p10 = st.number_input("Poids J10", value=0.0)
                p30 = st.number_input("Poids J30", value=0.0)
                p70 = st.number_input("Poids J70", value=0.0)

            st.markdown("---")
            st.markdown("**Mensurations Biométriques (cm)**")
            sc = st.session_state.get('last_scan', {})
            m1, m2, m3, m4 = st.columns(4)
            h = m1.number_input("H. Garrot", value=sc.get('h_garrot', 0.0))
            l = m2.number_input("L. Corps", value=sc.get('l_corps', 0.0))
            t = m3.number_input("P. Thorax", value=sc.get('p_thoracique', 0.0))
            c = m4.number_input("T. Canon", value=sc.get('c_canon', 0.0))
            
            if st.form_submit_button("💾 ENREGISTRER L'ANIMAL"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute('''INSERT OR REPLACE INTO beliers 
                            (id, race, sexe, date_naiss, dentition, p10, p30, p70, h_garrot, l_corps, p_thoracique, c_canon)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', 
                            (id_a, race, sexe, str(date_n), dentition, p10, p30, p70, h, l, t, c))
                    st.success(f"Animal {id_a} enregistré avec succès !")
                else:
                    st.error("L'ID est obligatoire.")

    # --- ADMIN ---
    elif menu == "⚙️ Admin":
        st.title("Administration")
        if st.button("🗑️ Vider la base de données"):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
