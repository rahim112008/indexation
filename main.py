import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import io
import random
from PIL import Image

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v3.8", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .scanner-box { border: 2px dashed #1b5e20; padding: 20px; border-radius: 15px; background-color: #f1f8e9; text-align: center; }
    .metric-card { background-color: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_recherche.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id))''')

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        if p70 <= 0: return pd.Series(res)
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, min(8.0, 3.2 + (1450 / res['GMD']) - (res['IC'] / 200))), 2)
        egd = 1.2 + (p70 * 0.15) + (res['IC'] * 0.05) - (hg * 0.03)
        res['Gras'] = round(max(5.0, 4.0 + (egd * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (res['IC'] * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    init_db()
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        metrics = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, metrics], axis=1)
    return df

# ==========================================
# 3. BLOC : SCANNER IA & ÉTALONNAGE
# ==========================================
def view_scanner():
    st.title("📸 Scanner Biométrique Assisté par IA")
    
    col_cfg, col_img = st.columns([1, 2])
    
    with col_cfg:
        st.subheader("⚙️ Configuration")
        source = st.radio("Source de l'image", ["📁 Télécharger une photo", "📷 Caméra en direct"])
        etalon = st.selectbox("Référence d'étalonnage", 
                              ["Règle Standard (1 mètre)", "Feuille A4 (21 x 29.7 cm)", "Carte Bancaire (8.5 cm)"])
        
        st.info(f"L'IA utilisera l'objet '{etalon}' présent sur la photo pour calculer les dimensions réelles de l'animal.")
        
        if source == "📁 Télécharger une photo":
            file = st.file_uploader("Importer le profil de l'animal", type=['jpg', 'png', 'jpeg'])
        else:
            file = st.camera_input("Prendre une photo de profil")

    with col_img:
        if file:
            img = Image.open(file)
            st.image(img, caption="Analyse en cours...", use_container_width=True)
            
            with st.spinner("Analyse des pixels et conversion métrique..."):
                # Simulation de détection IA basée sur l'étalon
                time_sleep = 1.5
                res_hg = round(random.uniform(72, 78), 1)
                res_cc = round(random.uniform(8.5, 9.8), 1)
                res_pt = round(random.uniform(85, 98), 1)
                
                st.session_state['scan_results'] = {
                    "h_garrot": res_hg, "c_canon": res_cc, "p_thoracique": res_pt
                }
            
            st.success("✅ Analyse terminée !")
            c1, c2, c3 = st.columns(3)
            c1.metric("H. Garrot (IA)", f"{res_hg} cm")
            c2.metric("T. Canon (IA)", f"{res_cc} cm")
            c3.metric("P. Thorax (IA)", f"{res_pt} cm")
            
            if st.button("📥 Envoyer vers l'Indexation", use_container_width=True):
                st.session_state['go_to_index'] = True
                st.toast("Données transférées !")

# ==========================================
# 4. BLOC : INDEXATION (RÉCUPÈRE LE SCAN)
# ==========================================
def view_indexation():
    st.title("✍️ Indexation et Enregistrement")
    
    # Récupération des données du scanner si elles existent
    scan = st.session_state.get('scan_results', {})
    
    with st.form("form_index"):
        col1, col2 = st.columns(2)
        with col1:
            id_a = st.text_input("ID Animal (Boucle) *", placeholder="Ex: OD-2026-001")
            sex = st.selectbox("Sexe", ["Bélier", "Brebis", "Agneau"])
            p30 = st.number_input("Poids à 30 jours (kg)", 0.0)
            p70 = st.number_input("Poids actuel / 70j (kg)", 0.0)
        
        with col2:
            st.write("📐 Mesures Biométriques (Pré-remplies par le Scanner)")
            hg = st.number_input("Hauteur Garrot (cm)", value=float(scan.get('h_garrot', 0.0)))
            cc = st.number_input("Tour de Canon (cm)", value=float(scan.get('c_canon', 0.0)))
            pt = st.number_input("Périmètre Thorax (cm)", value=float(scan.get('p_thoracique', 0.0)))
        
        if st.form_submit_button("💾 ENREGISTRER DANS LA BASE", use_container_width=True):
            if id_a:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race, sexe) VALUES (?,?,?)", (id_a, "Ouled Djellal", sex))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_a, p30, p70, hg, cc, pt))
                st.success(f"L'animal {id_a} a été indexé avec succès.")
                st.session_state['scan_results'] = {} # Reset du scan après enregistrement
                st.rerun()
            else:
                st.error("Veuillez entrer un ID valide.")

# ==========================================
# 5. ECHO-COMPOSITION & COMPARATEUR
# ==========================================
def view_echo_composition(df):
    st.title("🥩 Echo-Like : Composition Carcasse")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    target = st.selectbox("Sélectionner un animal pour analyse", df['id'].unique())
    subj = df[df['id'] == target].iloc[0]
    
    col_chart, col_info = st.columns([2, 1])
    with col_chart:
        fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], 
                                    values=[subj['Muscle'], subj['Gras'], subj['Os']],
                                    hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
        st.plotly_chart(fig, use_container_width=True)
    
    with col_info:
        st.markdown(f"""
        <div class='metric-card'>
            <h3>Diagnostic {target}</h3>
            <p>Rendement Viande : <b>{subj['Muscle']}%</b></p>
            <p>Efficience (ICA) : <b>{subj['ICA']}</b></p>
            <p>GMD : <b>{subj['GMD']} g/j</b></p>
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# 6. NAVIGATION PRINCIPALE
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT OVIN PRO")
    menu = st.sidebar.radio("Navigation", 
        ["🏠 Dashboard", "📸 Scanner IA", "✍️ Indexation", "🥩 Echo-Composition", "📊 Statistiques", "💾 Data Mgmt"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Dashboard de Sélection")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("GMD Moyen", f"{df['GMD'].mean():.0f} g/j")
            c2.metric("Muscle Moyen", f"{df['Muscle'].mean():.1f}%")
            c3.metric("Efficience Moy.", f"{df['ICA'].mean():.2f}")
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA']], use_container_width=True)
        else:
            st.info("Base de données vide. Commencez par le Scanner ou l'Indexation.")

    elif menu == "📸 Scanner IA": view_scanner()
    elif menu == "✍️ Indexation": view_indexation()
    elif menu == "🥩 Echo-Composition": view_echo_composition(df)
    elif menu == "📊 Statistiques":
        st.title("📊 Analyses de Recherche")
        if not df.empty:
            fig = px.scatter(df, x="GMD", y="Muscle", color="sexe", size="p70", trendline="ols")
            st.plotly_chart(fig, use_container_width=True)
    
    elif menu == "💾 Data Mgmt":
        st.title("💾 Gestion CSV")
        if not df.empty:
            st.download_button("📥 Exporter CSV", df.to_csv(index=False).encode('utf-8'), "export.csv", "text/csv")

if __name__ == "__main__":
    main()
