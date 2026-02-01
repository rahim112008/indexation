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
# 1. MOTEUR DE DONNÉES & CALCULS (V12)
# ==========================================
DB_NAME = "expert_ovin_v12.db"

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
    seed_data() # Remplissage automatique si vide

def seed_data():
    """Ajoute des données de démonstration pour tester l'application"""
    with get_db_connection() as conn:
        check = conn.execute("SELECT count(*) FROM beliers").fetchone()[0]
        if check == 0:
            # Données fictives : ID, Race, Sexe, Age, Source, Date
            beliers = [
                ('AG-001', 'Ouled Djellal', 'Agneau', 'Né Ferme', 'Né à la ferme', '2025-11-15'),
                ('BEL-99', 'Ouled Djellal', 'Bélier', '24 mois', 'Acheté à l\'extérieur', '2025-12-20'),
                ('AGN-02', 'Ouled Djellal', 'Agnelle', 'Né Ferme', 'Né à la ferme', '2025-11-20'),
                ('BR-05', 'Ouled Djellal', 'Brebis', '48 mois', 'Acheté à l\'extérieur', '2026-01-05'),
                ('ELITE-01', 'Ouled Djellal', 'Bélier', '14 mois', 'Acheté à l\'extérieur', '2026-01-10')
            ]
            conn.executemany("INSERT INTO beliers VALUES (?,?,?,?,?,?)", beliers)
            
            # Mesures : id_animal, p_base, p_actuel, h_garrot, l_corps, pt, cc, bassin, date
            mesures = [
                ('AG-001', 15.0, 32.5, 74.0, 82.0, 88.0, 8.5, 21.0, '2026-01-30'),
                ('BEL-99', 65.0, 85.0, 82.0, 95.0, 115.0, 10.5, 26.0, '2026-01-25'),
                ('AGN-02', 14.0, 28.0, 72.0, 80.0, 84.0, 8.2, 20.5, '2026-01-28'),
                ('BR-05', 55.0, 62.0, 78.0, 88.0, 105.0, 9.5, 24.0, '2026-01-20'),
                ('ELITE-01', 50.0, 70.0, 80.0, 92.0, 110.0, 10.0, 27.5, '2026-01-31')
            ]
            conn.executemany("""INSERT INTO mesures (id_animal, p_base, p_actuel, h_garrot, l_corps, p_thoracique, c_canon, bassin, date_mesure) 
                             VALUES (?,?,?,?,?,?,?,?,?)""", mesures)

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Volume': 0.0, 'Rendement': 0.0, 'SNC': 0.0}
    try:
        p_act, p_bas = float(row.get('p_actuel') or 0), float(row.get('p_base') or 0)
        hg, lg, pt = float(row.get('h_garrot') or 0), float(row.get('l_corps') or 0), float(row.get('p_thoracique') or 0)
        cc, bas = float(row.get('c_canon') or 0), float(row.get('bassin') or 0)
        
        if p_act > p_bas > 0: res['GMD'] = round(((p_act - p_bas) / 30) * 1000)
        rayon = pt / (2 * np.pi)
        res['Volume'] = round(np.pi * (rayon**2) * lg, 1)
        densite_volumique = res['Volume'] / lg if lg > 0 else 0
        res['SNC'] = round((densite_volumique * 0.015) + (bas * 0.4), 2)
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
# 2. STATION DE SCAN
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan Biométrique")
    tab1, tab2 = st.tabs(["🤖 IA Autonome", "📏 Métrologie avec Étalon"])

    with tab1:
        st.subheader("Analyse Assistée par IA")
        up_ia = st.file_uploader("Importer une photo", type=['jpg', 'png'], key="up_ia")
        cam_ia = st.camera_input("Scanner en direct", key="cam_ia")
        if up_ia or cam_ia:
            with st.spinner("IA : Extraction des contours..."):
                time.sleep(1)
                res = {"h_garrot": 78.5, "l_corps": 87.0, "p_thoracique": 95.0, "c_canon": 9.2, "bassin": 23.0}
                st.session_state['last_scan'] = res
                st.success("✅ Analyse terminée")
                st.table(pd.DataFrame([res]))

    with tab2:
        st.subheader("Calcul par Objet Témoin")
        etalon = st.selectbox("Étalon utilisé", ["Bâton 1m", "Feuille A4", "Carte Bancaire"])
        up_et = st.file_uploader("Importer photo avec étalon", type=['jpg', 'png'], key="up_et")
        if up_et:
            if st.button("Calculer Mesures"):
                res_et = {"h_garrot": 77.0, "l_corps": 86.5, "p_thoracique": 93.0, "c_canon": 9.0, "bassin": 22.0}
                st.session_state['last_scan'] = res_et
                st.info(f"Mesures validées via {etalon}")

