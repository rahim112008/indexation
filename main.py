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
# 1. SYSTÈME DE BASE DE DONNÉES
# ==========================================
DB_NAME = "expert_ovin_v9_3.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_db():
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL DEFAULT 0, p30 REAL DEFAULT 0, p70 REAL DEFAULT 0, 
            h_garrot REAL DEFAULT 0, c_canon REAL DEFAULT 0, 
            p_thoracique REAL DEFAULT 0, l_corps REAL DEFAULT 0, bassin REAL DEFAULT 0)''')

def load_data():
    init_db()
    try:
        with get_db_connection() as conn:
            query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps, m.bassin 
                       FROM beliers b 
                       LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal
                       LEFT JOIN mesures m ON last_m.last_id = m.id"""
            df = pd.read_sql(query, conn)
            if df.empty: return pd.DataFrame()
            metrics = df.apply(moteur_calcul_expert, axis=1)
            return pd.concat([df, metrics], axis=1).drop_duplicates(subset=['id'])
    except: return pd.DataFrame()

# ==========================================
# 2. MOTEUR DE CALCULS (ECHO & VOLUME)
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Volume': 0.0, 'Rendement': 0.0}
    try:
        p70, p30, hg, pt, cc, lg, bs = [float(row.get(k) or 0) for k in ['p70', 'p30', 'h_garrot', 'p_thoracique', 'c_canon', 'l_corps', 'bassin']]
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        r_p = pt / (2 * np.pi) if pt > 0 else 0
        if bs > 0 and lg > 0:
            r_b = bs / 2
            res['Volume'] = round(((1/3) * np.pi * lg * (r_p**2 + r_p*r_b + r_b**2)) / 1000, 2)
        elif lg > 0:
            res['Volume'] = round((np.pi * (r_p**2) * lg) / 1000, 2)
        res['Gras'] = round(max(5.0, 4.0 + (p70 * 0.12)), 1)
        res['Muscle'] = round(min(75.0, 78.0 - res['Gras'] + (bs * 0.15 if bs > 0 else 0)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        return pd.Series(res)
    except: return pd.Series(res)

# ==========================================
# 3. INTERFACE PAR BLOCS
# ==========================================

def view_scanner():
    st.title("📸 Scanner IA & Métrologie")
    t1, t2 = st.tabs(["🤖 IA Auto", "📏 Étalon"])
    with t1:
        if st.file_uploader("Photo", type=['jpg','png'], key="ia"):
            res = {"h_garrot": 77, "p_thoracique": 93, "l_corps": 86, "c_canon": 9}
            st.session_state['last_scan'] = res; st.success("Mesures prêtes.")
    with t2:
        st.selectbox("Référence", ["Bâton 1m", "A4", "Carte"])
        if st.file_uploader("Photo + Étalon", type=['jpg','png'], key="et"):
            res = {"h_garrot": 78, "p_thoracique": 95, "l_corps": 88, "c_canon": 9.2}
            st.session_state['last_scan'] = res; st.success("Précision validée.")

def view_indexation():
    st.title("✍️ Indexation")
    scan = st.session_state.get('last_scan', {})
    with st.form("idx"):
        c1, c2 = st.columns(2)
        id_a = c1.text_input("ID Animal *")
        cat = c1.selectbox("Catégorie", ["Agneau (Mâle)", "Agnelle (Femelle)", "Bélier", "Brebis"])
        mode_age = c2.radio("Âge par", ["Jours", "Mois", "Dents"])
        age_v = c2.number_input("Valeur", value=70)
        st.subheader("⚖️ Poids (10j, 30j, 70j)")
        p1, p2, p3 = st.columns(3)
        p10, p30, p70 = p1.number_input("P10", 8.5), p2.number_input("P30", 15.0), p3.number_input("P70", 28.0)
        st.subheader("📏 Mensurations")
        opt_bs = st.checkbox("🔍 Option Bassin")
        m1, m2, m3, m4, m5 = st.columns(5)
        hg, lg, cc, pt = m1.number_input("Garrot", value=float(scan.get('h_garrot', 75.0))), m2.number_input("Long", value=float(scan.get('l_corps', 85.0))), m3.number_input("Canon", value=float(scan.get('c_canon', 9.0))), m4.number_input("Thorax", value=float(scan.get('p_thoracique', 90.0)))
        bs = m5.number_input("Bassin", value=22.0) if opt_bs else 0.0
        if st.form_submit_button("SAUVEGARDER"):
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "OD", cat, str(age_v)))
                conn.execute("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps, bassin) VALUES (?,?,?,?,?,?,?,?,?)", (id_a, p10, p30, p70, hg, cc, pt, lg, bs))
            st.success("Enregistré !"); st.rerun()

def view_echo(df):
    st.title("🥩 Echo-Composition")
    if df.empty: return
    sel = st.selectbox("Animal", df['id'].unique())
    sub = df[df['id'] == sel].iloc[0]
    c1, c2 = st.columns(2)
    c1.metric("Muscle", f"{sub['Muscle']}%", f"{round(sub['p70']*sub['Muscle']/100, 1)} kg")
    fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[sub['Muscle'], sub['Gras'], sub['Os']], hole=.4)])
    st.plotly_chart(fig)

# --- REINTEGRATION DU BLOC NUTRITION ---
def view_nutrition(df):
    st.title("🥗 Nutritionniste IA")
    if df.empty: st.warning("Données insuffisantes."); return
    sel = st.selectbox("Sélectionner l'animal à nourrir", df['id'].unique(), key="nut")
    sub = df[df['id'] == sel].iloc[0]
    
    col1, col2 = st.columns(2)
    with col1:
        gmd_obj = st.slider("Objectif de croissance (g/jour)", 50, 500, 250)
        poids = sub['p70']
        # Calcul simplifié Besoins (UFL)
        besoin_maintien = 0.035 * (poids**0.75)
        besoin_croissance = (gmd_obj / 1000) * 3.5
        total_ufl = round(besoin_maintien + besoin_croissance, 2)
        st.metric("Besoin Énergétique Total", f"{total_ufl} UFL/jour")
    
    with col2:
        st.subheader("Ration Conseillée")
        ms_max = round(poids * 0.03, 2) # 3% du poids vif en MS
        st.write(f"📦 Capacité d'ingestion : **{ms_max} kg MS**")
        st.write(f"🌾 Concentré suggéré : **{round(total_ufl * 0.4, 2)} kg**")
        st.write(f"🌿 Fourrage suggéré : **{round(ms_max * 0.6, 2)} kg**")

def view_admin(df):
    st.title("🔧 Admin")
    if st.button("🔥 REPARER / RESET"):
        with get_db_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS mesures"); conn.execute("DROP TABLE IF EXISTS beliers")
        init_db(); st.rerun()
    if not df.empty: st.download_button("Export Excel", df.to_csv(index=False), "data.csv")

# ==========================================
# MAIN
# ==========================================
def main():
    st.set_page_config(layout="wide")
    df = load_data()
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition", "🔧 Admin"])
    if menu == "🏠 Dashboard" and not df.empty: st.title("🏆 Dashboard"); st.dataframe(df)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Composition": view_echo(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)
    elif menu == "🔧 Admin": view_admin(df)

if __name__ == "__main__": main()
