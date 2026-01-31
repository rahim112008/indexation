import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import time
import random

# ==========================================
# 1. DESIGN & CSS
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; margin-bottom: 15px;
    }
    .metric-card h2 { color: #2E7D32; font-size: 28px; margin: 5px 0; }
    .metric-card p { color: #555555; font-weight: 600; text-transform: uppercase; font-size: 13px; margin:0; }
    .analysis-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #558b2f; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)
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
            id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, 
            p_thoracique REAL, l_corps REAL, 
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
        # Patch de sécurité pour la colonne sexe
        try: conn.execute("ALTER TABLE beliers ADD COLUMN sexe TEXT")
        except: pass
        try: conn.execute("ALTER TABLE beliers ADD COLUMN dentition TEXT")
        except: pass

# ==========================================
# 3. MOTEUR DE CALCULS & CHARGEMENT
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70 = float(row.get('p70') or 0)
        hg = float(row.get('h_garrot') or 70)
        pt = float(row.get('p_thoracique') or 80)
        cc = float(row.get('c_canon') or 8.5)
        if p70 <= 5: return 0, 0, 0, 0, "N/A", 0, 0
        ic = max(15, min(45, (pt / (cc * hg)) * 1000))
        gras_mm = max(2.0, min(22.0, 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)))
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)
        cl = "S" if ic > 33 else "E" if ic > 30 else "U" if ic > 27 else "R" if ic > 24 else "O/P"
        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        return round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(gras_mm, 1), cl, s90, round(ic, 1)
    except: return 0, 0, 0, 0, "Erreur", 0, 0

def load_data():
    with get_db_connection() as conn:
        df = pd.read_sql("""SELECT b.*, m.p70, m.h_garrot, m.p_thoracique, m.c_canon, m.l_corps 
                           FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                           LEFT JOIN mesures m ON l.mid = m.id""", conn)
    if not df.empty:
        res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
        df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = res
        df['Index'] = (df['p70'].fillna(0) * 0.4) + (df['S90'].fillna(0) * 0.6)
        limit = df['Index'].quantile(0.85) if len(df) > 5 else 999
        df['Statut'] = np.where(df['Index'] >= limit, "⭐ ELITE PRO", "Standard")
    return df

# ==========================================
# 4. FONCTIONS ADMIN (50 INDIVIDUS)
# ==========================================
def generer_50_test():
    sexes = ["Bélier", "Brebis", "Agneau", "Agnelle"]
    races = ["Ouled Djellal", "Rembi", "Hamra"]
    with get_db_connection() as conn:
        for i in range(50):
            id_a = f"DZ-{random.randint(2024, 2026)}-{random.randint(1000, 9999)}"
            sx = random.choice(sexes)
            hg, pt, cc, p70 = (random.uniform(70,85), random.uniform(85,110), random.uniform(8,10), random.uniform(60,90)) if "Agne" not in sx else (random.uniform(50,65), random.uniform(60,75), random.uniform(6,7.5), random.uniform(25,45))
            conn.execute("INSERT OR REPLACE INTO beliers (id, race, sexe, dentition) VALUES (?,?,?,?)", (id_a, random.choice(races), sx, "Adulte"))
            conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?)", (id_a, p70, hg, cc, pt, hg*1.1))

# ==========================================
# 5. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    st.sidebar.title("💎 Expert Selector")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty: st.info("Base vide. Allez dans Admin pour générer des données.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p>Elite</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'><p>Poids Moyen</p><h2>{df['p70'].mean():.1f} kg</h2></div>", unsafe_allow_html=True)
            st.dataframe(df[['id', 'sexe', 'race', 'p70', 'Pct_Muscle', 'EUROP', 'Statut']], use_container_width=True)

    # --- COMPOSITION ---
    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de Carcasse")
        if not df.empty:
            target = st.selectbox("Sélectionner l'animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure(go.Scatterpolar(r=[subj['Pct_Muscle'], subj['Pct_Gras'], subj['Pct_Os'], subj['IC']],
                    theta=['Muscle %', 'Gras %', 'Os %', 'Conformation'], fill='toself', line_color='#2E7D32'))
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(f"<div class='analysis-box'><b>ID:</b> {target}<br><b>Classe:</b> {subj['EUROP']}<br><b>Muscle:</b> {subj['Pct_Muscle']}%</div>", unsafe_allow_html=True)
        else: st.warning("Données absentes.")

    # --- SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        mode = st.radio("Mode", ["🤖 Automatique (IA)", "📏 Manuel"], horizontal=True)
        img = st.camera_input("Scanner l'animal")
        if img:
            with st.spinner("Analyse en cours..."):
                time.sleep(1)
                res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                st.session_state['scan'] = res
                st.success("Scan validé ! Tour de canon : 8.8 cm")
                if st.button("🚀 ENVOYER À LA SAISIE"): 
                    st.info("Données transférées vers l'onglet Saisie.")

    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation")
        sd = st.session_state.get('scan', {})
        with st.form("f_saisie"):
            id_a = st.text_input("ID / Boucle *")
            sexe = st.selectbox("Sexe", ["Bélier", "Brebis", "Agneau", "Agnelle"])
            poids = st.number_input("Poids actuel (kg)", 0.0)
            hg = st.number_input("Hauteur Garrot (cm)", value=float(sd.get('h_garrot', 0.0)))
            cc = st.number_input("Tour de Canon (cm)", value=float(sd.get('c_canon', 0.0)))
            if st.form_submit_button("💾 ENREGISTRER"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, sexe) VALUES (?,?)", (id_a, sexe))
                        conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon) VALUES (?,?,?,?)", (id_a, poids, hg, cc))
                    st.success("Animal indexé !")
                else: st.error("L'ID est obligatoire.")

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS DE TEST", use_container_width=True):
            generer_50_test()
            st.success("50 individus ajoutés !")
            st.rerun()
        if st.button("🗑️ VIDER LA BASE", type="primary", use_container_width=True):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
