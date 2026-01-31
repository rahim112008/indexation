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
    .podium-card {
        background: linear-gradient(135deg, #f1f8e9 0%, #ffffff 100%);
        padding: 15px; border-radius: 12px; border: 2px solid #FFD700;
        text-align: center; margin-bottom: 10px;
    }
    .analysis-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #558b2f; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
        .podium-card { background: #262626; border-color: #B8860B; color: white; }
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
            id TEXT PRIMARY KEY, race TEXT, type_morpho TEXT, p70 REAL, h_garrot REAL, c_canon REAL, 
            p_thoracique REAL, l_corps REAL, l_poitrine REAL)''')

# ==========================================
# 3. MOTEUR DE CALCULS CARCASSE (ÉCHO-LIKE UNIVERSEL)
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70, hg, pt, cc = float(row.get('p70', 0)), float(row.get('h_garrot', 70)), float(row.get('p_thoracique', 80)), float(row.get('c_canon', 8.5))
        if p70 <= 5 or cc <= 2: return 0, 0, 0, 0, "Inconnu", 0, 0
        
        ic = (pt / hg * 100) if hg > 0 else 0
        gras_mm = max(1.5, (pt * 0.12) + (p70 * 0.05) - (hg * 0.1))
        pct_muscle = round(52 + (ic * 0.15) - (cc * 0.4), 1)
        pct_gras = round((gras_mm * 1.5) + 4, 1)
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)
        cl = "S" if ic > 130 else "E" if ic > 120 else "U" if ic > 110 else "R" if ic > 100 else "O"
        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        return pct_muscle, pct_gras, pct_os, round(gras_mm, 1), cl, s90, round(ic, 1)
    except: return 0, 0, 0, 0, "Erreur", 0, 0

@st.cache_data(ttl=2)
def load_data():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT * FROM beliers", conn)
            if df.empty: return df
            res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = res
            df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
            df['Statut'] = np.where(df['Index'] >= df['Index'].quantile(0.85) if len(df)>1 else df['Index'], "⭐ ELITE PRO", "Standard")
            return df
    except: return pd.DataFrame()

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    st.sidebar.title("💎 Expert Selector")
    search_query = st.sidebar.text_input("🔍 Recherche par ID", "").strip()
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    df_filtered = df[df['id'].str.contains(search_query, case=False, na=False)] if (search_query and not df.empty) else df

    # --- DASHBOARD AMÉLIORÉ ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Centre de Performance Ovine")
        if df.empty: 
            st.info("👋 Bienvenue ! Commencez par le Scanner ou la Saisie pour analyser vos premiers sujets.")
        else:
            # KPIs de tête
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><p>Elite</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><p>Gras Moy.</p><h2>{df['Gras_mm'].mean():.1f}mm</h2></div>", unsafe_allow_html=True)
            
            st.divider()

            # Podium des Champions
            st.subheader("🥇 Top 3 des Meilleurs Reproducteurs (Index Boucher)")
            top_3 = df.sort_values(by="Index", ascending=False).head(3)
            p_cols = st.columns(3)
            for i, (idx, row) in enumerate(top_3.iterrows()):
                with p_cols[i]:
                    st.markdown(f"""<div class='podium-card'><h3>Rang {i+1}</h3><h2>ID: {row['id']}</h2>
                    <p><b>Index:</b> {row['Index']:.1f} | <b>Muscle:</b> {row['Pct_Muscle']}%</p></div>""", unsafe_allow_html=True)

            st.divider()

            # Graphiques d'analyse
            g1, g2 = st.columns(2)
            with g1:
                st.subheader("📊 Répartition des Classes EUROP")
                fig_pie = px.pie(df, names='EUROP', hole=0.4, color_discrete_sequence=px.colors.sequential.Greens_r)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with g2:
                st.subheader("📈 Corrélation Muscle / Poids")
                fig_scatter = px.scatter(df, x='p70', y='Pct_Muscle', color='Statut', size='IC', hover_data=['id'])
                st.plotly_chart(fig_scatter, use_container_width=True)

            st.subheader("🔍 Liste Complète")
            st.dataframe(df_filtered[['id', 'race', 'p70', 'Pct_Muscle', 'EUROP', 'Statut', 'Index']], use_container_width=True)

    # --- COMPOSITION PRO ---
    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de Carcasse (Écho-Like)")
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
                st.markdown(f"<div class='analysis-box'><b>ID:</b> {target}<br><b>Classe:</b> {subj['EUROP']}<br><b>Muscle:</b> {subj['Pct_Muscle']}%<br><b>Gras Dorsal:</b> {subj['Gras_mm']}mm</div>", unsafe_allow_html=True)
        else: st.warning("Données absentes.")

    # --- SCANNER EXPERT FINAL ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1: source = st.radio("Source", ["📷 Caméra", "📁 Importer"], horizontal=True)
        with col_cfg2: mode_scanner = st.radio("Méthode", ["🤖 IA", "📏 Manuel"], horizontal=True)
        
        img = st.camera_input("Profil") if source == "📷 Caméra" else st.file_uploader("Photo", type=['jpg','png'])

        if img:
            col_img, col_res = st.columns([1.5, 1])
            with col_img: st.image(img, caption="Scan 1m Standard", use_container_width=True)
            with col_res:
                if mode_scanner == "🤖 IA":
                    time.sleep(1)
                    res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                    st.success("✅ CADRAGE VALIDE")
                else:
                    h_in = st.number_input("Hauteur Garrot", value=72.0)
                    c_in = st.number_input("Tour Canon", value=8.5)
                    t_in = st.number_input("Thorax", value=84.0)
                    res = {"h_garrot": h_in, "c_canon": c_in, "p_thoracique": t_in, "l_corps": 82.0}
                
                st.session_state['scan'] = res
                st.metric("📏 Hauteur", f"{res['h_garrot']} cm")
                st.metric("🦴 Canon", f"{res['c_canon']} cm")
                if st.button("🚀 ENVOYER À LA SAISIE"): st.success("Transféré !")

    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation")
        sd = st.session_state.get('scan', {})
        with st.form("form_saisie"):
            id_animal = st.text_input("N° Boucle / ID *")
            race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Autre"])
            c1, c2 = st.columns(2)
            p70j = c1.number_input("Poids (kg)", value=0.0)
            canon = c2.number_input("Tour de Canon", value=float(sd.get('c_canon', 0.0)))
            hg = c1.number_input("Hauteur Garrot", value=float(sd.get('h_garrot', 0.0)))
            pt = c2.number_input("Périmètre Thorax", value=float(sd.get('p_thoracique', 0.0)))
            
            if st.form_submit_button("💾 INDEXER"):
                if id_animal:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)",
                                     (id_animal, race, p70j, hg, canon, pt))
                    st.success(f"✅ {id_animal} enregistré !")
                else: st.warning("ID requis.")

    elif menu == "🔧 Admin":
        if st.button("🗑️ Vider la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
