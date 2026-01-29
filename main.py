import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="Expert Selector IA Pro v5", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { color: #00ff00 !important; }
    .certificat-card { padding: 25px; border: 3px double #d4af37; background-color: #fffdf5; border-radius: 10px; text-align: center; color: black; }
    .calibration-box { padding: 15px; border: 2px dashed #007bff; border-radius: 10px; background-color: #f0f8ff; color: black; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_ia_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE SCIENTIFIQUE & CALIBRATION ---

def calculer_indices_complets(row):
    """ Calculs zootechniques INRA adaptés """
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if row['p70'] and row['p30'] else 0
    viande = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    gras = (row['p_thoracique'] * 0.18) + (row['p70'] * 0.15) - 14.5
    index = (gmq * 0.05) + (viande * 0.45) + (row['p70'] * 0.3) + (row['p_thoracique'] * 0.2)
    return round(gmq, 1), round(viande, 1), round(gras, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, robe TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
                  p_thoracique REAL, l_poitrine REAL, l_bassin REAL)''')
    # Table de configuration pour la calibration
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value REAL)''')
    c.execute("INSERT OR IGNORE INTO config VALUES ('etalon_ratio', 1.0)")
    conn.commit()
    conn.close()

init_db()

# --- 4. RÉCUPÉRATION PARAMÈTRES ---
conn = get_db_connection()
etalon_ratio = conn.execute("SELECT value FROM config WHERE key='etalon_ratio'").fetchone()[0]
conn.close()

# --- 5. NAVIGATION ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/1998/1998762.png", width=80)
st.sidebar.title("Expert Selector Pro")
menu = st.sidebar.radio("Navigation", 
    ["🏠 Tableau de Bord", "📸 Saisie IA (Masse)", "✍️ Saisie Manuelle", "🏆 Duel & Certificats", "⚙️ Maintenance"])

# Chargement global des données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    df[['GMQ', 'Viande_%', 'Gras_%', 'Index']] = df.apply(lambda x: pd.Series(calculer_indices_complets(x)), axis=1)

# --- PAGE : SAISIE IA (AVEC CALIBRATION) ---
if menu == "📸 Saisie IA (Masse)":
    st.title("📸 Scanner Morphométrique IA")
    st.info(f"Calibration actuelle : 1 pixel = {etalon_ratio} cm")
    
    photo = st.camera_input("Scanner le bélier")
    
    if photo:
        # L'IA simule l'extraction de pixels multipliée par l'étalon
        res_brut_px = {"hg": 70, "lc": 80, "pt": 95} # Pixels détectés
        
        with st.form("ia_val"):
            col1, col2, col3 = st.columns(3)
            id_a = col1.text_input("ID Boucle")
            race = col1.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            
            # Application du coefficient d'étalonnage
            hg = col2.number_input("H. Garrot (cm)", value=round(res_brut_px['hg'] * etalon_ratio, 1))
            lc = col2.number_input("L. Corps (cm)", value=round(res_brut_px['lc'] * etalon_ratio, 1))
            
            pt = col3.number_input("Périmètre (cm)", value=round(res_brut_px['pt'] * etalon_ratio, 1))
            p70 = col3.number_input("Poids J70 (kg)", value=35.0)
            
            if st.form_submit_button("✅ Enregistrer & Suivant"):
                if id_a:
                    conn = get_db_connection()
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, race, str(datetime.now().date()), "Blanche"))
                    conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?)", (id_a, 15.0, p70, hg, lc, pt, 22.0, 25.0))
                    conn.commit()
                    conn.close()
                    st.rerun()

# --- PAGE : MAINTENANCE & CALIBRATION ---
elif menu == "⚙️ Maintenance":
    st.title("⚙️ Paramètres Avancés")
    
    st.subheader("📏 Étalonnage de la Caméra")
    st.markdown("""
    <div class="calibration-box">
    <b>Comment calibrer ?</b><br>
    1. Placez une règle de 1 mètre derrière l'animal.<br>
    2. Prenez une photo.<br>
    3. Ajustez le curseur jusqu'à ce que la mesure affichée par l'IA corresponde à la règle.
    </div>
    """, unsafe_allow_html=True)
    
    new_ratio = st.slider("Coefficient d'étalonnage (Pixels vers CM)", 0.5, 2.0, etalon_ratio, 0.01)
    
    if st.button("💾 Sauvegarder la Calibration"):
        conn = get_db_connection()
        conn.execute("UPDATE config SET value=? WHERE key='etalon_ratio'", (new_ratio,))
        conn.commit()
        conn.close()
        st.success(f"Calibration mise à jour : {new_ratio}")

    st.divider()
    if st.button("🗑️ Vider toute la base de données"):
        conn = get_db_connection()
        conn.execute("DROP TABLE IF EXISTS beliers")
        conn.execute("DROP TABLE IF EXISTS mesures")
        conn.commit()
        st.rerun()

# --- (Les autres pages : Tableau de Bord, Manuel, Duel restent identiques au code complet précédent) ---
elif menu == "🏠 Tableau de Bord":
    st.title("📊 État de la Reproductrice")
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Individus", len(df))
        c2.metric("Meilleur GMQ", f"{df['GMQ'].max()} g/j")
        c3.metric("Rendement Max", f"{df['Viande_%'].max()}%")
        c4.metric("Score Moyen", f"{df['Index'].mean().round(1)}")
        st.dataframe(df[['id', 'race', 'Index', 'GMQ', 'Viande_%']].sort_values(by="Index", ascending=False), use_container_width=True)

elif menu == "🏆 Duel & Certificats":
    st.title("📜 Expertise & Sélection")
    if not df.empty:
        id1 = st.selectbox("Bélier A", df['id'].unique(), index=0)
        id2 = st.selectbox("Bélier B", df['id'].unique(), index=min(1, len(df)-1))
        b1, b2 = df[df['id']==id1].iloc[0], df[df['id']==id2].iloc[0]
        fig = go.Figure()
        m = ['h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'l_bassin']
        fig.add_trace(go.Scatterpolar(r=[b1[x] for x in m], theta=m, fill='toself', name=id1))
        fig.add_trace(go.Scatterpolar(r=[b2[x] for x in m], theta=m, fill='toself', name=id2))
        st.plotly_chart(fig)
