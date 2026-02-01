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
# BLOC 1 : CONFIGURATION & BASE DE DONNÉES
# ==========================================
DB_NAME = "expert_ovin_v15.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try: yield conn; conn.commit()
    except Exception as e: conn.rollback(); raise e
    finally: conn.close()

def init_db():
    with get_db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS beliers 
            (id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT, 
             source TEXT, date_entree DATE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS mesures 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL, 
             p_base REAL, p_actuel REAL, h_garrot REAL, l_corps REAL, 
             p_thoracique REAL, c_canon REAL, bassin REAL, date_mesure DATE)""")
    seed_data()

def seed_data():
    """Données de test pour activer les alertes dès le premier lancement"""
    with get_db_connection() as conn:
        check = conn.execute("SELECT count(*) FROM beliers").fetchone()[0]
        if check == 0:
            today = datetime.now().date()
            # Un animal à jour, un en retard, un critique
            d_ok = (today - timedelta(days=10)).strftime('%Y-%m-%d')
            d_warn = (today - timedelta(days=35)).strftime('%Y-%m-%d')
            d_crit = (today - timedelta(days=50)).strftime('%Y-%m-%d')
            
            beliers = [
                ('AG-TEST-01', 'Ouled Djellal', 'Agneau', 'Né Ferme', 'Né à la ferme', (today - timedelta(days=20)).strftime('%Y-%m-%d')),
                ('BEL-TEST-02', 'Ouled Djellal', 'Bélier', '24 mois', 'Acheté à l\'extérieur', d_warn),
                ('ELITE-TEST-03', 'Ouled Djellal', 'Bélier', '14 mois', 'Acheté à l\'extérieur', d_crit)
            ]
            conn.executemany("INSERT INTO beliers VALUES (?,?,?,?,?,?)", beliers)
            
            mesures = [
                ('AG-TEST-01', 15.0, 22.0, 74.0, 82.0, 88.0, 8.5, 21.0, d_ok),
                ('BEL-TEST-02', 65.0, 70.0, 82.0, 95.0, 115.0, 10.5, 26.0, d_warn),
                ('ELITE-TEST-03', 50.0, 60.0, 80.0, 92.0, 110.0, 10.0, 27.5, d_crit)
            ]
            conn.executemany("""INSERT INTO mesures (id_animal, p_base, p_actuel, h_garrot, l_corps, p_thoracique, c_canon, bassin, date_mesure) 
                             VALUES (?,?,?,?,?,?,?,?,?)""", mesures)

# ==========================================
# BLOC 2 : MOTEUR DE CALCULS EXPERTS
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Volume': 0.0, 'Rendement': 0.0, 'SNC': 0.0, 'jours_depuis_pesee': 0}
    try:
        p_act, p_bas = float(row.get('p_actuel') or 0), float(row.get('p_base') or 0)
        hg, lg, pt = float(row.get('h_garrot') or 0), float(row.get('l_corps') or 0), float(row.get('p_thoracique') or 0)
        cc, bas = float(row.get('c_canon') or 0), float(row.get('bassin') or 0)
        
        # Calcul de l'ancienneté de la pesée
        if row['date_mesure']:
            last_date = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date()
            res['jours_depuis_pesee'] = (datetime.now().date() - last_date).days

        # Calcul GMD, Volume et SNC
        if p_act > p_bas > 0: res['GMD'] = round(((p_act - p_bas) / 30) * 1000)
        rayon = pt / (2 * np.pi)
        res['Volume'] = round(np.pi * (rayon**2) * lg, 1)
        densite_volumique = res['Volume'] / lg if lg > 0 else 0
        res['SNC'] = round((densite_volumique * 0.015) + (bas * 0.4), 2)
        
        # Carcasse
        ic = (pt / (cc * hg)) * 1000 if cc > 0 else 0
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p_act*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    init_db()
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p_base, m.p_actuel, m.h_garrot, m.l_corps, m.p_thoracique, m.c_canon, m.bassin, m.date_mesure 
                   FROM beliers b 
                   LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal 
                   LEFT JOIN mesures m ON last_m.last_id = m.id"""
        df = pd.read_sql(query, conn)
    if not df.empty:
        df_calc = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, df_calc], axis=1).drop_duplicates(subset=['id'])
    return df

