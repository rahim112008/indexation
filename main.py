import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

# ==========================================
# 1. DESIGN & CSS (CADRES VISIBLES)
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
            id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, 
            p_thoracique REAL, l_corps REAL, l_poitrine REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. MOTEUR DE CALCULS CARCASSE
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70, hg, pt, cc = float(row.get('p70', 0)), float(row.get('h_garrot', 70)), float(row.get('p_thoracique', 80)), float(row.get('c_canon', 8.5))
        if p70 <= 5 or cc <= 2: return 0, 0, 0, 0, "Inconnu", 0, 0
        ic = max(15, min(45, (pt / (cc * hg)) * 1000))
        gras_mm = max(2.0, min(22.0, 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)))
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)
        cl = "S" if ic > 33 else "E" if ic > 30 else "U" if ic > 27 else "R" if ic > 24 else "O/P"
        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        return round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(gras_mm, 1), cl, s90, round(ic, 1)
    except: return 0, 0, 0, 0, "Erreur", 0, 0

@st.cache_data(ttl=2)
def load_data():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("""SELECT b.*, m.p70, m.h_garrot, m.p_thoracique, m.c_canon, m.l_corps, m.l_poitrine 
                               FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                               LEFT JOIN mesures m ON l.mid = m.id""", conn)
            if df.empty: return df
            res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = res
            df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
            df['Statut'] = np.where(df['Index'] >= df['Index'].quantile(0.85), "⭐ ELITE PRO", "Standard")
            return df
    except: return pd.DataFrame()

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    # Barre latérale
    st.sidebar.title("💎 Expert Selector")
    search_query = st.sidebar.text_input("🔍 Recherche par ID", "").strip()
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    df_filtered = df[df['id'].str.contains(search_query, case=False, na=False)] if (search_query and not df.empty) else df

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty: st.info("Commencez par le Scanner ou la Saisie.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><p>Elite</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><p>Gras Moy.</p><h2>{df['Gras_mm'].mean():.1f}mm</h2></div>", unsafe_allow_html=True)
            st.dataframe(df_filtered[['id', 'race', 'p70', 'Pct_Muscle', 'EUROP', 'Statut']], use_container_width=True)

    # --- COMPOSITION PRO ---
    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de Carcasse")
        if not df.empty:
            target = st.selectbox("Sélectionner l'animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(r=[subj['Pct_Muscle'], subj['Pct_Gras'], subj['Pct_Os'], subj['IC']],
                    theta=['Muscle %', 'Gras %', 'Os %', 'Conformation'], fill='toself', line_color='#2E7D32'))
                st.plotly_chart(fig_radar, use_container_width=True)
            with col2:
                st.markdown(f"<div class='analysis-box'><b>ID:</b> {target}<br><b>Classe:</b> {subj['EUROP']}<br><b>Muscle:</b> {subj['Pct_Muscle']}%</div>", unsafe_allow_html=True)
        else: st.warning("Données absentes.")

    # --- SCANNER INTELLIGENT (VOTRE BLOC) ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Intelligent")
        col1, col2 = st.columns(2)
        with col1:
            img = st.camera_input("📷 Photo de profil")
        with col2:
            race_scan = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Non identifiée"])
            correction = st.slider("Ajustement (%)", -10, 10, 0)
        
        if img:
            with st.spinner("Analyse du profil..."):
                time.sleep(1)
                DATA_RACES = {
                    "Ouled Djellal": {"h_garrot": 72.0, "c_canon": 8.0, "l_poitrine": 24.0, "p_thoracique": 83.0, "l_corps": 82.0},
                    "Rembi": {"h_garrot": 76.0, "c_canon": 8.8, "l_poitrine": 26.0, "p_thoracique": 88.0, "l_corps": 86.0},
                    "Hamra": {"h_garrot": 70.0, "c_canon": 7.8, "l_poitrine": 23.0, "p_thoracique": 80.0, "l_corps": 78.0},
                    "Babarine": {"h_garrot": 74.0, "c_canon": 8.2, "l_poitrine": 25.0, "p_thoracique": 85.0, "l_corps": 84.0},
                    "Non identifiée": {"h_garrot": 73.0, "c_canon": 8.1, "l_poitrine": 24.5, "p_thoracique": 84.0, "l_corps": 82.5}
                }
                base = DATA_RACES[race_scan].copy()
                if correction != 0:
                    fact = 1 + (correction/100)
                    for k in base: base[k] = round(base[k] * fact, 1)
                
                st.session_state['scan'] = base
                st.success(f"✅ Profil {race_scan} chargé. Prêt pour transfert.")
                
                res_cols = st.columns(3)
                res_cols[0].metric("Hauteur", f"{base['h_garrot']} cm")
                res_cols[1].metric("Canon", f"{base['c_canon']} cm")
                res_cols[2].metric("Thorax", f"{base['p_thoracique']} cm")
                
                if st.button("📝 Transférer vers Saisie"):
                    st.session_state['go_saisie'] = True
                    st.success("Données envoyées ! Cliquez sur l'onglet Saisie.")

    # --- SAISIE (AVEC RÉCEPTION SCAN) ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Enregistrement Animal")
        # On récupère les données du scan s'il existe
        sd = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.info("✨ Mesures importées du scanner.")
            # On ne remet à False qu'après l'affichage
        
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            with c1:
                id_animal = st.text_input("Identifiant (ID) *")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
            with c2:
                p70 = st.number_input("Poids Actuel (kg) *", 0.0, 150.0, 0.0)
                cc = st.number_input("Canon (cm) *", 0.0, 20.0, float(sd.get('c_canon', 0.0)))
            
            st.subheader("Mesures Morphologiques")
            m1, m2, m3 = st.columns(3)
            hg = m1.number_input("Hauteur (cm)", value=float(sd.get('h_garrot', 0.0)))
            pt = m2.number_input("Périmètre Thorax (cm)", value=float(sd.get('p_thoracique', 0.0)))
            lc = m3.number_input("Longueur Corps (cm)", value=float(sd.get('l_corps', 0.0)))
            
            if st.form_submit_button("💾 SAUVEGARDER"):
                if id_animal and p70 > 0 and cc > 0:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_animal, race))
                        conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?)", (id_animal, p70, hg, cc, pt, lc))
                    st.session_state['scan'] = {} # Vider après succès
                    st.session_state['go_saisie'] = False
                    st.success("Sauvegardé !"); time.sleep(1); st.rerun()
                else: st.error("ID, Poids et Canon sont obligatoires.")

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        if st.button("🗑️ Vider la base de données"):
            with get_db_connection() as conn: conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
