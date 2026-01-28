import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import math
import sqlite3 # Ajout de la bibliothèque SQL

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
    
    # Table Béliers
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (ID TEXT PRIMARY KEY, Race TEXT, Age REAL, BCS REAL, PoidsActuel REAL, 
                  GMQ REAL, DateDernierePesee TEXT, Score_Global REAL, ProchainesPesees TEXT)''')
    
    # Table Agneaux
    c.execute('''CREATE TABLE IF NOT EXISTS agneaux 
                 (ID_Agneau TEXT PRIMARY KEY, ID_Mere TEXT, ID_Pere TEXT, 
                  Date_Naissance TEXT, Sexe TEXT, Poids_Naissance REAL, 
                  Poids_J30 REAL, GMQ_J7_J30 REAL, Cotation_J30 REAL)''')
    
    # Table Consommation
    c.execute('''CREATE TABLE IF NOT EXISTS consommation 
                 (ID_Lot TEXT PRIMARY KEY, Date_Debut TEXT, Duree_Jours INTEGER, 
                  IC_Lot REAL, Marge_Alimentaire REAL, Efficacite TEXT)''')
    
    conn.commit()
    conn.close()

def sauvegarder_agneau_sql(data_dict):
    """Fonction pour enregistrer un nouvel agneau en base de données"""
    conn = get_db_connection()
    try:
        df = pd.DataFrame([data_dict])
        df.to_sql('agneaux', conn, if_exists='append', index=False)
        conn.commit()
    except Exception as e:
        st.error(f"Erreur sauvegarde SQL : {e}")
    finally:
        conn.close()

# ============================================================
# INITIALISATION ET SYNCHRONISATION
# ============================================================

# Appel des fonctions utilitaires (calculer_gmq, safe_json, etc. - gardez vos versions)
# [Ici vos fonctions utilitaires existantes...]

def init_demo_data():
    """Vos données de démo actuelles (Version abrégée pour l'exemple)"""
    # ... (Copiez ici votre fonction init_demo_data originale) ...
    return pd.DataFrame(beliers_data), pd.DataFrame(agneaux_data), pd.DataFrame(saillies_data), \
           pd.DataFrame(agnelages_data), pd.DataFrame(conso_data)

# --- LOGIQUE DE CHARGEMENT HYBRIDE (SQL + SESSION) ---
if 'initialized' not in st.session_state:
    init_db_structure()
    conn = get_db_connection()
    
    # Vérifier si la base de données est vide
    check_empty = pd.read_sql("SELECT count(*) as total FROM beliers", conn).iloc[0]['total']
    
    if check_empty == 0:
        # La base est neuve : on injecte la démo
        b_demo, a_demo, s_demo, agn_demo, c_demo = init_demo_data()
        
        # Sauvegarde initiale dans SQL
        b_demo.to_sql('beliers', conn, if_exists='replace', index=False)
        a_demo.to_sql('agneaux', conn, if_exists='replace', index=False)
        c_demo.to_sql('consommation', conn, if_exists='replace', index=False)
        
        st.session_state.db_data = b_demo
        st.session_state.agneaux_db = a_demo
        st.session_state.consommation_lot_db = c_demo
    else:
        # La base contient déjà des données : on les charge
        st.session_state.db_data = pd.read_sql("SELECT * FROM beliers", conn)
        st.session_state.agneaux_db = pd.read_sql("SELECT * FROM agneaux", conn)
        st.session_state.consommation_lot_db = pd.read_sql("SELECT * FROM consommation", conn)
    
    # Saillies et Agnelages restent en démo pour cet exemple (ou à ajouter en SQL)
    _, _, st.session_state.saillies_db, st.session_state.agnelages_db, _ = init_demo_data()
    
    conn.close()
    st.session_state.initialized = True