# ==========================================
# BLOC 3 : DASHBOARD (AVEC ALERTES & RAPPELS)
# ==========================================
def view_dashboard(df):
    st.title("🏠 Dashboard & Planification")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    # --- ALERTES RETARDS ---
    st.subheader("🔔 Alertes Retards de Pesée")
    a_orange = df[(df['jours_depuis_pesee'] >= 30) & (df['jours_depuis_pesee'] < 45)]
    a_rouge = df[df['jours_depuis_pesee'] >= 45]

    if not a_rouge.empty or not a_orange.empty:
        c1, c2 = st.columns(2)
        with c1:
            for _, r in a_rouge.iterrows():
                st.error(f"🚨 **ID {r['id']}** : Critique ! (+{r['jours_depuis_pesee']}j)")
        with c2:
            for _, r in a_orange.iterrows():
                st.warning(f"⚖️ **ID {r['id']}** : À peser ({r['jours_depuis_pesee']}j)")
    
    st.markdown("---")

    # --- RAPPELS PROCHAINES PESÉES ---
    st.subheader("📅 Prochaines Pesées Planifiées (15 prochains jours)")
    rappels = []
    today = datetime.now().date()

    for _, row in df.iterrows():
        # Cas 1 : Nés à la ferme (Etapes fixes)
        if row['source'] == "Né à la ferme":
            d_naiss = datetime.strptime(row['date_entree'], '%Y-%m-%d').date()
            for nom, j in [("P10", 10), ("P30 (Sevrage)", 30), ("P70", 70), ("P90", 90)]:
                d_cible = d_naiss + timedelta(days=j)
                diff = (d_cible - today).days
                if -1 <= diff <= 15:
                    rappels.append({"ID": row['id'], "Type": "🐣 Étape", "Détail": nom, "Date": d_cible, "Jours": diff})
        
        # Cas 2 : Achetés (Cycle 30 jours)
        else:
            d_last = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date()
            d_next = d_last + timedelta(days=30)
            diff = (d_next - today).days
            if diff <= 15:
                rappels.append({"ID": row['id'], "Type": "🛒 Achat", "Détail": "Suivi Mensuel", "Date": d_next, "Jours": diff})

    if rappels:
        st.table(pd.DataFrame(rappels).sort_values("Date"))
    else:
        st.success("✅ Aucune pesée spécifique prévue bientôt.")

# ==========================================
# BLOC 4 : SCANNER (IA & ÉTALON)
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan")
    tab1, tab2 = st.tabs(["🤖 IA", "📏 Étalon"])
    with tab1:
        if st.camera_input("Scanner l'animal"):
            st.session_state['last_scan'] = {"h_garrot": 78.0, "l_corps": 85.0, "p_thoracique": 92.0, "c_canon": 9.5, "bassin": 23.0}
            st.success("Analyse IA terminée !")
    with tab2:
        if st.file_uploader("Importer photo avec étalon"):
            if st.button("Calculer"):
                st.session_state['last_scan'] = {"h_garrot": 76.0, "l_corps": 84.0, "p_thoracique": 90.0, "c_canon": 9.0, "bassin": 22.5}

