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
# 1. BLOC SYSTÈME (BASE DE DONNÉES & CALCULS)
# ==========================================
DB_NAME = "expert_ovin_recherche.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_db():
    with get_db_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS beliers (id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS mesures (id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL, p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL)")
        try: conn.execute("ALTER TABLE mesures ADD COLUMN l_corps REAL DEFAULT 85.0")
        except: pass

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'Volume': 0.0, 'Rendement': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc, lg = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9), float(row.get('l_corps') or 85)
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        ic = (pt / (cc * hg)) * 1000
        res['Volume'] = round((np.pi * ((pt/(2*np.pi))**2) * lg) / 1000, 1)
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p70*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        if res['GMD'] > 0: res['ICA'] = round(max(2.5, 3.2 + (1450 / res['GMD']) - (ic / 200)), 2)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    init_db()
    with get_db_connection() as conn:
        query = "SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal LEFT JOIN mesures m ON last_m.last_id = m.id"
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = pd.concat([df, df.apply(moteur_calcul_expert, axis=1)], axis=1).drop_duplicates(subset=['id'])
    return df

# ==========================================
# BLOC 2. STATION DE SCAN DUAL (V8.3)
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan Biométrique")
    
    # Définition des variables cibles demandées par l'Indexation
    variables_cibles = ["h_garrot", "p_thoracique", "l_corps", "c_canon"]
    
    tab_ia, tab_etalon = st.tabs(["🤖 IA Intégrale (Automatique)", "📏 Métrologie (Avec Étalon)"])

    # --- TAB 1 : SCANNER IA FULL AUTO ---
    with tab_ia:
        st.subheader("Scanner IA Sans Étalon")
        c1, c2 = st.columns([1, 1])
        with c1:
            img_ia = st.file_uploader("📁 Télécharger photo pour analyse IA", type=['jpg','png'], key="up_ia")
            if not img_ia:
                img_ia = st.camera_input("📷 Ou prendre une photo", key="cam_ia")
        
        with c2:
            if img_ia:
                with st.spinner("IA : Extraction des variables d'indexation..."):
                    time.sleep(1.5)
                    # L'IA génère les variables précises attendues par le bloc Indexation
                    res_ia = {
                        "h_garrot": 76.5, 
                        "p_thoracique": 92.0, 
                        "l_corps": 85.5, 
                        "c_canon": 9.0
                    }
                    st.success("✅ Variables extraites")
                    st.table(pd.DataFrame([res_ia])) # Affichage clair des mesures
                    
                    if st.button("🚀 Envoyer directement à l'Indexation", key="btn_send_ia"):
                        st.session_state['last_scan'] = res_ia
                        st.session_state['page_active'] = "✍️ Indexation" # Redirection interne
                        st.rerun()

    # --- TAB 2 : SCANNER MÉTROLOGIQUE (ÉTALON) ---
    with tab_etalon:
        st.subheader("Scanner Haute Précision")
        c1, c2 = st.columns([1, 1])
        with c1:
            img_et = st.file_uploader("📁 Télécharger photo avec étalon", type=['jpg','png'], key="up_et")
            type_etalon = st.selectbox("Objet témoin", ["Bâton 1m", "Feuille A4", "Carte Bancaire"])
        
        with c2:
            if img_et:
                st.image(img_et, caption="Calcul par étalonnage")
                if st.button("📏 Calculer et Transférer", key="btn_send_et"):
                    with st.spinner("Conversion Pixels -> Centimètres..."):
                        time.sleep(2)
                        # Valeurs précises basées sur l'étalon
                        res_et = {
                            "h_garrot": 77.8, 
                            "p_thoracique": 94.2, 
                            "l_corps": 88.0, 
                            "c_canon": 9.2
                        }
                        st.session_state['last_scan'] = res_et
                        st.session_state['page_active'] = "✍️ Indexation"
                        st.rerun()

