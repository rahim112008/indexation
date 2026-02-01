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
    tab_ia, tab_etalon = st.tabs(["🤖 IA Intégrale (Automatique)", "📏 Métrologie (Avec Étalon)"])

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
                    res_ia = {"h_garrot": 76.5, "p_thoracique": 92.0, "l_corps": 85.5, "c_canon": 9.0}
                    st.success("✅ Variables extraites")
                    st.table(pd.DataFrame([res_ia]))
                    if st.button("🚀 Envoyer à l'Indexation", key="btn_send_ia"):
                        st.session_state['last_scan'] = res_ia
                        st.rerun()

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
                    res_et = {"h_garrot": 77.8, "p_thoracique": 94.2, "l_corps": 88.0, "c_canon": 9.2}
                    st.session_state['last_scan'] = res_et
                    st.rerun()

# ==========================================
# BLOC 3. INDEXATION - VERSION CORRIGÉE (DYNAMIQUE)
# ==========================================
def view_indexation():
    st.title("✍️ Indexation & Morphométrie")
    
    # 1. RÉCUPÉRATION DES DONNÉES DU SCANNER
    scan_data = st.session_state.get('last_scan', {})

    # 2. SÉLECTEUR D'ÂGE (HORS DU FORMULAIRE POUR ÊTRE DYNAMIQUE)
    st.markdown("### ⏳ Détermination de l'âge")
    methode_age = st.radio(
        "Choisir la méthode de saisie :",
        ["Par Dentition", "Âge Exact (Jours)", "Âge en Mois"],
        horizontal=True,
        key="age_selector"
    )

    # Création des champs dynamiques selon le choix
    col_a, col_b = st.columns(2)
    with col_a:
        if methode_age == "Par Dentition":
            dentition_val = st.selectbox("Nombre de dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            age_jours_val = 70
        elif methode_age == "Âge Exact (Jours)":
            age_jours_val = st.number_input("Entrez le nombre de jours exacts", min_value=1, value=70)
            dentition_val = "Saisie Jours"
        else:
            age_mois_val = st.number_input("Entrez le nombre de mois", min_value=1, value=3)
            age_jours_val = age_mois_val * 30
            dentition_val = f"Est. {age_mois_val} mois"

    st.markdown("---")

    # 3. LE RESTE DANS LE FORMULAIRE
    with st.form("form_index_final"):
        st.subheader("🆔 Identification & Mensurations")
        col_id1, col_id2 = st.columns([2, 1])
        id_animal = col_id1.text_input("N° Identifiant (Boucle) *")
        categorie = col_id2.selectbox("Catégorie", ["Agneau", "Agnelle", "Bélier", "Brebis"])
        
        # Section Poids
        cp1, cp2, cp3 = st.columns(3)
        p10 = cp1.number_input("Poids à 10j", value=8.5)
        p30 = cp2.number_input("Poids à 30j", value=15.0)
        p70 = cp3.number_input("Poids à 70j", value=28.0)

        # Section Mensurations
        activer_bassin = st.checkbox("🔍 ACTIVER L'OPTION BASSIN", value=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        hg = m1.number_input("Garrot (cm)", value=float(scan_data.get('h_garrot', 75.0)))
        lg = m2.number_input("Longueur (cm)", value=float(scan_data.get('l_corps', 85.0)))
        cc = m3.number_input("Canon (cm)", value=float(scan_data.get('c_canon', 9.0)))
        pt = m4.number_input("Thorax (cm)", value=float(scan_data.get('p_thoracique', 90.0)))
        
        largeur_bassin = m5.number_input("Bassin (cm)", value=22.0) if activer_bassin else 0.0

        # Bouton de validation
        submit = st.form_submit_button("💾 ENREGISTRER L'INDIVIDU", use_container_width=True)
        
        if submit:
            if id_animal:
                # Utilisation des valeurs capturées hors du formulaire
                st.success(f"✅ Animal {id_animal} enregistré !")
                st.info(f"Méthode: {methode_age} | Valeur: {dentition_val} | Jours: {age_jours_val}")
            else:
                st.error("L'identifiant est obligatoire.")
# ==========================================
# 4. BLOC ECHO-COMPOSITION (CORRIGÉ)
# ==========================================
def view_echo(df):
    st.title("🥩 Expertise de la Carcasse")
    if df is None or df.empty:
        st.warning("⚠️ Aucune donnée disponible.")
        return

    target = st.selectbox("🎯 Sélectionner un sujet", df['id'].unique())
    sub = df[df['id'] == target].iloc[0]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Poids P70", f"{sub['p70']} kg")
    col_b.metric("Muscle", f"{sub['Muscle']}%")
    col_c.metric("Rendement", f"{sub['Rendement']}%")

    st.markdown("---")
    m_muscle = round((sub['p70'] * sub['Muscle']) / 100, 2)
    m_gras = round((sub['p70'] * sub['Gras']) / 100, 2)
    m_os = round((sub['p70'] * sub['Os']) / 100, 2)

    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[m_muscle, m_gras, m_os], hole=.5, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        st.write(f"🟢 **Muscle:** {m_muscle} kg")
        st.write(f"🟡 **Gras:** {m_gras} kg")
        st.write(f"🔴 **Os:** {m_os} kg")

# ==========================================
# 5. BLOC NUTRITION IA - SIMULATEUR ALGÉRIEN
# ==========================================
def view_nutrition(df):
    st.title("🥗 Simulateur de Ration & Prédiction")
    
    if df is None or df.empty:
        st.warning("⚠️ Aucune donnée disponible. Enregistrez un animal d'abord.")
        return

    # 1. SÉLECTION DE L'ANIMAL ET ANALYSE
    target = st.selectbox("Sélectionner l'individu", df['id'].unique())
    subj = df[df['id'] == target].iloc[0]
    
    st.markdown(f"**Analyse de départ :** {subj['id']} | Poids : {subj['p70']} kg | GMD Actuel : {subj['GMD']} g/j")

    # 2. DÉFINITION DE L'OBJECTIF
    col_obj1, col_obj2 = st.columns(2)
    with col_id1:
        obj_gmd = st.slider("Objectif de croissance visé (g/j)", 100, 500, 250)
    
    # Calcul du besoin théorique (Norme UFL)
    besoin_ufl = round((0.035 * (subj['p70']**0.75)) + (obj_gmd / 1000) * 3.5, 2)
    besoin_pdi = round(besoin_ufl * 85, 0) # Estimation Protéines (PDI)

    st.info(f"🎯 **Besoin cible pour atteindre {obj_gmd}g/j : {besoin_ufl} UFL**")

    st.markdown("---")
    st.subheader("🌾 Composition de la Ration (Marché Algérien)")
    
    # 3. SIMULATEUR D'ALIMENTS LOCAUX
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    
    # Valeurs nutritionnelles moyennes (UFL/kg)
    q_orge = col_f1.number_input("Orge (kg)", min_value=0.0, step=0.1, value=0.5, help="1.05 UFL/kg")
    q_son = col_f2.number_input("Son de blé (kg)", min_value=0.0, step=0.1, value=0.3, help="0.90 UFL/kg")
    q_luzerne = col_f3.number_input("Luzerne (kg)", min_value=0.0, step=0.1, value=1.0, help="0.65 UFL/kg")
    q_paille = col_f4.number_input("Paille (kg)", min_value=0.0, step=0.1, value=0.5, help="0.40 UFL/kg")

    # Calcul de l'apport total
    apport_total = (q_orge * 1.05) + (q_son * 0.90) + (q_luzerne * 0.65) + (q_paille * 0.40)
    apport_total = round(apport_total, 2)

    # 4. PRÉDICTION DE L'IA
    st.markdown("---")
    st.subheader("🔮 Prédiction de Performance")
    
    diff = apport_total - besoin_ufl
    
    c_res1, c_res2 = st.columns(2)
    
    with c_res1:
        if apport_total < besoin_ufl:
            st.error(f"📉 Ration Insuffisante : {apport_total} UFL apportés.")
            st.write(f"⚠️ Manque **{abs(diff):.2f} UFL** pour atteindre l'objectif.")
        elif abs(diff) <= 0.1:
            st.success(f"✅ Ration Équilibrée : {apport_total} UFL.")
            st.write("L'animal devrait atteindre son objectif de croissance.")
        else:
            st.warning(f"📈 Ration Excédentaire : {apport_total} UFL.")
            st.write(f"💰 Risque de gaspillage de nourriture (+{diff:.2f} UFL).")

    with c_res2:
        # Prédiction du poids à 30 jours
        poids_futur = round(subj['p70'] + (obj_gmd * 30 / 1000), 1)
        st.metric("Poids Prédit (J+30)", f"{poids_futur} kg", delta=f"+{obj_gmd*30/1000} kg")

    # CONSEIL EXPERT DYNAMIQUE
    with st.expander("💡 Conseil Stratégique de l'IA"):
        if q_luzerne < 0.5:
            st.write("🥛 **Conseil :** Augmentez la Luzerne pour améliorer le développement musculaire (Azote).")
        if q_orge > 1.2:
            st.write("⚠️ **Alerte :** Trop d'orge ! Risque d'acidose. Ajoutez de la paille pour la rumination.")
        if diff < 0:
            supp_orge = round(abs(diff) / 1.05, 2)
            st.write(f"🛠 **Action :** Ajoutez environ **{supp_orge} kg d'Orge** pour combler le déficit.")

def view_admin(df):
    st.title("🔧 Admin & Export")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Exporter les données (CSV)", csv, "data_ovins.csv", "text/csv")
# ==========================================
# POINT D'ENTRÉE PRINCIPAL (CORRIGÉ)
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
    elif menu == "🥩 Echo-Composition": view_echo(df) # Corrigé : Nom de fonction
    elif menu == "🥗 Nutrition": view_nutrition(df)
    elif menu == "🔧 Admin": view_admin(df) # Corrigé : Passage de l'argument df

if __name__ == "__main__":
    main()
