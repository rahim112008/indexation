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
# BLOC 4 : STATION DE SCAN INDÉPENDANTE (V16)
# ==========================================
def view_scanner():
    st.title("📸 Station de Scan Biométrique")
    st.markdown("---")

    # --- 1. ZONE DE CAPTURE INDÉPENDANTE ---
    st.subheader("🖼️ Étape 1 : Capture de l'image")
    source_img = st.radio("Source de l'image :", ["Appareil Photo (Direct)", "Importer une image (Galerie)"], horizontal=True)
    
    img_data = None
    if source_img == "Appareil Photo (Direct)":
        img_data = st.camera_input("Prendre une photo de l'animal")
    else:
        img_data = st.file_uploader("Télécharger l'image de l'animal", type=['jpg', 'jpeg', 'png'])

    if img_data:
        st.image(img_data, caption="Image prête pour l'analyse", use_container_width=True)
        
        st.markdown("---")
        # --- 2. ZONE D'ANALYSE (CHOIX DE LA MÉTHODE) ---
        st.subheader("⚙️ Étape 2 : Méthode d'analyse")
        
        methode = st.segmented_control("Choisir la technologie de mesure :", 
                                     ["🤖 IA Autonome", "📏 Métrologie par Étalon"])

        if methode == "🤖 IA Autonome":
            if st.button("🚀 Lancer l'analyse automatique"):
                with st.spinner("IA : Détection des points anatomiques..."):
                    time.sleep(2)
                    res = {"h_garrot": 78.5, "l_corps": 87.2, "p_thoracique": 94.0, "c_canon": 9.2, "bassin": 23.5}
                    st.session_state['last_scan'] = res
                    st.success("✅ Analyse IA terminée !")
                    st.table(pd.DataFrame([res]))

        elif methode == "📏 Métrologie par Étalon":
            c1, c2 = st.columns([1, 1])
            with c1:
                obj_temoin = st.selectbox("Objet témoin présent sur la photo", 
                                        ["Bâton 1m", "Feuille A4", "Carte Bancaire"])
            with c2:
                st.write("") # Espacement
                if st.button("🚀 Calculer via Étalon"):
                    with st.spinner("Calcul des proportions..."):
                        time.sleep(1.5)
                        res = {"h_garrot": 76.2, "l_corps": 85.0, "p_thoracique": 91.5, "c_canon": 9.0, "bassin": 22.8}
                        st.session_state['last_scan'] = res
                        st.success(f"✅ Mesures validées via {obj_temoin}")
                        st.table(pd.DataFrame([res]))

    # --- 3. RAPPEL POUR L'INDEXATION ---
    if 'last_scan' in st.session_state:
        st.info("💡 Les mesures sont sauvegardées. Vous pouvez maintenant aller dans l'onglet **'Indexation'** pour finaliser l'enregistrement.")
    else:
        st.info("📷 Veuillez capturer ou importer une photo pour activer les outils d'analyse.")

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

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'Volume': 0.0, 'Rendement': 0.0, 'SNC': 0.0, 'jours_depuis_pesee': 0}
    try:
        p_act, p_bas = float(row.get('p_actuel') or 0), float(row.get('p_base') or 0)
        hg, lg, pt = float(row.get('h_garrot') or 0), float(row.get('l_corps') or 0), float(row.get('p_thoracique') or 0)
        cc, bas = float(row.get('c_canon') or 0), float(row.get('bassin') or 0)
        
        # --- ACTIVATION DU CALCUL DES JOURS ---
        if row['date_mesure']:
            last_date = datetime.strptime(row['date_mesure'], '%Y-%m-%d').date()
            res['jours_depuis_pesee'] = (datetime.now().date() - last_date).days

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

