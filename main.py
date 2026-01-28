import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import math
import sqlite3
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Pro - SQL Edition", layout="wide", page_icon="🐏")

# ============================================================
# GESTION DE LA BASE DE DONNÉES (SQLITE)
# ============================================================

DB_NAME = "elevage_pro.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db_structure():
    """Initialise les tables si elles n'existent pas"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (ID TEXT PRIMARY KEY, Race TEXT, Age REAL, BCS REAL, PoidsActuel REAL, 
                  GMQ REAL, DateDernierePesee TEXT, Score_Global REAL, ProchainesPesees TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS agneaux 
                 (ID_Agneau TEXT PRIMARY KEY, ID_Mere TEXT, ID_Pere TEXT, 
                  Date_Naissance TEXT, Sexe TEXT, Poids_Naissance REAL, 
                  Poids_J30 REAL, GMQ_J7_J30 REAL, Cotation_J30 REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS consommation 
                 (ID_Lot TEXT PRIMARY KEY, Date_Debut TEXT, Duree_Jours INTEGER, 
                  IC_Lot REAL, Marge_Alimentaire REAL, Efficacite TEXT)''')
    conn.commit()
    conn.close()

def sauvegarder_agneau_sql(data_dict):
    conn = get_db_connection()
    try:
        df = pd.DataFrame([data_dict])
        df.to_sql('agneaux', conn, if_exists='append', index=False)
        conn.commit()
    finally:
        conn.close()

def supprimer_animal_sql(table, column, animal_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(f"DELETE FROM {table} WHERE {column} = ?", (animal_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

# ============================================================
# UTILITAIRES & EXPORT
# ============================================================

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Donnees')
    return output.getvalue()

# ============================================================
# INITIALISATION DES DONNÉES DE DÉMO
# ============================================================

def init_demo_data():
    today = datetime.now().date()
    beliers_data = [{'ID': 'REM-001', 'Race': 'Rembi', 'Age': 24, 'BCS': 3.5, 'PoidsActuel': 68.0, 'GMQ': 245.0, 'Score_Global': 82.4}]
    agneaux_data = [{'ID_Agneau': 'AGN-001', 'ID_Mere': 'M-01', 'ID_Pere': 'REM-001', 'Date_Naissance': str(today), 'Sexe': 'Mâle', 'Poids_Naissance': 4.2, 'Poids_J30': 12.0, 'GMQ_J7_J30': 250.0, 'Cotation_J30': 4}]
    conso_data = [{'ID_Lot': 'LOT-A', 'Date_Debut': str(today), 'Duree_Jours': 30, 'IC_Lot': 3.5, 'Marge_Alimentaire': 150.0, 'Efficacite': 'Excellente'}]
    # Saillies et Agnelages pour l'interface
    saillies_db = pd.DataFrame([{'ID_Saillie': 'S01', 'ID_Brebis': 'B01', 'Gest_Confirme': 'Oui', 'Date_Agnelage_Prevu': str(today + timedelta(days=10))}])
    agnelages_db = pd.DataFrame([{'ID_Agnelage': 'A01', 'Nombre_Vivants': 2}])
    return pd.DataFrame(beliers_data), pd.DataFrame(agneaux_data), saillies_db, agnelages_db, pd.DataFrame(conso_data)

# --- LOGIQUE DE CHARGEMENT ---
if 'initialized' not in st.session_state:
    init_db_structure()
    conn = get_db_connection()
    check = pd.read_sql("SELECT count(*) as total FROM beliers", conn).iloc[0]['total']
    if check == 0:
        b_demo, a_demo, s_demo, agn_demo, c_demo = init_demo_data()
        b_demo.to_sql('beliers', conn, if_exists='replace', index=False)
        a_demo.to_sql('agneaux', conn, if_exists='replace', index=False)
        c_demo.to_sql('consommation', conn, if_exists='replace', index=False)
        st.session_state.db_data, st.session_state.agneaux_db, st.session_state.consommation_lot_db = b_demo, a_demo, c_demo
    else:
        st.session_state.db_data = pd.read_sql("SELECT * FROM beliers", conn)
        st.session_state.agneaux_db = pd.read_sql("SELECT * FROM agneaux", conn)
        st.session_state.consommation_lot_db = pd.read_sql("SELECT * FROM consommation", conn)
    
    _, _, st.session_state.saillies_db, st.session_state.agnelages_db, _ = init_demo_data()
    conn.close()
    st.session_state.initialized = True

# ============================================================
# INTERFACE PRINCIPALE
# ============================================================

st.sidebar.title("🐏 BélierSelector Pro")
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "👶 Agneaux", "📸 Photogrammétrie", "⚙️ Gestion"])

if menu == "🏠 Dashboard":
    st.title("🏠 Tableau de Bord")
    col1, col2, col3 = st.columns(3)
    col1.metric("Béliers", len(st.session_state.db_data))
    col2.metric("Agneaux", len(st.session_state.agneaux_db))
    col3.metric("Lots", len(st.session_state.consommation_lot_db))
    st.dataframe(st.session_state.agneaux_db)

elif menu == "👶 Agneaux":
    st.title("👶 Suivi de la Nurserie")
    with st.expander("➕ Enregistrer une Naissance"):
        with st.form("new_born"):
            c1, c2, c3 = st.columns(3)
            id_a = c1.text_input("ID Agneau")
            père = c2.selectbox("Père", st.session_state.db_data['ID'].unique())
            poids = c3.number_input("Poids (kg)", value=4.0)
            if st.form_submit_button("Sauvegarder en Base de Données"):
                new_data = {'ID_Agneau': id_a, 'ID_Mere': 'Inconnue', 'ID_Pere': père, 'Date_Naissance': str(datetime.now().date()), 'Sexe': 'M', 'Poids_Naissance': poids, 'Poids_J30': 0, 'GMQ_J7_J30': 0, 'Cotation_J30': 0}
                sauvegarder_agneau_sql(new_data)
                st.session_state.agneaux_db = pd.concat([st.session_state.agneaux_db, pd.DataFrame([new_data])], ignore_index=True)
                st.success("Enregistré !")

elif menu == "📸 Photogrammétrie":
    st.title("📸 Analyse Morphologique")
    mode = st.radio("Méthode", ["Photo (IA)", "Saisie Manuelle (Secours)"], horizontal=True)
    if mode == "Saisie Manuelle (Secours)":
        with st.form("manual"):
            long = st.number_input("Longueur (cm)")
            haut = st.number_input("Hauteur (cm)")
            if st.form_submit_button("Calculer"):
                st.metric("Score Morphologique", round((long + haut)/2, 2))

elif menu == "⚙️ Gestion":
    st.title("⚙️ Paramètres & SQL")
    
    # Export/Import
    tab1, tab2 = st.tabs(["📤 Export/Import", "🗑️ Nettoyage"])
    with tab1:
        st.download_button("📥 Exporter Agneaux (Excel)", data=to_excel(st.session_state.agneaux_db), file_name="agneaux.xlsx")
    with tab2:
        to_del = st.selectbox("Supprimer un agneau", st.session_state.agneaux_db['ID_Agneau'].unique())
        if st.button("Confirmer la suppression"):
            if supprimer_animal_sql('agneaux', 'ID_Agneau', to_del):
                st.session_state.agneaux_db = st.session_state.agneaux_db[st.session_state.agneaux_db['ID_Agneau'] != to_del]
                st.rerun()