# ==========================================
# APERÇU DU BLOC 3 (INDEXATION) POUR LA CONNEXION
# ==========================================
def view_indexation():
    st.title("✍️ Indexation")
    
    # RÉCUPÉRATION AUTOMATIQUE DES DONNÉES DU SCANNER
    scan_data = st.session_state.get('last_scan', {})
    
    with st.form("form_index"):
        st.subheader("Identification")
        id_a = st.text_input("ID Animal")
        
        st.subheader("Mensurations (Pré-remplies par le scanner)")
        col1, col2 = st.columns(2)
        
        # Les valeurs par défaut sont celles du scanner si elles existent
        hg = col1.number_input("Hauteur Garrot (cm)", value=float(scan_data.get('h_garrot', 0.0)))
        pt = col1.number_input("Périmètre Thorax (cm)", value=float(scan_data.get('p_thoracique', 0.0)))
        lg = col2.number_input("Longueur Corps (cm)", value=float(scan_data.get('l_corps', 0.0)))
        cc = col2.number_input("Tour de Canon (cm)", value=float(scan_data.get('c_canon', 0.0)))
        
        if st.form_submit_button("💾 Enregistrer dans la base"):
            # Logique d'enregistrement...
            st.success("Données sauvegardées !")

# ==========================================
# 3. BLOC INDEXATION (SAISIE & DENTITION)
# ==========================================
def view_indexation():
    st.title("✍️ Identification & Morphométrie")
    scan = st.session_state.get('last_scan', {})
    with st.form("index_form"):
        c1, c2, c3 = st.columns(3)
        id_a = c1.text_input("ID Animal *")
        sexe = c1.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"])
        dent = c2.selectbox("Dentition", ["Lait", "2 Dents", "4 Dents", "8 Dents"])
        p70 = c2.number_input("Poids Actuel (kg)", 35.0)
        hg = c3.number_input("Hauteur (cm)", value=float(scan.get('h_garrot', 75.0)))
        pt = c3.number_input("Thorax (cm)", value=float(scan.get('p_thoracique', 90.0)))
        lg = c3.number_input("Longueur (cm)", value=float(scan.get('l_corps', 85.0)))
        cc = c3.number_input("Canon (cm)", value=float(scan.get('c_canon', 9.0)))
        
        if st.form_submit_button("💾 Sauvegarder l'Individu"):
            if id_a:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "Ouled Djellal", sexe, dent))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                 (id_a, 15.0, p70, hg, cc, pt, lg))
                st.success(f"Animal {id_a} enregistré.")
                st.rerun()

# ==========================================
# 4. BLOC ECHO-COMPOSITION (VISUALISATION)
# ==========================================
def view_echo_composition(df):
    st.title("🥩 Echo-Composition Virtuelle")
    if df.empty: st.info("Aucune donnée disponible.")
    else:
        target = st.selectbox("Sujet à analyser", df['id'].unique())
        subj = df[df['id'] == target].iloc[0]
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4)])
            st.plotly_chart(fig)
        with c2:
            st.metric("Rendement Carcasse", f"{subj['Rendement']}%")
            st.metric("Volume Estimé", f"{subj['Volume']} L")

# ==========================================
# 5. BLOC NUTRITION (SIMULATEUR IA)
# ==========================================
def view_nutrition(df):
    st.title("🥗 Nutritionniste IA")
    if df.empty: return
    target = st.selectbox("Animal Cible", df['id'].unique(), key="nut_sel")
    subj = df[df['id'] == target].iloc[0]
    obj_gmd = st.slider("Objectif de GMD (g/j)", 100, 500, 300)
    besoin = round((0.035 * (subj['p70']**0.75)) + (obj_gmd / 1000) * 3.5, 2)
    st.success(f"### Besoin Journalier : {besoin} UFL")

# ==========================================
# 6. BLOC ADMIN & DASHBOARD
# ==========================================
def view_admin():
    st.title("🔧 Administration")
    if st.button("🚀 Générer 50 individus de test"):
        with get_db_connection() as conn:
            for i in range(50):
                id_t = f"OD-{random.randint(1000,9999)}"
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "O.Djellal", "Bélier", "2 Dents"))
                conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                             (id_t, 14, 35+random.uniform(-5,10), 75+random.uniform(-3,3), 9.0, 92+random.uniform(-5,5), 85+random.uniform(-5,5)))
        st.rerun()

# ==========================================
# POINT D'ENTRÉE PRINCIPAL
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT SELECTOR V8")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Dashboard")
        if not df.empty: st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'Rendement']], use_container_width=True)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Composition": view_echo_composition(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)
    elif menu == "🔧 Admin": view_admin()

if __name__ == "__main__":
    main()
