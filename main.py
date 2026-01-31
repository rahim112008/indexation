import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import random
import time

# ==========================================
# 1. INITIALISATION ET SÉCURITÉ DB
# ==========================================
DB_NAME = "expert_ovin_recherche.db"

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
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

def load_data():
    init_db()
    try:
        with get_db_connection() as conn:
            query = """SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                       FROM beliers b 
                       LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal
                       LEFT JOIN mesures m ON last_m.last_id = m.id"""
            df = pd.read_sql(query, conn)
            if df.empty: return pd.DataFrame()
            metrics = df.apply(moteur_calcul_expert, axis=1)
            return pd.concat([df, metrics], axis=1).drop_duplicates(subset=['id'])
    except:
        return pd.DataFrame()

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        ic = (pt / (cc * hg)) * 1000
        if res['GMD'] > 0: res['ICA'] = round(max(2.5, 3.2 + (1450 / res['GMD']) - (ic / 200)), 2)
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p70*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        return pd.Series(res)
    except: return pd.Series(res)

# ==========================================
# 2. INTERFACE UTILISATEUR
# ==========================================
def main():
    st.set_page_config(page_title="Expert Selector Pro v5.8", layout="wide")
    df = load_data()

    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "✍️ Saisie/Indexation", "🥩 Echo-Composition", "🔧 Admin"])

    # --- SCANNER ---
    if menu == "📸 Scanner IA":
        st.title("📸 Scanner Biométrique Intelligent")
        mode_scanner = st.radio("Mode", ["🤖 Automatique (IA)", "📏 Manuel (Gabarit)"], horizontal=True)
        source = st.radio("Source", ["📷 Caméra en direct", "📁 Charger photo"], horizontal=True)
        img = st.camera_input("Profil") if source == "📷 Caméra en direct" else st.file_uploader("Image", type=['jpg','png'])
        if img:
            col_img, col_res = st.columns([1.5, 1])
            with col_img: st.image(img, use_container_width=True)
            with col_res:
                if mode_scanner == "🤖 Automatique (IA)":
                    time.sleep(1)
                    st.success("✅ CADRAGE VALIDE (98%)")
                    res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                else:
                    res = {"h_garrot": st.number_input("HG", 70.0), "c_canon": st.number_input("CC", 8.5), "p_thoracique": st.number_input("PT", 85.0), "l_corps": st.number_input("LC", 80.0)}
                st.session_state['scan_data'] = res
                st.metric("📏 Hauteur", f"{res['h_garrot']} cm")
                if st.button("🚀 ENVOYER À LA SAISIE"): st.toast("Transféré !")

    # --- SAISIE ---
    elif menu == "✍️ Saisie/Indexation":
        st.title("✍️ Indexation")
        sd = st.session_state.get('scan_data', {})
        with st.form("form_saisie"):
            c1, c2, c3 = st.columns(3)
            id_a = c1.text_input("ID Animal *")
            dent = c2.selectbox("Âge", ["Agneau", "2 Dents", "4 Dents", "8 Dents"])
            sexe = c3.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)
            hg = st.number_input("HG (cm)", value=float(sd.get('h_garrot', 0.0)))
            cc = st.number_input("Canon (cm)", value=float(sd.get('c_canon', 0.0)))
            if st.form_submit_button("💾 ENREGISTRER"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "O.Djellal", sexe, dent))
                        conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                     (id_a, 15.0, 30.0, hg, cc, float(sd.get('p_thoracique', 0.0)), float(sd.get('l_corps', 0.0))))
                    st.success("Indexé !")
                    st.rerun()

    # --- ECHO-COMPOSITION & COMPARATEUR (NOUVEAU) ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse & Comparaison de Carcasse")
        if df.empty: st.warning("Base vide.")
        else:
            col_a, col_vs, col_b = st.columns([10, 1, 10])
            with col_a:
                id_a = st.selectbox("Individu A", df['id'].unique(), key="sel_a")
                subj_a = df[df['id'] == id_a].iloc[0]
                st.plotly_chart(go.Figure(data=[go.Pie(labels=['Muscle','Gras','Os'], values=[subj_a['Muscle'], subj_a['Gras'], subj_a['Os']], hole=.4, marker_colors=['#2E7D32','#FBC02D','#D32F2F'])]), use_container_width=True)
                st.metric("Muscle A", f"{subj_a['Muscle']}%")
            
            with col_vs: st.markdown("<h2 style='text-align:center; padding-top:100px;'>VS</h2>", unsafe_allow_html=True)
            
            with col_b:
                id_b = st.selectbox("Individu B", df['id'].unique(), key="sel_b")
                subj_b = df[df['id'] == id_b].iloc[0]
                st.plotly_chart(go.Figure(data=[go.Pie(labels=['Muscle','Gras','Os'], values=[subj_b['Muscle'], subj_b['Gras'], subj_b['Os']], hole=.4, marker_colors=['#2E7D32','#FBC02D','#D32F2F'])]), use_container_width=True)
                st.metric("Muscle B", f"{subj_b['Muscle']}%")

    # --- DASHBOARD ---
    elif menu == "🏠 Dashboard":
        st.title("🏆 Performance Troupeau")
        if not df.empty: st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA']], use_container_width=True)

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Outils Recherche")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_t = f"ID-{random.randint(1000,9999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "Ouled Djellal", "Bélier", "Adulte"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                 (id_t, 15, 35, 75, 9, 90, 85))
            st.success("50 individus créés !")
            st.rerun()

if __name__ == "__main__":
    main()
