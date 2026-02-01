import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
from datetime import datetime
import time

# ==========================================
# 1. SYSTÈME DE DONNÉES (NOUVELLE VERSION V9)
# ==========================================
# Changement de nom de fichier pour éviter les erreurs de colonnes manquantes
DB_NAME = "expert_ovin_v9.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_db():
    with get_db_connection() as conn:
        # Création des tables avec la nouvelle structure flexible
        conn.execute("""CREATE TABLE IF NOT EXISTS beliers 
            (id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT, 
             source TEXT, date_entree DATE, age_entree_jours INTEGER)""")
        
        conn.execute("""CREATE TABLE IF NOT EXISTS mesures 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL, 
             p_base REAL, p_actuel REAL, h_garrot REAL, c_canon REAL, 
             p_thoracique REAL, l_corps REAL, date_mesure DATE)""")

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Rendement': 0.0}
    try:
        # On s'assure que les valeurs sont numériques
        p_actuel = float(row.get('p_actuel') or 0)
        p_base = float(row.get('p_base') or 0)
        hg = float(row.get('h_garrot') or 75)
        pt = float(row.get('p_thoracique') or 90)
        cc = float(row.get('c_canon') or 9)
        
        # Calcul du GMD (Gain Moyen Quotidien)
        if p_actuel > p_base > 0:
            res['GMD'] = round(((p_actuel - p_base) / 30) * 1000) # Basé sur un cycle de 30 jours
            
        ic = (pt / (cc * hg)) * 1000
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p_actuel*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        return pd.Series(res)
    except: 
        return pd.Series(res)

def load_data():
    init_db()
    try:
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
    except Exception as e:
        st.error(f"Erreur de lecture base de données : {e}")
        return pd.DataFrame()

# ==========================================
# 2. DASHBOARD & ALERTES
# ==========================================
def view_dashboard(df):
    st.title("🏆 Dashboard & Suivi des Pesées")
    
    if df.empty:
        st.info("Aucun animal enregistré. Allez dans 'Indexation' pour commencer.")
        return

    # Gestion des Alertes de Pesée
    st.subheader("📢 Rappels de pesée")
    today = datetime.now().date()
    col_alert, col_stats = st.columns([2, 1])
    
    with col_alert:
        has_alerts = False
        for _, row in df.iterrows():
            if row['date_mesure']:
                last_date = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date()
                jours_ecoules = (today - last_date).days
                if jours_ecoules >= 30:
                    st.warning(f"⚖️ **ID {row['id']}** : À peser (Dernière pesée il y a {jours_ecoules} jours)")
                    has_alerts = True
        if not has_alerts:
            st.success("✅ Tous les contrôles de poids sont à jour.")

    # Section Élites
    st.markdown("---")
    st.subheader("🌟 Classement des Élites")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Top Croissance (GMD)**")
        st.dataframe(df[df['GMD']>0][['id', 'sexe', 'GMD']].sort_values('GMD', ascending=False), use_container_width=True)
    with c2:
        st.write("**Top Carcasse (Rendement %)**")
        st.dataframe(df[['id', 'Rendement', 'Muscle']].sort_values('Rendement', ascending=False), use_container_width=True)

# ==========================================
# 3. SCANNER & INDEXATION (FLEXIBLE)
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan Biométrique")
    img = st.camera_input("Scanner l'animal")
    if img:
        with st.spinner("Analyse IA en cours..."):
            time.sleep(1)
            # Simulation des mesures extraites par le scan
            st.session_state['last_scan'] = {"h_garrot": 77.5, "p_thoracique": 93.0, "l_corps": 86.5, "c_canon": 9.1}
            st.success("✅ Mesures biométriques prêtes pour l'indexation.")