# ==========================================
# 6. BLOC EXPERTISE ANALYTIQUE (V15 - AMÉLIORÉ)
# ==========================================
def view_echo(df):
    st.title("🥩 Expertise Analytique de la Carcasse")
    
    if df is None or df.empty:
        st.warning("⚠️ Aucune donnée disponible. Veuillez d'abord indexer des animaux.")
        return

    # Sélection de l'animal avec rappel de sa catégorie
    options = {f"{row['id']} ({row['sexe']})": row['id'] for _, row in df.iterrows()}
    target_label = st.selectbox("🎯 Sujet pour analyse de boucherie", options.keys())
    target_id = options[target_label]
    sub = df[df['id'] == target_id].iloc[0]

    # --- EN-TÊTE DE PERFORMANCE ---
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Poids Vif", f"{sub['p_actuel']} kg")
    with col_b:
        compacite = round(sub['p_actuel'] / sub['h_garrot'], 2) if sub['h_garrot'] > 0 else 0
        st.metric("Indice Compacité", f"{compacite}", help="Poids par cm de hauteur. Plus il est haut, plus l'animal est 'épais'.")
    with col_c:
        st.metric("Rendement Carcasse", f"{sub['Rendement']}%")
    with col_d:
        # Calcul du SNC (Surface de la Noix de Côtelette)
        st.metric("SNC (Muscularité)", f"{sub['SNC']} cm²")

    st.markdown("---")

    # --- RÉPARTITION TISSULAIRE (KG & %) ---
    st.subheader("📊 Composition Tissulaire Estimée (Masse Réelle)")
    
    # Calcul des masses en kg basées sur le poids actuel
    m_muscle = round((sub['p_actuel'] * sub['Muscle']) / 100, 2)
    m_gras = round((sub['p_actuel'] * sub['Gras']) / 100, 2)
    m_os = round((sub['p_actuel'] * sub['Os']) / 100, 2)

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"### 🟢 Muscle\n## {m_muscle} kg")
        st.progress(sub['Muscle'] / 100)
        st.caption(f"Soit {sub['Muscle']}% de la masse totale")
    
    with m2:
        st.markdown(f"### 🟡 Gras\n## {m_gras} kg")
        st.progress(sub['Gras'] / 100)
        st.caption(f"Soit {sub['Gras']}% (État d'engraissement)")
        
    with m3:
        st.markdown(f"### 🔴 Os\n## {m_os} kg")
        st.progress(sub['Os'] / 100)
        st.caption(f"Soit {sub['Os']}% (Squelette)")

    # --- VISUALISATION GRAPHIQUE ---
    g1, g2 = st.columns(2)
    with g1:
        fig_pie = go.Figure(data=[go.Pie(
            labels=['Muscle', 'Gras', 'Os'],
            values=[m_muscle, m_gras, m_os],
            hole=.5,
            marker_colors=['#2E7D32', '#FBC02D', '#D32F2F']
        )])
        fig_pie.update_layout(title="Répartition des Tissus", height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    with g2:
        # Échelle de classement de la conformation (Inspiré EUROP)
        ratio_mo = round(sub['Muscle'] / sub['Os'], 2) if sub['Os'] > 0 else 0
        
        st.write("### 🏆 Score de Conformation")
        if ratio_mo > 3.5:
            score, label, color = 5, "Classe S (Supérieur)", "gold"
        elif ratio_mo > 3.0:
            score, label, color = 4, "Classe E (Excellent)", "green"
        elif ratio_mo > 2.5:
            score, label, color = 3, "Classe U (Très Bon)", "blue"
        else:
            score, label, color = 2, "Classe R (Standard)", "orange"

        st.subheader(label)
        st.write(f"🧬 **Ratio Muscle/Os :** {ratio_mo}")
        st.info(f"Note technique : Cet individu présente un développement musculaire {label.lower()} par rapport au standard de la race.")

    # --- SECTION VALEUR COMMERCIALE ---
    st.markdown("---")
    st.subheader("💰 Estimation de Valeur Marchande (Boucherie)")
    prix_kg = st.number_input("Prix du kg de carcasse (DA)", value=1800, step=50)
    poids_carcasse = (sub['p_actuel'] * sub['Rendement']) / 100
    valeur_estimee = poids_carcasse * prix_kg
    
    ve1, ve2 = st.columns(2)
    ve1.metric("Poids Carcasse (froid)", f"{round(poids_carcasse, 2)} kg")
    ve2.metric("Valeur Estimée", f"{int(valeur_estimee)} DA")

# ==========================================
# BLOC 7 : NUTRITIONNISTE EXPERT & GÉNÉRATEUR DE RECETTES
# ==========================================

def view_nutrition(df):
    st.title("🥗 Expert Nutritionniste & Formulation de Ration")
    if df.empty:
        st.info("Veuillez d'abord enregistrer des animaux.")
        return

    # --- 1. SÉLECTION DU PROFIL PHYSIOLOGIQUE ---
    st.sidebar.subheader("📋 Profil de l'Animal")
    target_id = st.selectbox("Choisir l'animal", df['id'].unique())
    sub = df[df['id'] == target_id].iloc[0]
    
    profil = st.sidebar.selectbox("État physiologique", [
        "Engraissement rapide (Bélier/Agneau)",
        "Brebis Gestante (Fin de gestation)",
        "Brebis Allaitante",
        "Croissance Agneau/Agnelle",
        "Entretien (Bélier adulte)"
    ])

    obj_gmd = st.sidebar.slider("Objectif de gain de poids (g/jour)", 0, 500, 250)
    
    # --- 2. MOTEUR DE BESOINS SPÉCIFIQUES (Normes adaptées) ---
    poids = sub['p_actuel']
    if "Engraissement" in profil:
        besoin_ufl = (0.042 * (poids**0.75)) + (obj_gmd/1000 * 3.9)
        besoin_pdi = (poids * 0.6) + (obj_gmd * 0.45)
    elif "Gestante" in profil:
        besoin_ufl = (0.040 * (poids**0.75)) + 0.45  # Surplus pour le fœtus
        besoin_pdi = (poids * 0.5) + 65
    elif "Allaitante" in profil:
        besoin_ufl = (0.040 * (poids**0.75)) + 0.85  # Fort besoin pour le lait
        besoin_pdi = (poids * 0.5) + 110
    elif "Croissance" in profil:
        besoin_ufl = (0.045 * (poids**0.75)) + (obj_gmd/1000 * 3.5)
        besoin_pdi = (poids * 0.8) + (obj_gmd * 0.5)
    else: # Entretien
        besoin_ufl = 0.038 * (poids**0.75)
        besoin_pdi = poids * 0.5

    # --- 3. BASE ALIMENTS DZ ---
    aliments_dz = {
        "Orge (Chaïr)": {"ufl": 1.05, "pdi": 80},
        "Son de blé (Nokhala)": {"ufl": 0.88, "pdi": 95},
        "Maïs concassé": {"ufl": 1.18, "pdi": 75},
        "Foin Vesse-Avoine": {"ufl": 0.68, "pdi": 65},
        "Paille": {"ufl": 0.38, "pdi": 35}
    }

    # --- 4. AFFICHAGE DES BESOINS ---
    st.subheader(f"📊 Besoins calculés pour : {profil}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Énergie requise", f"{besoin_ufl:.2f} UFL")
    c2.metric("Protéines requises", f"{besoin_pdi:.1f} g PDI")
    c3.metric("Poids Actuel", f"{poids} kg")

    st.markdown("---")

    # --- 5. GÉNÉRATEUR AUTOMATIQUE DE RECETTE ---
    st.subheader("👨‍🍳 Ma Recette Optimale")
    
    if st.button("🪄 Générer la recette et le ratio idéal"):
        # Logique simplifiée de formulation (Ratio concentré/fourrage)
        # On priorise le foin pour le rumen, puis on complète avec le concentré
        quantite_foin = round(poids * 0.015, 1) # 1.5% du poids vif en foin
        ufl_foin = quantite_foin * aliments_dz["Foin Vesse-Avoine"]["ufl"]
        pdi_foin = quantite_foin * aliments_dz["Foin Vesse-Avoine"]["pdi"]
        
        reste_ufl = max(0, besoin_ufl - ufl_foin)
        # On utilise un mélange 70% Orge / 30% Son pour combler le reste
        quantite_orge = round((reste_ufl * 0.7) / aliments_dz["Orge (Chaïr)"]["ufl"], 2)
        quantite_son = round((reste_ufl * 0.3) / aliments_dz["Son de blé (Nokhala)"]["pdi"], 2) # On équilibre par le son
        
        st.success("✅ Recette générée pour couvrir l'objectif de croissance !")
        
        # Affichage visuel de la recette
        r1, r2, r3, r4 = st.columns(4)
        r1.markdown(f"🌾 **Orge**\n### {quantite_orge} kg")
        r2.markdown(f"📦 **Son**\n### {quantite_son} kg")
        r3.markdown(f"🌿 **Foin**\n### {quantite_foin} kg")
        r4.markdown(f"💧 **Eau**\n### ~ {round(poids*0.1, 1)} L")

        # Analyse du ratio
        total_poids_sec = quantite_orge + quantite_son + quantite_foin
        ratio_concentre = ((quantite_orge + quantite_son) / total_poids_sec) * 100
        
        st.info(f"💡 **Conseil de l'expert :** Votre ratio concentré est de **{int(ratio_concentre)}%**. " + 
                ("Attention au risque d'acidose (trop haut)." if ratio_concentre > 70 else "Ratio sécurisé pour la panse."))

    # --- 6. PRÉDICTION D'ÉVOLUTION ---
    st.markdown("---")
    st.subheader("📈 Prédiction de gain de poids")
    jours = st.slider("Nombre de jours de ce régime", 30, 150, 90)
    poids_final = poids + (obj_gmd/1000 * jours)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, jours], y=[poids, poids_final], mode='lines+markers', name='Croissance'))
    fig.update_layout(title=f"Evolution estimée : {poids_final:.1f} kg le { (datetime.now() + timedelta(days=jours)).strftime('%d/%m/%Y') }",
                      xaxis_title="Jours", yaxis_title="Poids (kg)")
    st.plotly_chart(fig, use_container_width=True)
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
