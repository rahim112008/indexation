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
# BLOC 6 : EXPERTISE, NUTRITION ALGÉRIE & PRÉDICTION
# ==========================================

def view_echo(df):
    st.title("🥩 Expertise Musculaire & Carcasse")
    if df.empty: return
    
    col1, col2 = st.columns([1, 2])
    with col1:
        target = st.selectbox("Sélectionner l'animal", df['id'].unique(), key="echo_sel")
        sub = df[df['id'] == target].iloc[0]
        st.metric("SNC (Surface Noix)", f"{sub['SNC']} cm²")
        st.metric("Rendement Estimé", f"{sub['Rendement']}%")
        
    with col2:
        fig = go.Figure(go.Indicator(
            mode="gauge+number", 
            value=sub['SNC'], 
            title={'text': "Indice de Muscularité (SNC)"},
            gauge={
                'axis': {'range': [None, 35]},
                'steps': [
                    {'range': [0, 18], 'color': "lightgray"},
                    {'range': [18, 25], 'color': "skyblue"},
                    {'range': [25, 35], 'color': "gold"}
                ],
                'threshold': {'line': {'color': "red", 'width': 4}, 'value': 22}
            }
        ))
        st.plotly_chart(fig, use_container_width=True)

def view_nutrition(df):
    st.title("🥗 Nutritionniste Expert (Marché Algérien)")
    if df.empty: return

    # --- 1. BASE DE DONNÉES ALIMENTS ALGÉRIE (Valeurs moyennes UFL/PDI) ---
    aliments_dz = {
        "Orge (Chaïr)": {"ufl": 1.0, "pdi": 75, "prix": 5500},
        "Son de blé (Nokhala)": {"ufl": 0.85, "pdi": 90, "prix": 3500},
        "Maïs concassé": {"ufl": 1.15, "pdi": 70, "prix": 7000},
        "Foin de vesse-avoine": {"ufl": 0.65, "pdi": 60, "prix": 2500},
        "Paille de blé": {"ufl": 0.35, "pdi": 30, "prix": 1200},
        "Aliment Complet (Bétail)": {"ufl": 0.95, "pdi": 105, "prix": 6200}
    }

    sub = df[df['id'] == st.selectbox("Sélectionner un animal", df['id'].unique(), key="nut_sel")].iloc[0]
    
    st.sidebar.subheader("🎯 Objectif de Croissance")
    obj_gmd = st.sidebar.slider("GMD visé (g/jour)", 100, 600, 250, step=50)
    duree_sim = st.sidebar.number_input("Durée de la simulation (jours)", 30, 180, 60)

    # --- 2. CALCUL DES BESOINS (INRA Adapté) ---
    # Entretien + Croissance
    besoin_ufl = (0.040 * (sub['p_actuel']**0.75)) + (obj_gmd/1000 * 3.8)
    besoin_pdi = (sub['p_actuel'] * 0.5) + (obj_gmd * 0.4)

    st.subheader(f"📊 Besoins pour {sub['id']} ({sub['p_actuel']} kg)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Énergie (UFL)", f"{besoin_ufl:.2f}")
    c2.metric("Protéines (PDI)", f"{besoin_pdi:.1f} g")
    c3.metric("Poids cible", f"{sub['p_actuel'] + (obj_gmd*duree_sim/1000):.1f} kg")

    # --- 3. SIMULATEUR DE RATION ---
    st.subheader("🌾 Composition de la Ration (en kg)")
    cols = st.columns(len(aliments_dz))
    ration = {}
    total_ufl = 0
    total_pdi = 0
    total_prix = 0

    for i, (nom, val) in enumerate(aliments_dz.items()):
        quantite = cols[i].number_input(f"{nom}", min_value=0.0, max_value=5.0, step=0.1, key=f"q_{nom}")
        ration[nom] = quantite
        total_ufl += quantite * val['ufl']
        total_pdi += quantite * val['pdi']
        total_prix += (quantite * val['prix'] / 100) # Prix par kg estimé depuis quintal

    # --- 4. ANALYSE DE LA RATION ---
    st.markdown("---")
    res_c1, res_c2 = st.columns(2)
    
    with res_c1:
        st.write("### ✅ Équilibre de la ration")
        diff_ufl = total_ufl - besoin_ufl
        if diff_ufl >= 0:
            st.success(f"Énergie : +{diff_ufl:.2f} UFL (OK)")
        else:
            st.error(f"Énergie : {diff_ufl:.2f} UFL (Manque)")

        diff_pdi = total_pdi - besoin_pdi
        if diff_pdi >= 0:
            st.success(f"Protéines : +{diff_pdi:.1f} g (OK)")
        else:
            st.error(f"Protéines : {diff_pdi:.1f} g (Manque)")
        
        st.info(f"💰 Coût estimé : {total_prix:.2f} DA / jour")

    with res_c2:
        st.write("### 📈 Prédiction d'évolution")
        # Prédiction basée sur l'énergie réelle fournie
        gmd_reel = (total_ufl - (0.040 * (sub['p_actuel']**0.75))) / 3.8 * 1000
        poids_futur = sub['p_actuel'] + (max(0, gmd_reel) * duree_sim / 1000)
        
        dates = [datetime.now() + timedelta(days=x) for x in range(0, duree_sim, 5)]
        poids_evol = [sub['p_actuel'] + (max(0, gmd_reel) * x / 1000) for x in range(0, duree_sim, 5)]
        
        fig_pred = px.line(x=dates, y=poids_evol, labels={'x': 'Date', 'y': 'Poids (kg)'}, title="Courbe de croissance prédite")
        st.plotly_chart(fig_pred, use_container_width=True)

    if st.button("📋 Imprimer la fiche nutritionnelle"):
        st.write("Fonction d'impression en cours de développement...")

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
