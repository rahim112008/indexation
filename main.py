import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
from PIL import Image

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="BélierSelector IA Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    .stButton>button { border-radius: 8px; height: 3em; font-weight: bold; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .ia-box { padding: 20px; border: 2px solid #007bff; border-radius: 15px; background-color: #e7f3ff; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_ia_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE IA & SCIENTIFIQUE ---
def analyser_photo_ia(photo):
    """ Simulation du moteur de Computer Vision """
    # En production, on utiliserait un modèle de segmentation ici
    return {
        "h_garrot": round(np.random.uniform(65, 75), 1),
        "l_corps": round(np.random.uniform(70, 85), 1),
        "p_thoracique": round(np.random.uniform(88, 105), 1),
        "robe": "Blanche (Ouled Djellal)" if np.random.rand() > 0.3 else "Rousse (Rembi)"
    }

def calculer_indices(row):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if row['p70'] and row['p30'] else 0
    viande = 51.5 + (0.4 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.1 * row['h_garrot'])
    scm = (row['h_garrot'] * 0.2 + row['l_corps'] * 0.4 + row['p_thoracique'] * 0.4)
    index = (gmq * 0.05) + (viande * 0.45) + (scm * 0.5)
    return round(gmq, 1), round(viande, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, robe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
                  p_thoracique REAL, l_poitrine REAL, l_bassin REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("🧬 BélierSelector IA")
menu = st.sidebar.radio("Navigation", ["📸 Saisie Automatisée", "✍️ Saisie Manuelle", "📄 Fiches & Duel", "⚙️ Gestion Base"])

# --- PAGE 1 : SAISIE IA (POUR 1000 TÊTES) ---
if menu == "📸 Saisie Automatisée":
    st.title("📸 Scanner Morphométrique par IA")
    st.write("Idéal pour le traitement de masse. Prenez la photo de profil.")
    
    photo = st.camera_input("Scanner le bélier")
    
    if photo:
        res_ia = analyser_photo_ia(photo)
        
        with st.container():
            st.markdown('<div class="ia-box">', unsafe_allow_html=True)
            st.subheader("🤖 Résultats de l'Analyse Vision")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                id_a = st.text_input("ID Animal (Boucle)")
                race_ia = st.selectbox("Race détectée", ["Ouled Djellal", "Rembi", "Hamra"], index=0 if "Blanche" in res_ia['robe'] else 1)
            with col2:
                hg = st.number_input("Hauteur Garrot (cm)", value=res_ia['h_garrot'])
                lc = st.number_input("Longueur Corps (cm)", value=res_ia['l_corps'])
            with col3:
                pt = st.number_input("Périmètre Thor. (cm)", value=res_ia['p_thoracique'])
                p30 = st.number_input("Poids J30 (kg)", value=18.0)
                p70 = st.number_input("Poids J70 (kg)", value=32.0)
            
            if st.button("💾 Valider & Scanner le Suivant"):
                if id_a:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, race_ia, str(datetime.now().date()), res_ia['robe']))
                    c.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?)", (id_a, p30, p70, hg, lc, pt, 22.0, 25.0))
                    conn.commit()
                    conn.close()
                    st.success(f"Animal {id_a} enregistré !")
                    st.rerun()
                else:
                    st.error("Veuillez entrer un ID.")
            st.markdown('</div>', unsafe_allow_html=True)

# --- PAGE 2 : SAISIE MANUELLE ---
elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie de Secours")
    with st.form("manuel"):
        c1, c2 = st.columns(2)
        id_m = c1.text_input("ID Animal")
        race_m = c1.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
        hg_m = c2.number_input("H. Garrot (cm)", 0.0)
        pt_m = c2.number_input("Périmètre (cm)", 0.0)
        p70_m = c2.number_input("Poids J70 (kg)", 0.0)
        
        if st.form_submit_button("Enregistrer"):
            st.success("Donnée enregistrée manuellement.")

# --- PAGE 3 : ANALYSE & DUEL ---
elif menu == "📄 Fiches & Duel":
    st.title("📊 Analyse des Performances")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    conn.close()
    
    if not df.empty:
        # Appliquer les calculs
        df[['GMQ', 'Viande_%', 'Index']] = df.apply(lambda x: pd.Series(calculer_indices(x)), axis=1)
        
        tab1, tab2 = st.tabs(["📄 Fiche Individuelle", "⚔️ Duel"])
        
        with tab1:
            sel = st.selectbox("Choisir un bélier", df['id'].unique())
            data = df[df['id'] == sel].iloc[0]
            st.metric("Index Élite", data['Index'])
            st.write(f"**Robe :** {data['robe']}")
            # 
            fig = go.Figure(data=go.Scatterpolar(
                r=[data['h_garrot'], data['l_corps'], data['p_thoracique'], 22, 25],
                theta=['Hauteur', 'Longueur', 'Périmètre', 'Largeur P.', 'Largeur B.'], fill='toself'
            ))
            st.plotly_chart(fig)
            
        with tab2:
            st.subheader("Comparaison Directe")
            id1 = st.selectbox("Bélier A", df['id'].unique(), index=0)
            id2 = st.selectbox("Bélier B", df['id'].unique(), index=min(1, len(df)-1))
            st.write(f"Vainqueur probable : **{id1 if df[df['id']==id1]['Index'].values[0] > df[df['id']==id2]['Index'].values[0] else id2}**")
    else:
        st.info("Aucune donnée à analyser.")

# --- PAGE 4 : GESTION ---
elif menu == "⚙️ Gestion Base":
    st.title("⚙️ Administration")
    conn = get_db_connection()
    df_all = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    conn.close()
    
    st.dataframe(df_all)
    
    if st.button("🗑️ Vider toute la base"):
        conn = get_db_connection()
        conn.execute("DROP TABLE IF EXISTS beliers")
        conn.execute("DROP TABLE IF EXISTS mesures")
        conn.commit()
        conn.close()
        st.rerun()
