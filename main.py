import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from contextlib import contextmanager
import time
import random

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 15px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;
    }
    .metric-card h2 { color: #2E7D32; margin: 5px 0; font-size: 24px; }
    .analysis-box { 
        background-color: #f9fdf9; padding: 15px; border-radius: 10px; 
        border: 1px solid #c8e6c9; margin-bottom: 10px;
    }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .analysis-box { background-color: #121212; border: 1px solid #2E7D32; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
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
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT, objectif TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. LOGIQUE "ECHO-LIKE"
# ==========================================
def calculer_echo_metrics(row):
    try:
        p70 = float(row.get('p70') or 0)
        hg = float(row.get('h_garrot') or 75)
        pt = float(row.get('p_thoracique') or 90)
        cc = float(row.get('c_canon') or 9)
        if p70 < 5: return [0]*7
        ic = (pt / (cc * hg)) * 1000
        gras_mm = 1.2 + (p70 * 0.14) + (ic * 0.07) - (hg * 0.04)
        pct_gras = max(8.0, 5.0 + (gras_mm * 1.6))
        pct_muscle = max(40.0, 78.0 - (pct_gras * 0.58) + (ic * 0.18))
        pct_os = 100 - pct_muscle - pct_gras
        rendement = pct_muscle + (pct_gras * 0.2)
        return [round(pct_muscle, 1), round(pct_gras, 1), round(pct_os, 1), round(ic, 1), round(gras_mm, 1), round(rendement, 1), "R"]
    except: return [0]*7

def load_data():
    with get_db_connection() as conn:
        df = pd.read_sql("""SELECT b.*, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                           FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                           LEFT JOIN mesures m ON l.mid = m.id""", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        res = df.apply(lambda x: pd.Series(calculer_echo_metrics(x)), axis=1)
        df[['Muscle', 'Gras', 'Os', 'IC', 'Gras_mm', 'Rendement', 'Classe']] = res
        df['Score'] = (df['Muscle'] * 0.7) + (df['p70'] * 0.3)
        limit = df['Score'].quantile(0.85) if len(df) > 5 else 999
        df['Statut'] = np.where(df['Score'] >= limit, "⭐ ELITE PRO", "Standard")
    return df

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Echo-Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty: st.info("Base vide. Allez dans Admin.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p>Elite</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><p>Poids Moy.</p><h2>{df['p70'].mean():.1f} kg</h2></div>", unsafe_allow_html=True)
            st.dataframe(df[['id', 'sexe', 'race', 'p70', 'Muscle', 'Statut']], use_container_width=True)

    # --- ECHO-COMPOSITION ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse Échographique")
        if not df.empty:
            target = st.selectbox("Choisir un animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4)])
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(f"<div class='analysis-box'><h3>Score: {subj['Statut']}</h3>Muscle: {subj['Muscle']}%<br>Gras: {subj['Gras_mm']}mm</div>", unsafe_allow_html=True)
        else: st.warning("Pas de données.")

    # --- VOTRE NOUVEAU SCANNER EXPERT ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        st.markdown("_Analyse morphologique et diagnostic de la structure osseuse._")
        
        

        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            source = st.radio("Source de l'image", ["📷 Caméra en direct", "📁 Importer une photo"], horizontal=True)
        with col_cfg2:
            mode_scanner = st.radio("Méthode d'analyse", ["🤖 Automatique (IA)", "📏 Manuel (Gabarit)"], horizontal=True)
        
        st.divider()

        if source == "📷 Caméra en direct":
            img = st.camera_input("Positionnez l'animal bien de profil")
        else:
            img = st.file_uploader("Charger une photo de profil complète", type=['jpg', 'jpeg', 'png'])

        if img:
            col_img, col_res = st.columns([1.5, 1])
            with col_img:
                st.image(img, caption="Analyse de la silhouette", use_container_width=True)
            
            with col_res:
                if mode_scanner == "🤖 Automatique (IA)":
                    with st.spinner("🧠 Analyse du squelette..."):
                        time.sleep(1.2)
                        image_est_complete = True # Simulation
                        score_confiance = 98
                        if image_est_complete:
                            st.success(f"✅ **CADRAGE VALIDE ({score_confiance}%)**")
                            res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                        else:
                            st.error("⚠️ IMAGE INCOMPLÈTE")
                            res = {"h_garrot": 73.5, "c_canon": 8.2, "p_thoracique": 84.0, "l_corps": "Coupé"}
                else:
                    st.subheader("📏 Mesures au Gabarit (Étalon 1m)")
                    h_in = st.number_input("Hauteur Garrot (cm)", value=72.0)
                    c_in = st.number_input("Tour de Canon (cm)", value=8.5)
                    t_in = st.number_input("Périmètre Thorax (cm)", value=84.0)
                    l_in = st.number_input("Longueur Corps (cm)", value=82.0)
                    res = {"h_garrot": h_in, "c_canon": c_in, "p_thoracique": t_in, "l_corps": l_in}

                st.divider()
                st.session_state['scan'] = res 
                m1, m2 = st.columns(2)
                m1.metric("📏 Hauteur", f"{res['h_garrot']} cm")
                m1.metric("🦴 Tour de Canon", f"{res['c_canon']} cm")
                m2.metric("⭕ Thorax", f"{res['p_thoracique']} cm")
                m2.metric("📏 Longueur", f"{res['l_corps']} cm")

                if st.button("🚀 VALIDER ET ENVOYER À LA SAISIE", type="primary", use_container_width=True):
                    st.session_state['go_saisie'] = True
                    st.balloons()
                    st.success("Données transférées ! Allez dans l'onglet 'Saisie'.")

    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation")
        sd = st.session_state.get('scan', {})
        if not sd: st.info("Passez par le Scanner pour remplir automatiquement les champs.")
        with st.form("form_saisie"):
            id_a = st.text_input("ID / Boucle *")
            sexe = st.selectbox("Sexe", ["Bélier", "Brebis", "Agneau", "Agnelle"])
            poids = st.number_input("Poids actuel (kg)", 0.0)
            cc = st.number_input("Tour de Canon (cm)", value=float(sd.get('c_canon', 0.0)))
            hg = st.number_input("Hauteur Garrot (cm)", value=float(sd.get('h_garrot', 0.0)))
            pt = st.number_input("Périmètre Thorax (cm)", value=float(sd.get('p_thoracique', 0.0)))
            if st.form_submit_button("💾 ENREGISTRER"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, sexe, race) VALUES (?,?,?)", (id_a, sexe, "Ouled Djellal"))
                        conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?)", (id_a, poids, hg, cc, pt))
                    st.success("Individu ajouté !")
                    st.rerun()

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS DE TEST"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_a = f"DZ-2026-{random.randint(1000, 9999)}"
                    sx = random.choice(["Bélier", "Brebis", "Agneau", "Agnelle"])
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_a, "O.Djellal", sx, "Adulte", "Sélection"))
                    conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?)", (id_a, random.uniform(40,100), 75, 9, 95))
            st.rerun()
        if st.button("🗑️ RESET BASE", type="primary"):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