# ==========================================
# 5. INDEXATION & MORPHOMÉTRIE (VERSION DYNAMIQUE)
# ==========================================
def view_indexation():
    st.title("✍️ Indexation & Volume")
    scan = st.session_state.get('last_scan', {})
    
    # Choix de l'origine
    source = st.radio("Origine de l'animal", ["Né à la ferme", "Acheté à l'extérieur"], horizontal=True)
    
    with st.form("form_index"):
        c1, c2 = st.columns(2)
        id_a = c1.text_input("ID Animal (Boucle) *")
        sexe = c2.selectbox("Catégorie", ["Bélier", "Brebis", "Agneau", "Agnelle"])
        
        st.markdown("---")
        
        # --- CAS 1 : NÉ À LA FERME ---
        if source == "Né à la ferme":
            st.subheader("🐣 Suivi de Croissance (Naissance -> 70j)")
            col_date, col_vide = st.columns(2)
            date_naiss = col_date.date_input("Date de Naissance", datetime.now())
            
            cp1, cp2, cp3, cp4 = st.columns(4)
            p_naiss = cp1.number_input("Poids Naissance", value=4.0)
            p_10j = cp2.number_input("Poids 10j", value=8.0)
            p_30j = cp3.number_input("Poids 30j (Sevrage)", value=15.0)
            p_70j = cp4.number_input("Poids 70j", value=28.0)
            
            # Pour la compatibilité base de données
            p_base = p_30j
            p_act = p_70j
            age_info = "Né Ferme"

        # --- CAS 2 : ACHETÉ À L'EXTÉRIEUR ---
        else:
            st.subheader("🛒 Détails de l'Achat")
            ca1, ca2, ca3 = st.columns(3)
            date_achat = ca1.date_input("Date d'Achat", datetime.now())
            p_achat = ca2.number_input("Poids à l'Achat (kg)", value=35.0)
            age_mois = ca3.number_input("Âge estimé (en mois)", min_value=1, max_value=120, value=6)
            
            p_base = p_achat
            p_act = p_achat # Au jour de l'achat, le poids actuel est le poids d'achat
            age_info = f"{age_mois} mois"

        st.markdown("---")
        st.subheader("📏 Mensurations Biométriques (cm)")
        m1, m2, m3, m4, m5 = st.columns(5)
        # On récupère les valeurs du scan s'il existe, sinon valeurs par défaut
        hg = m1.number_input("Garrot", value=float(scan.get('h_garrot', 75.0)))
        lg = m2.number_input("Longueur", value=float(scan.get('l_corps', 85.0)))
        pt = m3.number_input("Thorax", value=float(scan.get('p_thoracique', 90.0)))
        cc = m4.number_input("Canon", value=float(scan.get('c_canon', 9.0)))
        bas = m5.number_input("Bassin", value=float(scan.get('bassin', 22.0)))

        # Bouton d'enregistrement
        if st.form_submit_button("💾 ENREGISTRER L'INDIVIDU"):
            if id_a:
                with get_db_connection() as conn:
                    # Sauvegarde profil
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?)", 
                                 (id_a, "Ouled Djellal", sexe, age_info, source, datetime.now().date()))
                    
                    # Sauvegarde mesures
                    conn.execute("""INSERT INTO mesures 
                                 (id_animal, p_base, p_actuel, h_garrot, l_corps, p_thoracique, c_canon, bassin, date_mesure) 
                                 VALUES (?,?,?,?,?,?,?,?,?)""",
                                 (id_a, p_base, p_act, hg, lg, pt, cc, bas, datetime.now().date()))
                
                st.success(f"✅ Fiche de l'animal {id_a} créée avec succès !")
                # Optionnel : On vide le scan après enregistrement
                if 'last_scan' in st.session_state: del st.session_state['last_scan']
                st.rerun()
            else:
                st.error("⚠️ Veuillez entrer un identifiant (Boucle).")

# ==========================================
# BLOC 6 : EXPERTISE & NUTRITION
# ==========================================
def view_echo(df):
    st.title("🥩 Expertise Musculaire")
    if df.empty: return
    sub = df[df['id'] == st.selectbox("Animal", df['id'].unique())].iloc[0]
    st.metric("Surface Noix (SNC)", f"{sub['SNC']} cm²")
    fig = go.Figure(go.Indicator(mode="gauge+number", value=sub['SNC'], title={'text': "Muscularité"}, gauge={'axis':{'range':[None,30]}}))
    st.plotly_chart(fig)

def view_nutrition(df):
    st.title("🥗 Ration")
    if df.empty: return
    sub = df[df['id'] == st.selectbox("Animal ", df['id'].unique())].iloc[0]
    obj = st.slider("Objectif GMD (g/j)", 100, 500, 250)
    ufl = round((0.035 * (sub['p_actuel']**0.75)) + (obj/1000)*3.5, 2)
    st.info(f"Besoin : {ufl} UFL/jour")

# ==========================================
# MAIN : NAVIGATION
# ==========================================
def main():
    st.set_page_config(layout="wide", page_title="Expert Ovin V15")
    df = load_data()
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Expertise", "🥗 Nutrition"])
    
    if menu == "🏠 Dashboard": view_dashboard(df)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Expertise": view_echo(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)

if __name__ == "__main__":
    main()
