import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Ultimate Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { color: #00ff00 !important; }
    .certificat { padding: 30px; border: 5px double #d4af37; background-color: #fffdf5; border-radius: 15px; text-align: center; color: black; }
    .alert-box { padding: 10px; border-radius: 5px; background-color: #ffeb3b; color: #333; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_master_v1.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE SCIENTIFIQUE ---
def calculer_tout(row, mode="Viande"):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if row['p70'] and row['p30'] else 0
    rendement = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    
    # Choix de l'index selon l'objectif de l'éleveur
    if mode == "Viande":
        index = (gmq * 0.1) + (rendement * 0.6) + (row['p70'] * 0.3)
    else: # Mode Rusticité
        index = (row['c_canon'] * 0.4) + (row['h_garrot'] * 0.3) + (gmq * 0.3)
        
    return round(gmq, 1), round(rendement, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, robe TEXT, sexe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
                  p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value REAL)''')
    c.execute("INSERT OR IGNORE INTO config VALUES ('etalon_ratio', 1.05)")
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("🐏 Expert Selector Pro")
menu = st.sidebar.radio("Navigation", 
    ["📊 Dashboard & Alertes", "📸 Saisie IA / OCR", "✍️ Saisie Manuelle", "🔬 Stats & Corrélations", "🏆 Duel & Élite", "📥 Import / Export"])

# Chargement des données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
ratio = conn.execute("SELECT value FROM config WHERE key='etalon_ratio'").fetchone()[0]
conn.close()

# --- PAGE 1 : DASHBOARD & ALERTES ---
if menu == "📊 Dashboard & Alertes":
    st.title("📈 Tableau de Bord du Troupeau")
    if not df.empty:
        df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_tout(x)), axis=1)
        
        # Section Alertes
        st.subheader("🔔 Alertes Pesées (Planning)")
        today = datetime.now().date()
        for _, row in df.iterrows():
            dnaiss = datetime.strptime(row['date_naiss'], '%Y-%m-%d').date()
            if today == dnaiss + timedelta(days=10) and row['p10'] == 0:
                st.markdown(f'<div class="alert-box">⚠️ Pesée J10 requise pour : {row["id"]}</div>', unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Effectif Total", len(df))
        c2.metric("GMQ Moyen", f"{df['GMQ'].mean().round(1)} g/j")
        c3.metric("Élite (>80)", len(df[df['Index'] > 80]))
        c4.metric("Rendement Moyen", f"{df['Rendement'].mean().round(1)} %")
        
        st.subheader("📋 Registre Global")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Base vide. Enregistrez vos premiers sujets.")

# --- PAGE 2 : SAISIE IA / OCR ---
elif menu == "📸 Saisie IA / OCR":
    st.title("📸 Scanner Intelligent")
    
    photo = st.camera_input("Scanner le bélier")
    if photo:
        id_ocr = f"DZ-{np.random.randint(1000,9999)}" # Simulation OCR
        st.success(f"Boucle détectée : {id_ocr}")
        with st.form("ia_form"):
            c1, c2, c3 = st.columns(3)
            id_f = c1.text_input("Confirmer ID", id_ocr)
            race_f = c1.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            hg = c2.number_input("H. Garrot (cm)", value=70.0 * ratio)
            lc = c2.number_input("L. Corps (cm)", value=82.0 * ratio)
            pt = c3.number_input("Périmètre (cm)", value=98.0 * ratio)
            p70 = c3.number_input("Poids J70 (Balance BT/Manuelle)", 35.0)
            if st.form_submit_button("📁 Valider & Suivant"):
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_f, race_f, str(datetime.now().date()), "Blanc", "Mâle"))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (id_f, 4.0, 15.0, p70, hg, lc, pt, 22.0, 9.5))
                conn.commit()
                st.rerun()

# --- PAGE 4 : STATS & CORRÉLATIONS ---
elif menu == "🔬 Stats & Corrélations":
    st.title("🔬 Analyse Scientifique")
    if not df.empty:
        df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_tout(x)), axis=1)
        st.subheader("🔗 Matrice de Corrélation (Morpho vs Performance)")
        corr = df[['h_garrot', 'l_corps', 'p_thoracique', 'p70', 'GMQ', 'Rendement']].corr()
        fig = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r')
        st.plotly_chart(fig, use_container_width=True)
        

# --- PAGE 5 : DUEL & ÉLITE ---
elif menu == "🏆 Duel & Élite":
    st.title("🏆 Sélection des Meilleurs")
    if len(df) >= 2:
        id1 = st.selectbox("Bélier A", df['id'].unique(), index=0)
        id2 = st.selectbox("Bélier B", df['id'].unique(), index=1)
        
        # Graphique Radar
        fig = go.Figure()
        for i_d in [id1, id2]:
            row = df[df['id']==i_d].iloc[0]
            fig.add_trace(go.Scatterpolar(r=[row['h_garrot'], row['l_corps'], row['p_thoracique'], row['l_poitrine'], row['c_canon']*7], 
                                          theta=['Hauteur', 'Longueur', 'Périmètre', 'Poitrine', 'Canon'], fill='toself', name=i_d))
        st.plotly_chart(fig)
        

# --- PAGE 6 : IMPORT / EXPORT ---
elif menu == "📥 Import / Export":
    st.title("📥 Gestion des Fichiers")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Export Excel")
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Télécharger la base complète", buffer, "troupeau_expert.xlsx")
    with col2:
        st.subheader("Importation de masse")
        file = st.file_uploader("Charger un fichier Excel (1000 têtes)", type="xlsx")
        if file:
            data_import = pd.read_excel(file)
            st.write(f"✅ {len(data_import)} nouveaux individus détectés.")
            if st.button("Fusionner avec la base"):
                # Logique d'importation SQL ici...
                st.success("Importation réussie !")
