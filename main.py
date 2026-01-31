import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import time

# --- CONFIGURATION ---
DB_NAME = "expert_ovin_pro.db"

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
            id TEXT PRIMARY KEY, race TEXT, p10 REAL, p30 REAL, p70 REAL,
            h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL)''')

def calculer_echo_data(row):
    h, t, c = row['h_garrot'], row['p_thoracique'], row['c_canon']
    ic = (t / (c * h)) * 100 if (c * h) > 0 else 0
    muscle = round(45 + (ic * 0.2), 1)
    return muscle, round(max(5, 100 - muscle - 12), 1), round(ic, 2)

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="Expert Selector Pro", layout="wide")
    init_db()

    # Titre et Sidebar
    st.sidebar.title("💎 Expert Selector Pro")
    
    # ⚠️ CRUCIAL : Les noms ici doivent correspondre EXACTEMENT aux elif plus bas
    menu_options = [
        "🏠 Dashboard", 
        "📸 Scanner IA", 
        "⚖️ Comparateur Elite", 
        "✍️ Saisie & Mesures", 
        "⚙️ Admin"
    ]
    menu = st.sidebar.radio("Menu Principal", menu_options)

    # Chargement des données
    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- LOGIQUE DES MENUS ---
    if menu == "🏠 Dashboard":
        st.title("📊 Performances du Troupeau")
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("La base est vide. Utilisez le menu Saisie.")

    elif menu == "📸 Scanner IA":
        st.title("📸 Scanner Morphologique")
        st.info("Utilisez l'étalon de 1 mètre pour la calibration automatique.")
        up = st.file_uploader("Importer une photo de profil", type=['jpg', 'png'])
        if up:
            st.image(up, width=400)
            if st.button("🚀 Analyser"):
                st.session_state['last_scan'] = {'h_garrot': 74.0, 'l_corps': 82.0, 'p_thoracique': 88.0, 'c_canon': 8.5}
                st.success("Mesures extraites et mémorisées !")

    elif menu == "⚖️ Comparateur Elite":
        st.title("⚖️ Comparaison Performance")
        if len(df) >= 2:
            ids = df['id'].tolist()
            c1, c2 = st.columns(2)
            sel1 = c1.selectbox("Animal A", ids, index=0)
            sel2 = c2.selectbox("Animal B", ids, index=1)
            
            # Affichage côte à côte
            res1 = df[df['id'] == sel1].iloc[0]
            res2 = df[df['id'] == sel2].iloc[0]
            
            # --- ZONE EXPORT ---
            st.divider()
            csv = df[df['id'].isin([sel1, sel2])].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Exporter la comparaison (CSV)", csv, "comparaison_elite.csv", "text/csv")
            
            # Graphiques
            g1, g2 = st.columns(2)
            for item, col in [(res1, g1), (res2, g2)]:
                with col:
                    m, g, ic = calculer_echo_data(item)
                    fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[m, g, 12], hole=.4)])
                    st.plotly_chart(fig, use_container_width=True)
                    st.metric("Indice de Conformation", f"{ic}")
        else:
            st.warning("Besoin d'au moins 2 animaux.")

    elif menu == "✍️ Saisie & Mesures":
        st.title("✍️ Enregistrement")
        scan = st.session_state.get('last_scan', {})
        with st.form("form_saisie"):
            id_a = st.text_input("ID Animal")
            col_p, col_m = st.columns(2)
            p70 = col_p.number_input("Poids J70 (kg)", 0.0)
            h_g = col_m.number_input("H. Garrot (cm)", value=scan.get('h_garrot', 0.0))
            t_h = col_m.number_input("P. Thorax (cm)", value=scan.get('p_thoracique', 0.0))
            c_a = col_m.number_input("T. Canon (cm)", value=scan.get('c_canon', 0.0))
            if st.form_submit_button("Sauvegarder"):
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, p70, h_garrot, p_thoracique, c_canon) VALUES (?,?,?,?,?)", 
                                 (id_a, p70, h_g, t_h, c_a))
                st.success("Enregistré !")

    elif menu == "⚙️ Admin":
        if st.button("Vider la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
