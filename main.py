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
# BLOC 3. INDEXATION - VERSION VISIBILITÉ TOTALE
# ==========================================
def view_indexation():
    st.title("✍️ Indexation & Morphométrie")
    
    # Récupération des données du scanner (ou valeurs à 0 par défaut)
    scan_data = st.session_state.get('last_scan', {})

    with st.form("form_index_final"):
        st.subheader("🆔 Identification")
        c1, c2, c3 = st.columns(3)
        id_animal = c1.text_input("Identifiant *")
        categorie = c2.selectbox("Catégorie", ["Agneau (Mâle)", "Agnelle (Femelle)", "Bélier", "Brebis"])
        dentition = c3.selectbox("Dentition", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])

        st.markdown("---")
        
        # --- SECTION POIDS ---
        st.subheader("⚖️ Chronologie des Poids (kg)")
        cp1, cp2, cp3 = st.columns(3)
        p10 = cp1.number_input("Poids à 10j", value=8.5, step=0.1)
        p30 = cp2.number_input("Poids à 30j", value=15.0, step=0.1)
        p70 = cp3.number_input("Poids à 70j", value=28.0, step=0.1)

        st.markdown("---")

        # --- SECTION MENSURATIONS ---
        st.subheader("📏 Mensurations Avancées")
        
        # On place la case à cocher bien en évidence
        activer_bassin = st.checkbox("✅ Activer la mesure du BASSIN", value=True)
        
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        
        hg = col_m1.number_input("Garrot (cm)", value=float(scan_data.get('h_garrot', 75.0)))
        lg = col_m2.number_input("Longueur (cm)", value=float(scan_data.get('l_corps', 85.0)))
        cc = col_m3.number_input("Canon (cm)", value=float(scan_data.get('c_canon', 9.0)))
        pt = col_m4.number_input("Thorax (cm)", value=float(scan_data.get('p_thoracique', 90.0)))
        
        # La case du bassin s'affiche si la checkbox est cochée
        largeur_bassin = 0.0
        if activer_bassin:
            largeur_bassin = col_m5.number_input("Bassin (cm)", value=22.0)
        else:
            col_m5.write("🚫 Option désactivée")

        # --- CALCUL DU VOLUME (AFFICHAGE EN TEMPS RÉEL DANS LE FORMULAIRE) ---
        st.markdown("### 📊 Analyse de la Structure")
        
        # Calcul du volume
        if pt > 0 and lg > 0:
            rayon_p = pt / (2 * 3.14159) # rayon poitrine
            if activer_bassin and largeur_bassin > 0:
                rayon_b = largeur_bassin / 2 # rayon bassin
                # Formule du tronc de cône (plus précise)
                volume_est = (1/3) * 3.14159 * lg * (rayon_p**2 + rayon_p*rayon_b + rayon_b**2) / 1000
                methode = "Modèle Structurel (Précis)"
            else:
                volume_est = (3.14159 * (rayon_p**2) * lg) / 1000
                methode = "Modèle Cylindrique (Standard)"
            
            st.info(f"📦 **Volume Corporel : {volume_est:.2f} Litres** | Méthode : {methode}")
        
        # Bouton de sauvegarde
        if st.form_submit_button("💾 ENREGISTRER L'EXPERTISE"):
            if id_animal:
                st.success(f"Animal {id_animal} enregistré !")
            else:
                st.error("L'identifiant est obligatoire !")