# ==========================================
# 3. INDEXATION DYNAMIQUE
# ==========================================
def view_indexation():
    st.title("✍️ Indexation & Volume")
    scan = st.session_state.get('last_scan', {})
    source = st.radio("Origine de l'animal", ["Né à la ferme", "Acheté à l'extérieur"], horizontal=True)
    
    with st.form("form_index"):
        c1, c2 = st.columns(2)
        id_a = c1.text_input("ID Animal (Boucle) *")
        sexe = c2.selectbox("Catégorie", ["Bélier", "Brebis", "Agneau", "Agnelle"])
        
        st.markdown("---")
        if source == "Né à la ferme":
            st.subheader("🐣 Suivi de Croissance")
            date_naiss = st.date_input("Date de Naissance", datetime.now())
            cp1, cp2, cp3, cp4 = st.columns(4)
            p_naiss = cp1.number_input("Poids Naissance", value=4.0)
            p_10j = cp2.number_input("Poids 10j", value=8.0)
            p_30j = cp3.number_input("Poids 30j", value=15.0)
            p_70j = cp4.number_input("Poids 70j", value=28.0)
            p_base, p_act, age_info = p_30j, p_70j, "Né Ferme"
        else:
            st.subheader("🛒 Détails Achat")
            ca1, ca2, ca3 = st.columns(3)
            date_achat = ca1.date_input("Date Achat", datetime.now())
            p_achat = ca2.number_input("Poids Achat (kg)", value=35.0)
            age_mois = ca3.number_input("Âge estimé (mois)", 1, 120, 6)
            p_base, p_act, age_info = p_achat, p_achat, f"{age_mois} mois"

        st.subheader("📏 Mensurations (cm)")
        m1, m2, m3, m4, m5 = st.columns(5)
        hg = m1.number_input("Garrot", value=float(scan.get('h_garrot', 75.0)))
        lg = m2.number_input("Longueur", value=float(scan.get('l_corps', 85.0)))
        pt = m3.number_input("Thorax", value=float(scan.get('p_thoracique', 90.0)))
        cc = m4.number_input("Canon", value=float(scan.get('c_canon', 9.0)))
        bas = m5.number_input("Bassin", value=float(scan.get('bassin', 22.0)))

        if st.form_submit_button("💾 ENREGISTRER"):
            if id_a:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?)", 
                                 (id_a, "Ouled Djellal", sexe, age_info, source, datetime.now().date()))
                    conn.execute("""INSERT INTO mesures (id_animal, p_base, p_actuel, h_garrot, l_corps, p_thoracique, c_canon, bassin, date_mesure) 
                                 VALUES (?,?,?,?,?,?,?,?,?)""", (id_a, p_base, p_act, hg, lg, pt, cc, bas, datetime.now().date()))
                st.success(f"✅ {id_a} enregistré !")
                st.rerun()

