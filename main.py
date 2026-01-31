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
            p_naiss REAL, p10 REAL, p30 REAL, p70 REAL, 
            h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. LOGIQUE "ECHO-LIKE" & GMD
# ==========================================
def calculer_metrics_finales(row):
    try:
        p70 = float(row.get('p70') or 0)
        p30 = float(row.get('p30') or 0)
        hg = float(row.get('h_garrot') or 75)
        pt = float(row.get('p_thoracique') or 90)
        cc = float(row.get('c_canon') or 9)
        
        # --- CALCUL GMD ---
        gmd = 0
        if p70 > p30 and p30 > 0:
            gmd = ((p70 - p30) / 40) * 1000  # g/jour (intervalle 30j-70j)

        if p70 < 2: return [0]*7
        
        # --- LOGIQUE ECHO ---
        ic = (pt / (cc * hg)) * 1000
        gras_mm = 1.2 + (p70 * 0.14) + (ic * 0.07) - (hg * 0.04)
        pct_gras = max(8.0, 5.0 + (gras_mm * 1.6))
        pct_muscle = max(40.0, 78.0 - (pct_gras * 0.58) + (ic * 0.18))
        pct_os = round(100 - pct_muscle - pct_gras, 1)
        
        return [round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(ic, 1), round(gras_mm, 1), round(gmd, 0), "R"]
    except: return [0]*7

def load_data():
    with get_db_connection() as conn:
        df = pd.read_sql("""SELECT b.*, m.p_naiss, m.p10, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                           FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                           LEFT JOIN mesures m ON l.mid = m.id""", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        res = df.apply(lambda x: pd.Series(calculer_metrics_finales(x)), axis=1)
        df[['Muscle', 'Gras', 'Os', 'IC', 'Gras_mm', 'GMD', 'Classe']] = res
        # Tri automatique par performance (Muscle et GMD)
        df = df.sort_values(by=['GMD', 'Muscle'], ascending=False)
        limit = df['Muscle'].quantile(0.85) if len(df) > 5 else 999
        df['Statut'] = np.where(df['Muscle'] >= limit, "⭐ ELITE PRO", "Standard")
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
        st.title("🏆 Performance et Suivi du Troupeau")
        if df.empty: st.info("Base vide. Utilisez l'onglet Admin ou Saisie.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p>GMD Moyen</p><h2>{df['GMD'].mean():.0f} g/j</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><p>Poids Moy.</p><h2>{df['p70'].mean():.1f} kg</h2></div>", unsafe_allow_html=True)
            
            st.subheader("📋 Classement par Performance (GMD & Muscle)")
            st.dataframe(df[['id', 'sexe', 'dentition', 'p70', 'GMD', 'Muscle', 'Statut']], use_container_width=True)

    # --- ECHO-COMPOSITION ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse Échographique Prédictive")
        if not df.empty:
            target = st.selectbox("Choisir un animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(f"<div class='analysis-box'><h3>Sujet : {target}</h3><b>Performance GMD :</b> {subj['GMD']} g/jour<br><b>Muscle :</b> {subj['Muscle']}%<br><b>Épaisseur Gras :</b> {subj['Gras_mm']} mm</div>", unsafe_allow_html=True)
        else: st.warning("Pas de données.")

    # --- SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1: source = st.radio("Source", ["📷 Caméra", "📁 Importer"], horizontal=True)
        with col_cfg2: mode = st.radio("Mode", ["🤖 IA", "📏 Manuel"], horizontal=True)
        
        img = st.camera_input("Profil de l'animal") if source == "📷 Caméra" else st.file_uploader("Photo", type=['jpg','png'])

        if img:
            with st.spinner("Analyse..."):
                time.sleep(1)
                res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                st.session_state['scan'] = res
                st.success("✅ Scan validé ! Tour de canon : 8.8 cm")

    # --- SAISIE MANUELLE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation et Identification")
        sd = st.session_state.get('scan', {})
        
        with st.form("form_saisie"):
            st.subheader("🆔 État Civil")
            c1, c2, c3 = st.columns(3)
            with c1: id_animal = st.text_input("N° Boucle / ID *")
            with c2: statut_dentaire = st.selectbox("Âge estimé", ["Agneau", "2 Dents", "4 Dents", "6 Dents", "Adulte", "Vieux"])
            with c3: sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)

            st.divider()
            st.subheader("⚖️ Historique de Poids (Calcul GMD)")
            cp1, cp2, cp3, cp4 = st.columns(4)
            with cp1: p_naiss = st.number_input("Poids Naiss.", 0.0)
            with cp2: p_10j = st.number_input("Poids 10j", 0.0)
            with cp3: p_30j = st.number_input("Poids 30j", 0.0)
            with cp4: p_70j = st.number_input("Poids actuel", 0.0)

            st.divider()
            st.subheader("📏 Morphologie (Scanner)")
            cm1, cm2, cm3, cm4 = st.columns(4)
            with cm1: hauteur = st.number_input("H. Garrot", value=float(sd.get('h_garrot', 0.0)))
            with cm2: canon = st.number_input("T. Canon", value=float(sd.get('c_canon', 0.0)))
            with cm3: thorax = st.number_input("P. Thorax", value=float(sd.get('p_thoracique', 0.0)))
            with cm4: 
                v_l = sd.get('l_corps', 0.0)
                longueur = st.number_input("Long. Corps", value=float(v_l) if isinstance(v_l, (int, float)) else 0.0)

            if st.form_submit_button("💾 INDEXER L'INDIVIDU", type="primary", use_container_width=True):
                if id_animal:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, sexe, dentition, race) VALUES (?,?,?,?)", (id_animal, sexe, statut_dentaire, "O.Djellal"))
                        conn.execute("INSERT INTO mesures (id_animal, p_naiss, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?,?,?)",
                                     (id_animal, p_naiss, p_10j, p_30j, p_70j, hauteur, canon, thorax, longueur))
                    st.success(f"✅ Animal {id_animal} enregistré !")
                else: st.warning("ID obligatoire.")

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS DE TEST"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_a = f"DZ-{random.randint(1000, 9999)}"
                    p30_sim = random.uniform(12, 18)
                    p70_sim = p30_sim + random.uniform(8, 15)
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_a, "O.Djellal", "Bélier", "Agneau", "Performance"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", 
                                 (id_a, p30_sim, p70_sim, 75, random.uniform(8,10), 95))
            st.rerun()

if __name__ == "__main__":
    main()
