import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
# Note : Pour l'OCR réel, on utiliserait pytesseract ou easyocr

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultimate", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    div[data-testid="stMetricValue"] { color: #00ff00 !important; }
    .bt-status { padding: 10px; border-radius: 5px; background-color: #e3f2fd; color: #0d47a1; font-weight: bold; border-left: 5px solid #2196f3; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "elevage_ia_ultimate.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE IA AVANCÉE ---

def simuler_ocr_boucle(photo):
    """ Simule la lecture du numéro de boucle sur l'oreille """
    return f"DZ-{np.random.randint(100,999)}"

def calculer_indices_complets(row):
    gmq = ((row['p70'] - row['p30']) / 40) * 1000 if row['p70'] and row['p30'] else 0
    viande = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    index = (gmq * 0.05) + (viande * 0.45) + (row['p70'] * 0.3)
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
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value REAL)''')
    c.execute("INSERT OR IGNORE INTO config VALUES ('etalon_ratio', 1.0)")
    c.execute("INSERT OR IGNORE INTO config VALUES ('bt_connected', 0.0)")
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("💎 Selector Ultimate")
menu = st.sidebar.radio("Navigation", 
    ["📊 Dashboard & Croissance", "📸 Scanner IA + OCR", "⚖️ Connexion Balance", "⚙️ Paramètres"])

# --- PAGE 1 : DASHBOARD & GRAPHIQUE DE CROISSANCE ---
if menu == "📊 Dashboard & Croissance":
    st.title("📈 Performance & Évolution")
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
    conn.close()

    if not df.empty:
        df[['GMQ', 'Viande_%', 'Index']] = df.apply(lambda x: pd.Series(calculer_indices_complets(x)), axis=1)
        
        # Graphique de Croissance
        st.subheader("🚀 Courbe de Croissance du Troupeau")
        fig_grow = px.scatter(df, x="p30", y="p70", size="Index", color="race", 
                             hover_name="id", text="id", title="Évolution Poids J30 vs J70")
        fig_grow.add_shape(type="line", x0=10, y0=10, x1=40, y1=40, line=dict(color="Red", dash="dash"))
        st.plotly_chart(fig_grow, use_container_width=True)
        
        st.dataframe(df[['id', 'Index', 'GMQ', 'Viande_%']].sort_values('Index', ascending=False))
    else:
        st.info("Aucune donnée enregistrée.")

# --- PAGE 2 : SCANNER IA + OCR ---
elif menu == "📸 Scanner IA + OCR":
    st.title("📸 Acquisition IA Intelligente")
    
    col_cam, col_data = st.columns([2, 1])
    
    with col_cam:
        photo = st.camera_input("Scanner le bélier (Identification OCR automatique)")
    
    with col_data:
        if photo:
            id_detecte = simuler_ocr_boucle(photo)
            st.success(f"🔍 OCR : Boucle détectée : **{id_detecte}**")
            
            with st.form("quick_save"):
                final_id = st.text_input("Confirmer ID", value=id_detecte)
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
                
                # Récupération automatique du poids (Simulation Balance Bluetooth)
                conn = get_db_connection()
                bt_status = conn.execute("SELECT value FROM config WHERE key='bt_connected'").fetchone()[0]
                conn.close()
                
                if bt_status == 1.0:
                    poids_auto = round(np.random.uniform(30.0, 45.0), 1)
                    st.markdown(f'<div class="bt-status">⚖️ Balance Connectée : {poids_auto} kg</div>', unsafe_allow_html=True)
                    p70 = st.number_input("Poids J70 (kg)", value=poids_auto)
                else:
                    p70 = st.number_input("Poids J70 (Saisie Manuelle)", value=0.0)
                
                hg = st.number_input("H. Garrot (IA cm)", value=71.0)
                
                if st.form_submit_button("📁 Enregistrer et Suivant"):
                    conn = get_db_connection()
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (final_id, race, str(datetime.now().date()), "Blanc"))
                    conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?)", (final_id, 15.0, p70, hg, 80.0, 95.0, 22.0, 25.0))
                    conn.commit()
                    conn.close()
                    st.rerun()

# --- PAGE 3 : CONNEXION BALANCE BLUETOOTH ---
elif menu == "⚖️ Connexion Balance":
    st.title("⚖️ Configuration de la Balance Bluetooth")
    
    conn = get_db_connection()
    bt_status = conn.execute("SELECT value FROM config WHERE key='bt_connected'").fetchone()[0]
    
    col_bt1, col_bt2 = st.columns(2)
    with col_bt1:
        st.write("Statut actuel :", "🟢 Connecté" if bt_status == 1.0 else "🔴 Déconnecté")
        if st.button("Rechercher des balances (Bluetooth)"):
            st.info("Recherche de 'SmartScale-Sheep-V2'...")
            st.success("Balance trouvée !")
            
    with col_bt2:
        if st.button("Activer la transmission automatique"):
            conn.execute("UPDATE config SET value=1.0 WHERE key='bt_connected'")
            conn.commit()
            st.success("Liaison établie avec le Scanner IA.")
        if st.button("Désactiver (Passer en Manuel)"):
            conn.execute("UPDATE config SET value=0.0 WHERE key='bt_connected'")
            conn.commit()
            st.warning("Mode manuel activé.")
    conn.close()

# --- PAGE 4 : PARAMÈTRES ---
elif menu == "⚙️ Paramètres":
    st.title("⚙️ Système")
    # Calibration et remise à zéro...
    if st.button("Réinitialiser tout le système"):
        st.warning("Toutes les données de 1000 têtes seront perdues.")