def view_indexation():
    st.title("✍️ Indexation & Entrée en Stock")
    scan_data = st.session_state.get('last_scan', {})

    source = st.radio("Provenance de l'animal :", ["Né à la ferme", "Acheté à l'extérieur"], horizontal=True)

    # Détermination de l'âge
    st.markdown("### ⏳ Information sur l'âge")
    c_age1, c_age2 = st.columns(2)
    with c_age1:
        methode = st.radio("Saisie par :", ["Dents", "Mois", "Jours"], horizontal=True)
    with c_age2:
        if methode == "Dents":
            dents = st.selectbox("Dentition", ["Lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            jours_estimes = 180
        elif methode == "Mois":
            m = st.number_input("Nombre de mois", 1, 60, 4)
            jours_estimes = m * 30
            dents = f"{m} mois"
        else:
            jours_estimes = st.number_input("Âge exact (jours)", 1, 2000, 70)
            dents = "Saisie Jours"

    st.markdown("---")
    with st.form("form_index"):
        col1, col2 = st.columns(2)
        id_animal = col1.text_input("Identifiant (Boucle) *")
        sexe = col2.selectbox("Catégorie / Sexe", ["Bélier", "Brebis", "Agneau", "Agnelle"])
        
        cp1, cp2 = st.columns(2)
        if source == "Né à la ferme":
            p_base = cp1.number_input("Poids sevrage (P30)", value=15.0)
            p_actuel = cp2.number_input("Poids actuel (P70)", value=30.0)
        else:
            p_base = cp1.number_input("Poids à l'achat (kg)", value=35.0)
            p_actuel = cp2.number_input("Poids ce jour (kg)", value=35.0)

        st.markdown("📏 **Mensurations (Auto-remplies par Scan)**")
        m1, m2, m3 = st.columns(3)
        hg = m1.number_input("Garrot (cm)", value=float(scan_data.get('h_garrot', 75.0)))
        pt = m2.number_input("Thorax (cm)", value=float(scan_data.get('p_thoracique', 90.0)))
        cc = m3.number_input("Canon (cm)", value=float(scan_data.get('c_canon', 9.0)))
        
        if st.form_submit_button("💾 ENREGISTRER L'ANIMAL"):
            if id_animal:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?)", 
                                 (id_animal, "Race Locale", sexe, dents, source, datetime.now().date(), jours_estimes))
                    conn.execute("INSERT INTO mesures (id_animal, p_base, p_actuel, h_garrot, c_canon, p_thoracique, date_mesure) VALUES (?,?,?,?,?,?,?)",
                                 (id_animal, p_base, p_actuel, hg, cc, pt, datetime.now().date()))
                st.success(f"Animal {id_animal} enregistré !")
                st.rerun()
            else:
                st.error("L'identifiant est obligatoire.")

# ==========================================
# 4. NUTRITION & ECHO
# ==========================================
def view_nutrition(df):
    st.title("🥗 Simulateur de Ration")
    if df.empty: return
    target = st.selectbox("Sélectionner l'animal", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]
    
    obj_gmd = st.slider("Objectif de gain (g/j)", 100, 500, 250)
    besoin = round((0.035 * (sub['p_actuel']**0.75)) + (obj_gmd/1000)*3.5, 2)
    
    st.info(f"Besoin pour {target} : {besoin} UFL / jour")
    
    c1, c2 = st.columns(2)
    orge = c1.number_input("Orge (kg)", 0.5)
    luzerne = c2.number_input("Luzerne (kg)", 1.0)
    apport = round((orge*1.05) + (luzerne*0.65), 2)
    
    st.metric("Apport Total", f"{apport} UFL", delta=round(apport-besoin, 2))

def view_echo(df):
    st.title("🥩 Echo-Composition")
    if df.empty: return
    target = st.selectbox("Animal à expertiser", df['id'].unique(), key="echo_sel")
    sub = df[df['id'] == target].iloc[0]
    
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Muscle Estimé", f"{sub['Muscle']}%")
    col_m2.metric("Rendement Carcasse", f"{sub['Rendement']}%")
    
    fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], 
                                 values=[sub['Muscle'], sub['Gras'], sub['Os']], hole=.4)])
    st.plotly_chart(fig)

# ==========================================
# 5. ADMINISTRATION
# ==========================================
def view_admin():
    st.title("🔧 Administration")
    if st.button("🗑️ Réinitialiser toute la base de données"):
        import os
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            st.success("Base de données supprimée. Veuillez rafraîchir la page.")
            st.rerun()

# ==========================================
# MAIN
# ==========================================
def main():
    st.set_page_config(layout="wide", page_title="Expert Ovin V9")
    df = load_data()
    
    st.sidebar.title("💎 EXPERT OVIN V9")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition", "🔧 Admin"])
    
    if menu == "🏠 Dashboard": view_dashboard(df)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Composition": view_echo(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)
    elif menu == "🔧 Admin": view_admin()

if __name__ == "__main__":
    main()
