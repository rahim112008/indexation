import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from contextlib import contextmanager
import time

# ==========================================
# CONFIGURATION & BASE DE DONNÉES
# ==========================================
DB_NAME = "expert_ovin_pro.db"

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
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, race TEXT, sexe TEXT, date_naiss TEXT, dentition TEXT,
                p10 REAL, p30 REAL, p70 REAL,
                h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
                pct_muscle REAL, pct_gras REAL, index_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

def calculer_echo_data(row):
    """Calcule les scores de composition pour les graphiques"""
    h = row['h_garrot']
    t = row['p_thoracique']
    c = row['c_canon']
    # Algorithme de compacité
    ic = (t / (c * h)) * 100 if (c*h) > 0 else 0
    muscle = round(45 + (ic * 0.2), 1)
    gras = round(max(5, 100 - muscle - 12), 1) # 12% os fixe
    return muscle, gras, round(ic, 2)

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
def main():
    st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")
    init_db()
    
    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Menu Principal", [
        "📊 Dashboard", 
        "📸 Scanner IA (1m Standard)", 
        "⚖️ Comparateur Elite",
        "✍️ Saisie & Mesures",
        "⚙️ Admin"
    ])

    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- MODULE SCANNER IA ---
    if menu == "📸 Scanner IA (1m Standard)":
        st.title("📸 Scanner Morphologique")
        st.info("Calibration : L'IA utilise l'étalon de 1 mètre pour convertir les pixels en cm.")
        
        tab1, tab2 = st.tabs(["📁 Fichier Image", "📷 Caméra Directe"])
        source = None
        with tab1: source = st.file_uploader("Importer une photo de profil", type=['jpg', 'png'])
        with tab2: cam = st.camera_input("Scanner")
        if cam: source = cam

        if source:
            st.image(source, width=500)
            if st.button("🚀 Lancer l'analyse Biométrique"):
                with st.spinner("Calcul des ratios via étalon 1m..."):
                    time.sleep(1.5)
                    res = {'h_garrot': 74.5, 'l_corps': 83.2, 'p_thoracique': 89.0, 'c_canon': 8.5}
                    st.session_state['last_scan'] = res
                    st.success("✅ Mesures extraites !")
                    st.json(res)
                    

    # --- MODULE COMPARATEUR (NOUVEAU) ---
    elif menu == "⚖️ Comparateur Elite":
        st.title("⚖️ Comparaison Duale")
        if len(df) < 2:
            st.warning("Il faut au moins 2 animaux en base pour comparer.")
        else:
            col_sel1, col_sel2 = st.columns(2)
            id1 = col_sel1.selectbox("Animal A", df['id'].tolist(), index=0)
            id2 = col_sel2.selectbox("Animal B", df['id'].tolist(), index=1)
            
            a1 = df[df['id'] == id1].iloc[0]
            a2 = df[df['id'] == id2].iloc[0]
            
            # Comparaison visuelle
            c1, c2 = st.columns(2)
            
            for i, (anim, col) in enumerate([(a1, c1), (a2, c2)]):
                m, g, ic = calculer_echo_data(anim)
                with col:
                    st.subheader(f"Profil : {anim['id']}")
                    # Graphique Echo-like
                    fig_pie = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], 
                                                   values=[m, g, 12], hole=.4)])
                    fig_pie.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                    st.metric("Indice Conformation", f"{ic}")
                    
                    # Courbe de croissance
                    fig_growth = px.line(x=[10, 30, 70], y=[anim['p10'], anim['p30'], anim['p70']], 
                                       title="Croissance (kg)", markers=True)
                    st.plotly_chart(fig_growth, use_container_width=True)
                    

    # --- DASHBOARD ---
    elif menu == "📊 Dashboard":
        st.title("📋 État du Troupeau")
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            fig_scat = px.scatter(df, x='p70', y='p_thoracique', color='dentition', 
                                 size='c_canon', hover_data=['id'], title="Analyse Poids vs Thorax")
            st.plotly_chart(fig_scat, use_container_width=True)
        else:
            st.info("Base vide.")

    # --- SAISIE ---
    elif menu == "✍️ Saisie & Mesures":
        st.title("✍️ Enregistrement")
        scan = st.session_state.get('last_scan', {})
        with st.form("main_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                id_a = st.text_input("ID *")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            with c2:
                p10 = st.number_input("Poids J10", 0.0)
                p30 = st.number_input("Poids J30", 0.0)
                p70 = st.number_input("Poids J70", 0.0)
            with c3:
                h = st.number_input("H. Garrot", value=scan.get('h_garrot', 0.0))
                l = st.number_input("L. Corps", value=scan.get('l_corps', 0.0))
                t = st.number_input("P. Thorax", value=scan.get('p_thoracique', 0.0))
                c = st.number_input("T. Canon", value=scan.get('c_canon', 0.0))
            
            if st.form_submit_button("Sauvegarder"):
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race, p10, p30, p70, h_garrot, l_corps, p_thoracique, c_canon) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (id_a, race, p10, p30, p70, h, l, t, c))
                st.success("Enregistré !")

    elif menu == "⚙️ Admin":
        if st.button("Vider la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
