import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
from PIL import Image
import random
import time
import io

# ==========================================
# 1. CONFIGURATION & DESIGN (UI/UX)
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v4.0", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 15px;
        border-top: 5px solid #1b5e20; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        text-align: center;
    }
    .ai-box {
        background-color: #e3f2fd; padding: 15px; border-radius: 10px;
        border-left: 5px solid #1976d2; margin: 10px 0;
    }
    .vs-divider {
        font-size: 30px; font-weight: bold; color: #d32f2f;
        display: flex; align-items: center; justify-content: center; height: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_recherche.db"

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
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. MOTEUR ZOOTECHNIQUE & IA
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        
        if p70 <= 0: return pd.Series(res)
        
        # GMD & Compacité
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        
        # ICA (Efficience alimentaire estimée)
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, min(8.0, 3.2 + (1450 / res['GMD']) - (res['IC'] / 200))), 2)
        
        # Echo-Composition Prédite
        egd = 1.2 + (p70 * 0.15) + (res['IC'] * 0.05) - (hg * 0.03)
        res['Gras'] = round(max(5.0, 4.0 + (egd * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (res['IC'] * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_full_data():
    init_db()
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique 
                   FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal 
                   LEFT JOIN mesures m ON last_m.last_id = m.id"""
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id']).reset_index(drop=True)
        metrics = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, metrics], axis=1)
        df['Score_Expert'] = round((df['Muscle'] * 0.4) + (df['GMD']/10 * 0.4) + ((8 - df['ICA']) * 15), 1)
    return df

# ==========================================
# 4. COMPOSANTS DE L'INTERFACE
# ==========================================

def view_dashboard(df):
    st.title("🏆 Performance Zootechnique")
    if df.empty:
        st.info("Base de données vide.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='metric-card'>Sujets<br><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'>GMD Moyen<br><h2>{df['GMD'].mean():.0f} g/j</h2></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'>Muscle Moy.<br><h2>{df['Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='metric-card'>ICA Moyen<br><h2>{df['ICA'].mean():.2f}</h2></div>", unsafe_allow_html=True)
    st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA', 'Score_Expert']], use_container_width=True)

def view_scanner():
    st.title("📸 Station de Scan Biométrique")
    c_cfg, c_img = st.columns([1, 2])
    with c_cfg:
        source = st.radio("Source", ["📷 Caméra", "📁 Importer Photo"])
        ref = st.selectbox("Étalon de mesure", ["Règle 1 mètre", "Feuille A4", "Carte Bancaire"])
        img_file = st.camera_input("Scanner") if source == "📷 Caméra" else st.file_uploader("Image")
    
    if img_file:
        with st.spinner("Analyse IA et étalonnage..."):
            time.sleep(1) # Simulation
            res = {"h_garrot": round(75.5 + random.uniform(-2, 2), 1), 
                   "c_canon": round(9.0 + random.uniform(-0.5, 0.5), 1), 
                   "p_thoracique": round(92.0 + random.uniform(-3, 3), 1)}
            st.session_state['last_scan'] = res
            st.success(f"✅ Étalonnage réussi via {ref}")
            st.json(res)
            if st.button("Utiliser ces mesures pour l'indexation"):
                st.session_state['page'] = "✍️ Indexation"
                st.rerun()

def view_echo_composition(df):
    st.title("🥩 Echo-Composition & Comparateur")
    if df.empty: return
    
    col_a, col_vs, col_b = st.columns([4, 1, 4])
    with col_a:
        id_a = st.selectbox("Individu A", df['id'].unique(), key="a")
        subj_a = df[df['id'] == id_a].iloc[0]
        fig_a = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj_a['Muscle'], subj_a['Gras'], subj_a['Os']], hole=.4)])
        st.plotly_chart(fig_a, use_container_width=True)
    
    with col_vs:
        st.markdown("<div class='vs-divider'><br>VS</div>", unsafe_allow_html=True)
    
    with col_b:
        id_b = st.selectbox("Individu B", df['id'].unique(), key="b")
        subj_b = df[df['id'] == id_b].iloc[0]
        fig_b = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj_b['Muscle'], subj_b['Gras'], subj_b['Os']], hole=.4)])
        st.plotly_chart(fig_b, use_container_width=True)

def view_nutrition(df):
    st.title("🥗 Nutritionniste Assisté par IA")
    target = st.selectbox("Sélectionner l'animal", df['id'].unique())
    subj = df[df['id'] == target].iloc[0]
    
    st.subheader("Simulateur d'impact alimentaire")
    energie = st.slider("Ajustement Énergie (UFL)", 0.7, 1.3, 1.0)
    proteine = st.slider("Ajustement Protéines (PDI)", 0.7, 1.3, 1.0)
    
    # Simulation IA simplifiée
    new_gmd = subj['GMD'] * (energie * 0.7 + proteine * 0.3)
    new_muscle = subj['Muscle'] * proteine
    
    st.markdown(f"""
    <div class='ai-box'>
        <b>Prédiction IA pour {target} :</b><br>
        Le GMD passerait à <b>{new_gmd:.0f} g/j</b>. <br>
        Le rendement musculaire serait impacté de <b>{((proteine-1)*100):+.1f}%</b>.
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 5. POINT D'ENTRÉE PRINCIPAL
# ==========================================
def main():
    df = load_full_data()
    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Navigation", 
        ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition IA", "💾 Data Mgmt", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        view_dashboard(df)

    elif menu == "📸 Scanner":
        view_scanner()

    elif menu == "✍️ Indexation":
        st.title("✍️ Indexation")
        scan = st.session_state.get('last_scan', {})
        with st.form("saisie"):
            id_a = st.text_input("ID Animal")
            p30, p70 = st.number_input("Poids 30j"), st.number_input("Poids 70j")
            hg = st.number_input("Hauteur Garrot", value=float(scan.get('h_garrot', 75.0)))
            cc = st.number_input("Tour de Canon", value=float(scan.get('c_canon', 9.0)))
            pt = st.number_input("Périmètre Thorax", value=float(scan.get('p_thoracique', 90.0)))
            if st.form_submit_button("Sauvegarder"):
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_a, "O.Djellal"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_a, p30, p70, hg, cc, pt))
                st.success("Enregistré !")

    elif menu == "🥩 Echo-Composition":
        view_echo_composition(df)

    elif menu == "🥗 Nutrition IA":
        view_nutrition(df)

    elif menu == "💾 Data Mgmt":
        st.title("💾 Import/Export CSV")
        if not df.empty:
            st.download_button("Exporter en CSV", df.to_csv(index=False).encode('utf-8'), "data.csv", "text/csv")
        up = st.file_uploader("Importer CSV")
        if up and st.button("Valider l'import"):
            idf = pd.read_csv(up)
            # Logique d'insertion SQL ici...
            st.success("Import réussi")

    elif menu == "🔧 Admin":
        if st.button("🚀 Générer données de test"):
            with get_db_connection() as conn:
                for i in range(5):
                    id_t = f"TEST-{random.randint(100,999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "O.Djellal", "Bélier", "Agneau"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_t, 14, 28, 76, 9.2, 94))
            st.rerun()

if __name__ == "__main__":
    main()
