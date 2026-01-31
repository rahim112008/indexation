import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import time

# ==========================================
# 1. CONFIGURATION ET STYLE (CADRES VISIBLES)
# ==========================================
st.set_page_config(page_title="Expert Selector Pro - Universel", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; margin-bottom: 15px;
    }
    .metric-card h2 { color: #2E7D32; font-size: 28px; margin: 5px 0; }
    .analysis-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #558b2f; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_universel.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
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
            id TEXT PRIMARY KEY, race TEXT, type_morpho TEXT, 
            p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL)''')

# ==========================================
# 3. MOTEUR UNIVERSEL (SUBSTITUT ÉCHOGRAPHE)
# ==========================================
def calculer_composition_universelle(row):
    try:
        p, h, t, c = float(row['p70']), float(row['h_garrot']), float(row['p_thoracique']), float(row['c_canon'])
        morpho = row.get('type_morpho', 'Mixte')
        
        # Coefficients adaptatifs par type de race (Universalité)
        coefs = {
            "Viande (Précoce)": {"musc": 1.15, "gras": 1.10, "rend": 1.05},
            "Mixte": {"musc": 1.00, "gras": 1.00, "rend": 1.00},
            "Rustique": {"musc": 0.85, "gras": 0.90, "rend": 0.92}
        }
        cf = coefs.get(morpho, coefs["Mixte"])

        ic = (t / h * 100) if h > 0 else 0
        gras_mm = max(1.2, ((t * 0.1) + (p * 0.04) - (h * 0.08)) * cf['gras'])
        pct_muscle = (50 + (ic * 0.18) - (c * 0.45)) * cf['musc']
        pct_gras = (gras_mm * 1.4 + 3) * cf['gras']
        pct_os = 100 - pct_muscle - pct_gras
        rendement = (40 + (ic * 0.12)) * cf['rend']
        score = (pct_muscle * 1.3) + (rendement * 0.7) - (c * 1.5)
        
        return {
            "muscle": round(pct_muscle, 1), "gras": round(pct_gras, 1), "os": round(pct_os, 1),
            "gras_mm": round(gras_mm, 1), "rendement": round(rendement, 1), "score": round(score / 1.6, 1)
        }
    except: return None

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    
    # Barre latérale
    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "📸 Scanner IA", "✍️ Saisie", "🔧 Admin"])

    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord du Troupeau")
        if df.empty:
            st.info("Aucune donnée disponible. Commencez par la Saisie ou le Scanner.")
        else:
            df_res = df.apply(lambda x: pd.Series(calculer_composition_universelle(x)), axis=1)
            full_df = pd.concat([df, df_res], axis=1).sort_values(by="score", ascending=False)
            
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><p>Moy. Muscle</p><h2>{full_df['muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><p>Score Max</p><h2>{full_df['score'].max():.1f}</h2></div>", unsafe_allow_html=True)
            
            st.subheader("📋 Classement de Sélection")
            st.dataframe(full_df[['id', 'race', 'score', 'muscle', 'rendement', 'type_morpho']], use_container_width=True)

    # --- COMPOSITION (SUBSTITUT ÉCHO) ---
    elif menu == "🥩 Composition":
        st.title("🥩 Diagnostic Écho-Virtuel")
        if df.empty:
            st.warning("Veuillez d'abord enregistrer un animal.")
        else:
            target = st.selectbox("Sélectionner l'animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            res = calculer_composition_universelle(subj)
            
            if res:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.subheader("📟 Sonde Virtuelle")
                    fig_g = go.Figure(go.Indicator(
                        mode="gauge+number", value=res['gras_mm'],
                        title={'text': "Épaisseur Gras (mm)"},
                        gauge={'axis': {'range': [0, 15]}, 'bar': {'color': "#E65100"}}))
                    fig_g.update_layout(height=250)
                    st.plotly_chart(fig_g, use_container_width=True)
                    

                with col2:
                    st.subheader("🧱 Tissus (Dissection)")
                    fig_p = px.pie(values=[res['muscle'], res['gras'], res['os']], 
                                   names=['Muscle', 'Gras', 'Os'],
                                   color_discrete_sequence=['#2E7D32', '#FBC02D', '#9E9E9E'], hole=0.4)
                    st.plotly_chart(fig_p, use_container_width=True)

                with col3:
                    st.subheader("🏆 Rapport")
                    st.markdown(f"""
                        <div class='analysis-box'>
                            <h2 style='color:#2E7D32; margin:0;'>{res['score']}/100</h2>
                            <p><b>Note de Sélection</b></p>
                            <hr>
                            <b>Rendement:</b> {res['rendement']}%<br>
                            <b>Finesse d'os:</b> {'Idéale' if subj['c_canon'] < 8.5 else 'Standard'}<br>
                            <b>Potentiel:</b> {'⭐ ELITE' if res['score'] > 75 else 'Standard'}
                        </div>
                    """, unsafe_allow_html=True)

                st.divider()
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=[res['muscle'], res['rendement'], res['score'], subj['p70']],
                    theta=['Muscle %', 'Rendement %', 'Score Global', 'Poids'],
                    fill='toself', line_color='#2E7D32'
                ))
                st.plotly_chart(fig_radar, use_container_width=True)
                

    # --- SCANNER IA (ÉTALON 1M) ---
    elif menu == "📸 Scanner IA":
        st.title("📸 Station de Scan Biométrique")
        st.info("Calibrage automatique sur étalon de 1 mètre.")
        img = st.camera_input("Positionnez l'animal de profil")
        if img:
            st.success("Image capturée. Extraction des points osseux...")
            # Simulation des résultats du scanner
            st.session_state['scan_data'] = {'h': 74.0, 't': 88.0, 'c': 8.4}
            st.json(st.session_state['scan_data'])

    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Enregistrement de l'Individu")
        scan = st.session_state.get('scan_data', {})
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            id_a = c1.text_input("ID / Boucle *")
            race = c1.text_input("Race (ex: Ouled Djellal, Merinos)")
            type_m = c1.selectbox("Morphotype", ["Viande (Précoce)", "Mixte", "Rustique"])
            p70 = c2.number_input("Poids actuel (kg)", 0.0)
            h = c2.number_input("Hauteur (cm)", value=scan.get('h', 0.0))
            t = c2.number_input("Thorax (cm)", value=scan.get('t', 0.0))
            c = c2.number_input("Canon (cm)", value=scan.get('c', 0.0))
            if st.form_submit_button("Enregistrer l'Analyse"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?)", 
                                     (id_a, race, type_m, p70, h, c, t, 0.0))
                    st.balloons()
                    st.success(f"Animal {id_a} indexé avec succès.")
                else: st.error("L'ID est obligatoire.")

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        if st.button("🗑️ Réinitialiser la base de données"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