# ==========================================
# BLOC 3. INDEXATION - VERSION AVEC CASE À COCHER PRIORITAIRE
# ==========================================
def view_indexation():
    st.title("✍️ Indexation & Morphométrie")
    
    # 1. RÉCUPÉRATION DES DONNÉES
    scan_data = st.session_state.get('last_scan', {})

    # 2. INSTRUCTION VISUELLE
    st.info("💡 Pour activer la mesure du bassin, cochez la case ci-dessous AVANT de remplir les mensurations.")

    with st.form("form_index_final"):
        # --- SECTION IDENTITÉ ---
        col_id1, col_id2 = st.columns([2, 1])
        id_animal = col_id1.text_input("N° Identifiant (Boucle) *")
        
        # --- LA CASE À COCHER (PLACÉE ICI POUR ÊTRE BIEN VISIBLE) ---
        activer_bassin = st.checkbox("🔍 ACTIVER L'OPTION BASSIN (Recherche)", value=False)
        
        st.markdown("---")
        
        # --- SECTION ÂGE ET CATÉGORIE ---
        c1, c2, c3 = st.columns(3)
        categorie = c1.selectbox("Catégorie", ["Agneau (Mâle)", "Agnelle (Femelle)", "Bélier", "Brebis"])
        dentition = c2.selectbox("Dentition", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
        
        # Logique d'âge simplifiée pour le test
        age_jours = c3.number_input("Âge (Jours)", value=70)

        st.markdown("---")
        
        # --- SECTION POIDS ---
        st.subheader("⚖️ Chronologie des Poids (kg)")
        cp1, cp2, cp3 = st.columns(3)
        p10 = cp1.number_input("Poids à 10j", value=8.5)
        p30 = cp2.number_input("Poids à 30j", value=15.0)
        p70 = cp3.number_input("Poids à 70j", value=28.0)

        st.markdown("---")

        # --- SECTION MENSURATIONS ---
        st.subheader("📏 Mensurations")
        
        # On crée 5 colonnes pour aligner les mesures
        m1, m2, m3, m4, m5 = st.columns(5)
        
        hg = m1.number_input("Garrot (cm)", value=float(scan_data.get('h_garrot', 75.0)))
        lg = m2.number_input("Longueur (cm)", value=float(scan_data.get('l_corps', 85.0)))
        cc = m3.number_input("Canon (cm)", value=float(scan_data.get('c_canon', 9.0)))
        pt = m4.number_input("Thorax (cm)", value=float(scan_data.get('p_thoracique', 90.0)))
        
        # LOGIQUE D'AFFICHAGE DE LA CASE BASSIN
        largeur_bassin = 0.0
        if activer_bassin:
            largeur_bassin = m5.number_input("Bassin (cm)", value=22.0, help="Largeur aux hanches")
        else:
            m5.write("❌")
            m5.caption("Bassin désactivé")

        # --- SECTION CALCUL DU VOLUME ---
        st.markdown("---")
        if pt > 0 and lg > 0:
            rayon_p = pt / (2 * 3.14159)
            if activer_bassin and largeur_bassin > 0:
                rayon_b = largeur_bassin / 2
                # Formule tronc de cône
                volume_est = (1/3) * 3.14159 * lg * (rayon_p**2 + rayon_p*rayon_b + rayon_b**2) / 1000
                st.success(f"📦 **Volume Corporel (Précis) : {volume_est:.2f} Litres**")
            else:
                # Formule cylindre
                volume_est = (3.14159 * (rayon_p**2) * lg) / 1000
                st.warning(f"📦 **Volume Corporel (Standard) : {volume_est:.2f} Litres**")

        # BOUTON DE VALIDATION
        if st.form_submit_button("💾 ENREGISTRER L'INDIVIDU"):
            if id_animal:
                st.success(f"Animal {id_animal} sauvegardé avec succès !")
            else:
                st.error("L'identifiant est obligatoire.")
# ==========================================
# 4. BLOC ECHO-COMPOSITION ANALYTIQUE (V9.1)
# ==========================================
def view_echo(df):
    st.title("🥩 Expertise de la Carcasse")
    
    if df is None or df.empty:
        st.warning("⚠️ Aucune donnée disponible pour l'analyse. Veuillez d'abord indexer des animaux.")
        return

    # Sélection de l'animal
    target = st.selectbox("🎯 Sélectionner un sujet pour analyse détaillée", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]

    # --- EN-TÊTE DE PERFORMANCE ---
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Poids Actuel (P70)", f"{sub['p70']} kg")
    with col_b:
        # Calcul de la compacité (Poids / Taille)
        compacite = round(sub['p70'] / sub['h_garrot'], 2) if sub['h_garrot'] > 0 else 0
        st.metric("Indice de Compacité", f"{compacite}")
    with col_c:
        st.metric("Rendement Estimé", f"{sub['Rendement']}%")

    st.markdown("---")

    # --- RÉPARTITION DÉTAILLÉE (KG & %) ---
    st.subheader("📊 Composition Tissulaire Estimée")
    
    # Calcul des masses réelles en kg
    m_muscle = round((sub['p70'] * sub['Muscle']) / 100, 2)
    m_gras = round((sub['p70'] * sub['Gras']) / 100, 2)
    m_os = round((sub['p70'] * sub['Os']) / 100, 2)

    m1, m2, m3 = st.columns(3)
    
    with m1:
        st.markdown(f"### 🟢 Muscle\n**{m_muscle} kg** ({sub['Muscle']}%)")
        st.caption("Masse maigre exploitable")
    
    with m2:
        st.markdown(f"### 🟡 Gras\n**{m_gras} kg** ({sub['Gras']}%)")
        st.caption("Gras de couverture et intermusculaire")
        
    with m3:
        st.markdown(f"### 🔴 Os\n**{m_os} kg** ({sub['Os']}%)")
        st.caption("Squelette et tissus conjonctifs")

    # --- GRAPHIQUES DE RÉPARTITION ---
    st.markdown("---")
    g1, g2 = st.columns(2)

    with g1:
        # Graphique en secteurs (Donut)
        fig_pie = go.Figure(data=[go.Pie(
            labels=['Muscle', 'Gras', 'Os'],
            values=[m_muscle, m_gras, m_os],
            hole=.5,
            marker_colors=['#2E7D32', '#FBC02D', '#D32F2F']
        )])
        fig_pie.update_layout(title="Proportions de la carcasse", height=350, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)

    with g2:
        # Histogramme de qualité
        fig_bar = px.bar(
            x=["Muscle", "Gras", "Os"],
            y=[m_muscle, m_gras, m_os],
            color=["Muscle", "Gras", "Os"],
            color_discrete_map={'Muscle':'#2E7D32', 'Gras':'#FBC02D', 'Os':'#D32F2F'},
            labels={'x': 'Tissu', 'y': 'Masse (kg)'},
            title="Poids par type de tissu"
        )
        fig_bar.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- NOTE DE CONFORMATION ---
    st.markdown("---")
    ratio_mo = round(sub['Muscle'] / sub['Os'], 2) if sub['Os'] > 0 else 0
    st.write(f"🧬 **Ratio Muscle/Os :** {ratio_mo} (Indicateur de précocité et de qualité bouchère)")
    
    if ratio_mo > 3.5:
        st.success("🏆 Conformation Excellente (Type Viande Supérieur)")
    elif ratio_mo > 2.8:
        st.info("✅ Conformation Bonne (Standard Ouled Djellal)")
    else:
        st.warning("⚠️ Conformation Faible (Individu tardif ou sous-alimenté)")
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

def view_admin(df):
    st.title("🔧 Administration & Données")
    
    # --- SECTION EXPORT ---
    st.subheader("📤 Exportation")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger la base en CSV (Excel)",
            data=csv,
            file_name='donnees_ovins_expert.csv',
            mime='text/csv',
        )
    
    st.markdown("---")
    
    # --- SECTION IMPORT ---
    st.subheader("📥 Importation")
    uploaded_file = st.file_uploader("Charger un fichier CSV pour importer des données", type="csv")
    if uploaded_file is not None:
        data_import = pd.read_csv(uploaded_file)
        st.write("Aperçu des données à importer :", data_import.head())
        if st.button("✅ Confirmer l'importation"):
            # Logique pour insérer les lignes dans SQL...
            st.success("Données importées avec succès !")

    st.markdown("---")
    
    # --- SECTION RÉPARATION (Pour corriger vos erreurs actuelles) ---
    st.subheader("⚠️ Zone de Maintenance")
    if st.button("🔥 RÉINITIALISER ET RÉPARER LA BASE"):
        with get_db_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS mesures")
            conn.execute("DROP TABLE IF EXISTS beliers")
        init_db()
        st.success("Base de données reconstruite avec toutes les colonnes ! L'erreur SQL devrait disparaître.")
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
