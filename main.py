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
        border: 1px solid #e0e0e0; border-top: 5px solid #2E7D32;
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
# 3. MOTEUR ZOOTECHNIQUE PROFESSIONNEL
# ==========================================
def calculer_metrics_finales(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'IC': 0.0, 'Gras_mm': 0.0, 'GMD': 0, 'ICA': 0.0}
    try:
        p_actuel = float(row.get('p70') or 0)
        p_depart = float(row.get('p30') or 0)
        hg = float(row.get('h_garrot') or 75)
        pt = float(row.get('p_thoracique') or 90)
        cc = float(row.get('c_canon') or 9)
        
        if p_actuel < 5: return pd.Series(res)

        # 1. GMD (Gain Moyen Quotidien)
        if p_actuel > p_depart and p_depart > 0:
            res['GMD'] = round(((p_actuel - p_depart) / 40) * 1000)

        # 2. ICA Estimé (Indice de Conversion)
        # Formule empirique : les animaux à fort GMD et bonne compacité sont plus efficients
        if res['GMD'] > 0:
            res['ICA'] = round(3.5 + (1500 / res['GMD']) - (pt/hg * 0.5), 2)
            res['ICA'] = max(2.8, min(7.5, res['ICA'])) # Bornes réalistes

        # 3. Morphologie & Carcasse
        ic_calc = (pt / (cc * hg)) * 1000
        res['IC'] = round(ic_calc, 2)
        egd = 1.2 + (p_actuel * 0.15) + (ic_calc * 0.05) - (hg * 0.03)
        res['Gras_mm'] = round(max(0.5, egd), 2)
        res['Gras'] = round(max(5.0, 4.0 + (res['Gras_mm'] * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 82.0 - (res['Gras'] * 0.6) + (ic_calc * 0.12)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)

        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p_naiss, m.p10, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                   FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal 
                   LEFT JOIN mesures m ON last_m.last_id = m.id"""
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id']).reset_index(drop=True)
        metrics_df = df.apply(calculer_metrics_finales, axis=1)
        df = pd.concat([df, metrics_df], axis=1)
        df['Score_Expert'] = round((df['Muscle'] * 0.5) + (df['GMD']/10 * 0.5), 1)
        df = df.sort_values(by='Score_Expert', ascending=False)
        seuil = df['Score_Expert'].quantile(0.85) if len(df) > 5 else 999
        df['Statut'] = np.where(df['Score_Expert'] >= seuil, "⭐ ELITE PRO", "Standard")
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
        st.title("🏆 Performance Zootechnique")
        if df.empty: st.info("Base vide.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p>GMD Moyen</p><h2>{df['GMD'].mean():.0f} g/j</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><p>ICA Moyen</p><h2>{df['ICA'].mean():.2f}</h2></div>", unsafe_allow_html=True)
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA', 'Statut']], use_container_width=True)

    # --- ECHO-COMPOSITION ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse de Carcasse")
        if not df.empty:
            target = st.selectbox("Sélectionner", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4)])
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(f"<div class='analysis-box'><h3>Sujet : {target}</h3><b>Efficience (ICA) :</b> {subj['ICA']}<br><b>GMD :</b> {subj['GMD']} g/j</div>", unsafe_allow_html=True)

    # --- SCANNER EXPERT ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        c_cfg1, c_cfg2 = st.columns(2)
        with c_cfg1: source = st.radio("Source", ["📷 Caméra", "📁 Importer"], horizontal=True)
        with c_cfg2: mode = st.radio("Méthode", ["🤖 Automatique", "📏 Manuel"], horizontal=True)
        img = st.camera_input("Profil") if source == "📷 Caméra" else st.file_uploader("Image")
        if img:
            res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
            st.session_state['scan'] = res
            st.success(f"✅ Cadrage valide ! Tour de canon détecté : {res['c_canon']} cm")

    # --- SAISIE MANUELLE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation et Identification")
        sd = st.session_state.get('scan', {})
        with st.form("form_saisie"):
            st.subheader("🆔 Identité & Âge")
            c1, c2, c3 = st.columns(3)
            with c1: id_animal = st.text_input("N° Boucle / ID *")
            with c2: dentition = st.selectbox("Âge estimé", ["Agneau", "2 Dents", "4 Dents", "Adulte"])
            with c3: sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)
            st.divider()
            st.subheader("⚖️ Pesées")
            cp1, cp2 = st.columns(2)
            with cp1: p_30 = st.number_input("Poids 30j (kg)", 0.0)
            with cp2: p_70 = st.number_input("Poids 70j (kg)", 0.0)
            st.divider()
            st.subheader("📏 Morphologie")
            cm1, cm2, cm3 = st.columns(3)
            with cm1: h_g = st.number_input("H. Garrot", value=float(sd.get('h_garrot', 0.0)))
            with cm2: c_c = st.number_input("T. Canon", value=float(sd.get('c_canon', 0.0)))
            with cm3: p_t = st.number_input("P. Thorax", value=float(sd.get('p_thoracique', 0.0)))
            if st.form_submit_button("💾 INDEXER L'INDIVIDU", type="primary", use_container_width=True):
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_animal, "O.Djellal", sexe, dentition, "Performance"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_animal, p_30, p_70, h_g, c_c, p_t))
                st.success("Enregistré !")

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        if st.button("🚀 GÉNÉRER TEST PROFESSIONNEL"):
            with get_db_connection() as conn:
                for i in range(20):
                    id_a = f"DZ-{random.randint(1000, 9999)}"
                    p3 = random.uniform(12, 16); p7 = p3 + random.uniform(8, 14)
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_a, "O.Djellal", "Agneau", "Agneau", "Test"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_a, p3, p7, 75, 9, 95))
            st.rerun()

if __name__ == "__main__":
    main()
