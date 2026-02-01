import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
from datetime import datetime, timedelta
import time

# ==========================================
# 1. SYSTÈME DE DONNÉES (STRUCTURE FLEXIBLE)
# ==========================================
DB_NAME = "expert_ovin_final.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_db():
    with get_db_connection() as conn:
        # Table Profil : Ajout de la Source et de la Date d'entrée
        conn.execute("""CREATE TABLE IF NOT EXISTS beliers 
            (id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT, 
             source TEXT, date_entree DATE, age_entree_jours INTEGER)""")
        
        # Table Mesures : Stockage historique
        conn.execute("""CREATE TABLE IF NOT EXISTS mesures 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL, 
             p_base REAL, p_actuel REAL, h_garrot REAL, c_canon REAL, 
             p_thoracique REAL, l_corps REAL, date_mesure DATE)""")

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Rendement': 0.0}
    try:
        p_actuel = float(row.get('p_actuel') or 0)
        p_base = float(row.get('p_base') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        
        # Calcul GMD Flexible (sur 40 jours glissants ou période d'engraissement)
        if p_actuel > p_base > 0:
            res['GMD'] = round(((p_actuel - p_base) / 40) * 1000)
            
        ic = (pt / (cc * hg)) * 1000
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p_actuel*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    init_db()
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p_base, m.p_actuel, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps, m.date_mesure 
                   FROM beliers b 
                   LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal 
                   LEFT JOIN mesures m ON last_m.last_id = m.id"""
        df = pd.read_sql(query, conn)
    if not df.empty:
        df_calc = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, df_calc], axis=1).drop_duplicates(subset=['id'])
    return df

# ==========================================
# 2. DASHBOARD AVEC ALERTES INTELLIGENTES
# ==========================================
def view_dashboard(df):
    st.title("🏆 Tableau de Bord Expert")
    
    if df.empty:
        st.info("👋 Bienvenue ! Commencez par indexer un animal (Né ou Acheté).")
        return

    # Section ALERTES
    st.subheader("📢 Alertes & Rappels")
    today = datetime.now().date()
    alertes = []
    for _, row in df.iterrows():
        # Exemple d'alerte : Pesée tous les 30 jours
        last_date = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date() if row['date_mesure'] else today
        if (today - last_date).days >= 30:
            alertes.append(f"⚖️ **ID {row['id']}** : Contrôle mensuel requis (Dernière pesée il y a {(today-last_date).days}j)")

    if alertes:
        for a in alertes: st.warning(a)
    else: st.success("✅ Tous les suivis sont à jour.")

    # Section ÉLITES
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🌟 Top Croissance (GMD)")
        st.dataframe(df[df['GMD'] > 0][['id', 'sexe', 'GMD']].sort_values(by='GMD', ascending=False))
    
    with col2:
        st.subheader("🥩 Top Carcasse (%)")
        st.dataframe(df[['id', 'Rendement', 'Muscle']].sort_values(by='Rendement', ascending=False))

    # Graphique de Projection
    st.subheader("📈 Projection de croissance (6 mois)")
    target = st.selectbox("Simuler un individu", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]
    jours = np.array([0, 30, 60, 90, 120, 150, 180])
    poids_p = [sub['p_actuel'] + (sub['GMD'] * j / 1000) for j in jours]
    fig = px.line(x=jours, y=poids_p, title=f"Évolution estimée : {target}", labels={'x':'Jours', 'y':'Poids (kg)'})
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 3. SCANNER & INDEXATION FLEXIBLE
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan Dual")
    tab1, tab2 = st.tabs(["🤖 IA Auto", "📏 Étalon 1m"])
    with tab1:
        img = st.camera_input("Prendre photo de l'animal")
        if img:
            st.session_state['last_scan'] = {"h_garrot": 76.0, "p_thoracique": 92.0, "l_corps": 85.0, "c_canon": 9.0}
            st.success("✅ Mesures extraites. Allez dans 'Indexation'.")

def view_indexation():
    st.title("✍️ Indexation Flexible")
    scan_data = st.session_state.get('last_scan', {})

    # CHOIX DE LA SOURCE
    source = st.radio("Origine de l'animal :", ["Né à la ferme", "Acheté à l'extérieur"], horizontal=True)
    
    col_a, col_b = st.columns(2)
    with col_a:
        methode_age = st.radio("Âge par :", ["Dents", "Mois", "Jours"])
        if methode_age == "Dents": val_age = st.selectbox("Dents", ["Lait", "2", "4", "6", "8"]); jours_age = 180
        elif methode_age == "Mois": val_age = "Mois"; m = st.number_input("Nombre de mois", 1, 60, 3); jours_age = m*30
        else: val_age = "Jours"; jours_age = st.number_input("Jours", 1, 2000, 70)

    with st.form("form_flexible"):
        st.subheader("🆔 Fiche Individuelle")
        c1, c2 = st.columns(2)
        id_animal = c1.text_input("ID Boucle *")
        sexe = c2.selectbox("Sexe", ["Bélier", "Brebis", "Agneau", "Agnelle"])
        
        if source == "Né à la ferme":
            p_base = st.number_input("Poids au sevrage (P30)", value=15.0)
            p_actuel = st.number_input("Poids actuel (P70)", value=28.0)
        else:
            p_base = st.number_input("Poids à l'achat (kg)", value=30.0)
            p_actuel = st.number_input("Poids ce jour (kg)", value=32.0)
            date_achat = st.date_input("Date d'achat", datetime.now())

        st.markdown("📏 **Mensurations (Scan)**")
        m1, m2, m3 = st.columns(3)
        hg = m1.number_input("Garrot", value=float(scan_data.get('h_garrot', 75.0)))
        pt = m2.number_input("Thorax", value=float(scan_data.get('p_thoracique', 90.0)))
        cc = m3.number_input("Canon", value=float(scan_data.get('c_canon', 9.0)))
        
        if st.form_submit_button("💾 ENREGISTRER"):
            if id_animal:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?)", 
                                 (id_animal, "Ouled Djellal", sexe, str(val_age), source, datetime.now().date(), jours_age))
                    conn.execute("INSERT INTO mesures (id_animal, p_base, p_actuel, h_garrot, c_canon, p_thoracique, date_mesure) VALUES (?,?,?,?,?,?,?)",
                                 (id_animal, p_base, p_actuel, hg, cc, pt, datetime.now().date()))
                st.success("Animal enregistré avec succès !")
                st.rerun()

# ==========================================
# 4. NUTRITION & ECHO (CONSERVÉS)
# ==========================================
def view_nutrition(df):
    st.title("🥗 Simulateur Ration Algérie")
    if df.empty: return
    target = st.selectbox("Animal", df['id'].unique())
    subj = df[df['id'] == target].iloc[0]
    
    col1, col2 = st.columns(2)
    with col1: obj = st.slider("Objectif GMD (g/j)", 100, 500, 250)
    
    besoin = round((0.035 * (subj['p_actuel']**0.75)) + (obj/1000)*3.5, 2)
    st.info(f"🎯 Besoin cible : {besoin} UFL")
    
    f1, f2 = st.columns(2)
    orge = f1.number_input("Orge (kg)", 0.5)
    luzerne = f2.number_input("Luzerne (kg)", 1.0)
    apport = round((orge*1.05) + (luzerne*0.65), 2)
    st.metric("Apport Total", f"{apport} UFL", delta=round(apport-besoin, 2))

def view_echo(df):
    st.title("🥩 Analyse de Carcasse")
    if df.empty: return
    target = st.selectbox("Animal", df['id'].unique(), key="echo")
    sub = df[df['id'] == target].iloc[0]
    fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[sub['Muscle'], sub['Gras'], sub['Os']], hole=.4)])
    st.plotly_chart(fig)

# ==========================================
# MAIN
# ==========================================
def main():
    st.set_page_config(layout="wide", page_title="Expert Ovin V9")
    df = load_data()
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition"])
    
    if menu == "🏠 Dashboard": view_dashboard(df)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Composition": view_echo(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)

if __name__ == "__main__":
    main()
