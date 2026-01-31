import streamlit as st
import pandas as pd
import sqlite3
import time
import cv2
import numpy as np
from datetime import datetime
from PIL import Image
import io

# ==========================================
# 1. CONFIGURATION ET STYLE CSS (ECHO-LIKE)
# ==========================================
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1c1f26; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .sidebar .sidebar-content { background-image: linear-gradient(#2e313d,#0e1117); }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #ff4b4b; color: white; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. GESTION DE LA BASE DE DONNÉES
# ==========================================
def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY,
                race TEXT,
                age_estimé TEXT,
                sexe TEXT,
                poids_naissance REAL,
                poids_10j REAL,
                poids_30j REAL,
                poids_70j REAL,
                h_garrot REAL,
                c_canon REAL,
                p_thoracique REAL,
                l_corps REAL,
                score_viande REAL,
                score_gras REAL,
                score_os REAL,
                date_enregistrement DATETIME
            )
        """)
        conn.commit()

# ==========================================
# 3. FONCTIONS TECHNIQUES (IA & CALCULS)
# ==========================================
def estimer_composition(canon, thorax, longueur):
    """Calcule le ratio Viande/Gras/Os selon la morphométrie"""
    if canon == 0: return 0, 0, 0
    os = round((canon * 2.15), 1)
    viande = round((thorax / 1.58), 1)
    gras = round(max(2.0, 100 - (os + viande)), 1)
    return viande, gras, os

def simuler_IA_scanner(image_bytes):
    """Simule l'analyse de contour et détection de points osseux"""
    time.sleep(2) # Simulation temps de calcul
    return {
        "hauteur": 74.5,
        "canon": 8.8,
        "thorax": 87.2,
        "longueur": 85.0,
        "confiance": 98.4
    }

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    
    # Chargement des données
    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- SIDEBAR (DASHBOARD ECHO) ---
    st.sidebar.title("🐏 EXPERT OVIN PRO")
    st.sidebar.markdown("_Système Intelligent d'Aide à la Décision_")
    
    menu = st.sidebar.selectbox("NAVIGATION", 
        ["📊 Tableau de Bord", "📸 Scanner Biométrique", "✍️ Saisie de Données", "🔧 Administration"])
    
    st.sidebar.divider()
    
    if not df.empty:
        st.sidebar.subheader("📈 État du Troupeau")
        col_s1, col_s2 = st.sidebar.columns(2)
        col_s1.metric("Têtes", len(df))
        col_s2.metric("Moy. Canon", f"{df['c_canon'].mean():.1f}")
        
        st.sidebar.divider()
        st.sidebar.subheader("🥩 Composition Tissulaire Moy.")
        v_moy, g_moy, o_moy = estimer_composition(df['c_canon'].mean(), df['p_thoracique'].mean(), df['l_corps'].mean())
        
        st.sidebar.write(f"Muscle: {v_moy}%")
        st.sidebar.progress(v_moy/100)
        st.sidebar.write(f"Os: {o_moy}%")
        st.sidebar.progress(o_moy/100)
        st.sidebar.write(f"Gras: {g_moy}%")
        st.sidebar.progress(g_moy/100)
    
    st.sidebar.divider()
    st.sidebar.info(f"Serveur Actif : {datetime.now().strftime('%H:%M:%S')}")

    # --- ONGLET 1 : TABLEAU DE BORD ---
    if menu == "📊 Tableau de Bord":
        st.title("📊 Tableau de Bord Analytique")
        
        if df.empty:
            st.warning("⚠️ Aucune donnée disponible. Veuillez effectuer un scan.")
            # Image de bienvenue/guide
            st.image("https://images.unsplash.com/photo-1484557918186-7b4e571d993c?auto=format&fit=crop&q=80&w=1000", caption="Station Ovine Connectée")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Effectif Total", len(df))
            c2.metric("Poids Sevrage (70j)", f"{df[df['poids_70j']>0]['poids_70j'].mean():.1f} kg")
            c3.metric("Indice Osseux", f"{df['c_canon'].mean():.1f} cm")
            c4.metric("Conformation", "Elite" if df['p_thoracique'].mean() > 85 else "Standard")

            st.divider()
            
            # Graphique de répartition
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.subheader("Répartition par Dentition")
                st.bar_chart(df['age_estimé'].value_counts())
            with col_g2:
                st.subheader("Courbe de Poids (Derniers 10)")
                st.line_chart(df[['poids_10j', 'poids_30j', 'poids_70j']].tail(10))

            st.subheader("📋 Registre Digital")
            st.dataframe(df.sort_values(by='date_enregistrement', ascending=False), use_container_width=True)

    # --- ONGLET 2 : SCANNER (IA & ÉTALON 1M) ---
    elif menu == "📸 Scanner Biométrique":
        st.title("📸 Station de Scan")
        
        tab1, tab2 = st.tabs(["🤖 Scanner IA (Auto)", "📏 Scanner Manuel (Étalon 1m)"])
        
        with tab1:
            st.markdown("### Analyse Automatique par Vision")
            img_file = st.camera_input("Capturer le profil de l'animal")
            if img_file:
                with st.spinner("Analyse du squelette en cours..."):
                    res = simuler_IA_scanner(img_file)
                    col_res_img, col_res_data = st.columns([1.5, 1])
                    with col_res_img:
                        st.image(img_file, caption=f"Cadrage validé à {res['confiance']}%")
                    with col_res_data:
                        st.metric("Tour de Canon (🦴)", f"{res['canon']} cm")
                        st.metric("Hauteur (📏)", f"{res['hauteur']} cm")
                        st.metric("Périmètre Thorax", f"{res['thorax']} cm")
                        if st.button("🚀 Transférer vers la fiche"):
                            st.session_state['scan_data'] = res
                            st.success("Données envoyées !")

        with tab2:
            st.markdown("### Calibration par Étalon")
            st.info("Placez l'animal à côté d'une règle de 100cm (1m).")
            ref_std = st.number_input("Référence Étalon (cm)", value=100.0)
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                h_manual = st.number_input("Hauteur Garrot (Mesurée)", value=70.0)
                c_manual = st.number_input("Tour de Canon (Mesuré)", value=8.5)
            with col_m2:
                t_manual = st.number_input("Périmètre Thorax (Mesuré)", value=82.0)
                l_manual = st.number_input("Longueur Corps (Mesurée)", value=80.0)
            
            if st.button("💾 Valider Mesures Manuelles"):
                st.session_state['scan_data'] = {"hauteur": h_manual, "canon": c_manual, "thorax": t_manual, "longueur": l_manual}
                st.success("Mesures mémorisées.")

    # --- ONGLET 3 : SAISIE ---
    elif menu == "✍️ Saisie de Données":
        st.title("✍️ Fiche d'Identification")
        sd = st.session_state.get('scan_data', {})
        
        with st.form("form_index"):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1: 
                id_ani = st.text_input("ID / N° Boucle *", help="Obligatoire")
            with col_f2:
                dent = st.selectbox("Dentition (Âge)", ["Lait (Agneau)", "2 Dents", "4 Dents", "6 Dents", "8 Dents", "Usée"])
            with col_f3:
                sx = st.radio("Sexe", ["Mâle", "Femelle"], horizontal=True)

            st.divider()
            st.subheader("⚖️ Suivi de Croissance (Poids en kg)")
            p_c1, p_c2, p_c3, p_c4 = st.columns(4)
            p_n = p_c1.number_input("Naissance", 0.0)
            p_10 = p_c2.number_input("10 Jours", 0.0)
            p_30 = p_c3.number_input("30 Jours", 0.0)
            p_70 = p_c4.number_input("70 Jours (Sevrage)", 0.0)

            st.divider()
            st.subheader("📏 Mensurations Importées")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            h_f = m_c1.number_input("Hauteur Garrot", value=float(sd.get('hauteur', 0.0)))
            c_f = m_c2.number_input("Tour de Canon", value=float(sd.get('canon', 0.0)))
            t_f = m_c3.number_input("Périmètre Thorax", value=float(sd.get('thorax', 0.0)))
            l_f = m_c4.number_input("Longueur Corps", value=float(sd.get('longueur', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER L'ANIMAL DANS LA BASE"):
                if id_ani:
                    v, g, o = estimer_composition(c_f, t_f, l_f)
                    with get_db_connection() as conn:
                        conn.execute("""INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (id_ani, "Ouled Djellal", dent, sx, p_n, p_10, p_30, p_70, h_f, c_f, t_f, l_f, v, g, o, datetime.now()))
                    st.success(f"Animal {id_ani} enregistré avec succès !")
                    st.balloons()
                else:
                    st.error("L'ID de l'animal est requis.")

    # --- ONGLET 4 : ADMIN PRO ---
    elif menu == "🔧 Administration":
        st.title("🔧 Centre de Contrôle")
        
        st.subheader("📥 Export & Data")
        col_ad1, col_ad2 = st.columns(2)
        with col_ad1:
            st.write("Télécharger la base complète")
            if not df.empty:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Télécharger l'inventaire CSV", csv, "base_ovins.csv", "text/csv")
        
        with col_ad2:
            st.write("Gestion des sauvegardes")
            st.file_uploader("Importer un fichier .csv externe", type=['csv'])

        st.divider()
        st.subheader("⚠️ Maintenance")
        with st.expander("Zone de danger (Réinitialisation)"):
            st.warning("Cette action supprimera tous les enregistrements de manière irréversible.")
            confirm = st.checkbox("Je confirme vouloir vider la base de données.")
            if st.button("🗑️ SUPPRIMER TOUT", disabled=not confirm):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM beliers")
                st.success("Base de données réinitialisée.")
                st.rerun()

if __name__ == "__main__":
    main()