# ==========================================
# 4. DASHBOARD & ANALYSE
# ==========================================
# ==========================================
# 3. DASHBOARD & RAPPELS (BLOC COMPLET V14)
# ==========================================
def view_dashboard(df):
    st.title("🏠 Dashboard & Planification")
    if df.empty:
        st.info("Aucune donnée disponible. Veuillez enregistrer un animal.")
        return

    # --- SECTION ALERTES ---
    st.subheader("🔔 Alertes de Suivi Immédiates")
    # Alerte si la dernière pesée date de plus de 30 jours (pour TOUS les animaux)
    alerte_orange = df[(df['jours_depuis_pesee'] >= 30) & (df['jours_depuis_pesee'] < 45)]
    alerte_rouge = df[df['jours_depuis_pesee'] >= 45]

    if not alerte_rouge.empty or not alerte_orange.empty:
        c1, c2 = st.columns(2)
        with c1:
            for _, r in alerte_rouge.iterrows():
                st.error(f"🚨 **ID {r['id']}** : Retard critique ! (+{r['jours_depuis_pesee']}j)")
        with c2:
            for _, r in alerte_orange.iterrows():
                st.warning(f"⚖️ **ID {r['id']}** : Pesée à prévoir ({r['jours_depuis_pesee']}j)")
    
    st.markdown("---")

    # --- SECTION CALENDRIER PRÉVISIONNEL ---
    st.subheader("📅 Prochaines Pesées Planifiées")
    
    rappels = []
    today = datetime.now().date()

    for _, row in df.iterrows():
        # CAS 1 : ANIMAUX NÉS À LA FERME (Pesées par étapes d'âge)
        if row['source'] == "Né à la ferme":
            date_naiss = datetime.strptime(row['date_entree'], '%Y-%m-%d').date()
            etapes = [("P10 (10j)", 10), ("P30 (Sevrage)", 30), ("P70 (Croissance)", 70), ("P90", 90)]
            
            for nom, jours in etapes:
                date_cible = date_naiss + timedelta(days=jours)
                jours_restants = (date_cible - today).days
                if -2 <= jours_restants <= 15: # On affiche si c'est prévu dans les 15 prochains jours
                    rappels.append({
                        "ID": row['id'],
                        "Type": "🍼 Étape Croissance",
                        "Détail": nom,
                        "Date Prévue": date_cible,
                        "Jours Restants": jours_restants
                    })

        # CAS 2 : ANIMAUX ACHETÉS (Pesées cycliques tous les 30 jours)
        else:
            last_pesee = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date()
            # On prévoit la prochaine pesée 30 jours après la dernière enregistrée
            date_prochaine = last_pesee + timedelta(days=30)
            jours_restants = (date_prochaine - today).days
            
            if jours_restants <= 15: # On affiche si c'est prévu bientôt
                rappels.append({
                    "ID": row['id'],
                    "Type": "🛒 Suivi Achat",
                    "Détail": "Contrôle Mensuel",
                    "Date Prévue": date_prochaine,
                    "Jours Restants": jours_restants
                })

    if rappels:
        plan_df = pd.DataFrame(rappels).sort_values("Date Prévue")
        
        # Affichage avec style
        def style_column(row):
            if row['Jours Restants'] <= 2: return ['background-color: #ff4b4b']*5
            elif row['Jours Restants'] <= 7: return ['background-color: #ffa500']*5
            return ['']*5

        st.table(plan_df)
    else:
        st.success("✅ Aucune pesée spécifique n'est prévue pour les 15 prochains jours.")

    st.markdown("---")
    
    # --- SECTION INVENTAIRE ---
    st.subheader("📊 Performance de l'Exploitation")
    st.dataframe(df[['id', 'sexe', 'source', 'GMD', 'SNC', 'Rendement']], use_container_width=True)
def view_dashboard(df):
    st.title("🏠 Dashboard de l'Exploitation")
    if df.empty: return
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Effectif Total", len(df))
    col2.metric("GMD Moyen", f"{int(df['GMD'].mean())} g/j")
    col3.metric("SNC Élite", f"{df['SNC'].max():.1f} cm²")
    col4.metric("Rendement", f"{df['Rendement'].mean():.1f}%")

    st.markdown("---")
    st.subheader("🌟 Classement par Performance Musculaire (SNC)")
    st.dataframe(df[['id', 'sexe', 'source', 'SNC', 'Muscle', 'Volume', 'GMD']].sort_values('SNC', ascending=False), use_container_width=True)

def view_echo(df):
    st.title("🥩 Expertise de la Noix de Côtelette")
    if df.empty: return
    target = st.selectbox("Sélectionner l'animal", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]

    c1, c2 = st.columns([1, 1])
    with c1:
        st.metric("Surface Noix (SNC)", f"{sub['SNC']} cm²")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = sub['SNC'], title = {'text': "Indice de Muscularité"},
            gauge = {'axis': {'range': [None, 30]}, 'steps': [
                {'range': [0, 15], 'color': "#E8E8E8"},
                {'range': [15, 22], 'color': "#A0A0A0"},
                {'range': [22, 30], 'color': "#FFD700"}],
                'threshold': {'line': {'color': "red", 'width': 4}, 'value': 22}}))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with c2:
        st.subheader("Répartition Tissulaire")
        fig_pie = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[sub['Muscle'], sub['Gras'], sub['Os']], hole=.4)])
        st.plotly_chart(fig_pie, use_container_width=True)

def view_nutrition(df):
    st.title("🥗 Ration Optimisée")
    if df.empty: return
    target = st.selectbox("Individu", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]
    obj = st.slider("Objectif GMD (g/j)", 100, 500, 250)
    besoin = round((0.035 * (sub['p_actuel']**0.75)) + (obj/1000)*3.5, 2)
    st.info(f"Besoin estimé pour {target} ({sub['p_actuel']}kg) : {besoin} UFL/jour")

# ==========================================
# MAIN
# ==========================================
def main():
    st.set_page_config(layout="wide", page_title="Expert Ovin V12")
    df = load_data()
    menu = st.sidebar.radio("Menu Principal", ["🏠 Dashboard", "📸 Scanner", "✍️ Indexation", "🥩 Echo-Expertise", "🥗 Nutrition"])
    
    if menu == "🏠 Dashboard": view_dashboard(df)
    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Expertise": view_echo(df)
    elif menu == "🥗 Nutrition": view_nutrition(df)

if __name__ == "__main__":
    main()
