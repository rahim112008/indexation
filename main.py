import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, Tuple, Optional, List
import time
import logging
import os
from dataclasses import dataclass

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 1. DESIGN & CSS
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; margin-bottom: 15px;
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }
    .metric-card h2 { color: #2E7D32; font-size: 28px; margin: 5px 0; }
    .metric-card p { color: #555555; font-weight: 600; text-transform: uppercase; font-size: 13px; margin:0; }
    .analysis-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #558b2f; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Erreur connexion SQLite: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        if conn: conn.close()

def check_and_migrate_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(mesures)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            
            columns_to_add = {
                'p_naiss': 'REAL DEFAULT 0.0',
                'p10': 'REAL DEFAULT 0.0',
                'p30': 'REAL DEFAULT 0.0'
            }
            
            for col_name, col_type in columns_to_add.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE mesures ADD COLUMN {col_name} {col_type}")
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='latest_measurements'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE latest_measurements (
                        id_animal TEXT PRIMARY KEY,
                        last_mesure_id INTEGER,
                        FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE
                    )
                ''')
    except Exception as e:
        logger.error(f"Erreur migration: {e}")

def init_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT,
                sexe TEXT CHECK(sexe IN ('Bélier', 'Brebis', 'Agneau/elle')),
                statut_dentaire TEXT, date_indexation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS mesures (
                id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
                date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP, p_naiss REAL DEFAULT 0.0,
                p10 REAL DEFAULT 0.0, p30 REAL DEFAULT 0.0, p70 REAL DEFAULT 0.0,
                h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL, l_poitrine REAL,
                FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
        check_and_migrate_db()
    except Exception as e:
        st.error(f"❌ Erreur DB: {e}")

def update_latest_measurement(conn, animal_id: str):
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO latest_measurements (id_animal, last_mesure_id) '
                   'SELECT id_animal, MAX(id) FROM mesures WHERE id_animal = ?', (animal_id,))

# ==========================================
# 3. DONNÉES DE TEST
# ==========================================
def generate_test_data():
    races = ['Ouled Djellal', 'Sardi', 'Timahdite', 'Dman']
    sexes = ['Bélier', 'Brebis', 'Agneau/elle']
    data_list = []
    for i in range(1, 51):
        sexe = np.random.choice(sexes)
        p70 = np.random.normal(60 if sexe=='Bélier' else 40, 10)
        data = {
            'id': f'TEST_{i:03d}', 'race': np.random.choice(races), 'sexe': sexe,
            'statut_dentaire': 'Adulte', 'objectif': 'Reproduction',
            'p_naiss': 4.0, 'p10': 8.0, 'p30': 15.0, 'p70': round(p70, 1),
            'h_garrot': 75.0, 'c_canon': 8.5, 'p_thoracique': 88.0, 'l_corps': 82.0
        }
        data_list.append(data)
    return data_list

def insert_test_data():
    try:
        test_data = generate_test_data()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for data in test_data:
                cursor.execute("INSERT OR IGNORE INTO beliers (id, race, objectif, sexe, statut_dentaire) VALUES (?,?,?,?,?)",
                             (data['id'], data['race'], data['objectif'], data['sexe'], data['statut_dentaire']))
                cursor.execute("INSERT INTO mesures (id_animal, p_naiss, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?,?,?)",
                             (data['id'], data['p_naiss'], data['p10'], data['p30'], data['p70'], data['h_garrot'], data['c_canon'], data['p_thoracique'], data['l_corps']))
                update_latest_measurement(conn, data['id'])
        return len(test_data), 0, None
    except Exception as e: return 0, 50, str(e)

# ==========================================
# 4. MOTEUR DE CALCULS VECTORISÉ
# ==========================================
def calculer_composition_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    df = df.copy()
    
    # Correction de l'Indice de Conformation (IC) : Standard Zootechnique
    # Un IC élevé signifie un animal compact et musclé
    df['IC'] = np.where(df['h_garrot'] > 0, (df['p_thoracique'] / df['h_garrot']) * 100, 0)
    
    # Calcul Muscle et Gras
    df['Gras_mm'] = np.clip((df['p70'] * 0.12) + (df['IC'] * 0.05) - 5, 1.5, 20)
    df['Pct_Muscle'] = np.clip(50 + (df['IC'] * 0.1) - (df['c_canon'] * 0.5), 40, 70)
    df['Pct_Gras'] = np.clip((df['Gras_mm'] * 1.2) + 5, 8, 35)
    df['Pct_Os'] = 100 - df['Pct_Muscle'] - df['Pct_Gras']
    
    # EUROP
    conds = [df['IC'] > 125, df['IC'] > 118, df['IC'] > 112, df['IC'] > 105]
    df['EUROP'] = np.select(conds, ['S', 'E', 'U', 'R'], default='O')
    
    df['S90'] = (df['Pct_Muscle'] * 1.2) - (df['Pct_Gras'] * 0.4)
    df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
    
    threshold = df['Index'].quantile(0.85) if len(df) > 1 else 0
    df['Statut'] = np.where(df['Index'] >= threshold, "⭐ ELITE PRO", "Standard")
    
    return df.round(1)

def load_data():
    with get_db_connection() as conn:
        query = """
            SELECT b.*, m.p70, m.h_garrot, m.p_thoracique, m.c_canon, m.l_corps, m.p_naiss, m.p10, m.p30
            FROM beliers b
            LEFT JOIN latest_measurements lm ON b.id = lm.id_animal
            LEFT JOIN mesures m ON lm.last_mesure_id = m.id
        """
        df = pd.read_sql(query, conn)
    return calculer_composition_vectorized(df)

# ==========================================
# 5. INTERFACE
# ==========================================
def main():
    init_db()
    if 'data_refresh' not in st.session_state: st.session_state.data_refresh = False
    
    df = load_data()
    
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty:
            st.info("Utilisez l'onglet Admin pour générer des données de test.")
        else:
            # Métriques
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sujets", len(df))
            c2.metric("Elite", len(df[df['Statut'] != "Standard"]))
            c3.metric("Muscle Moy.", f"{df['Pct_Muscle'].mean():.1f}%")
            c4.metric("Gras Moy.", f"{df['Gras_mm'].mean():.1f}mm")
            
            # Graphiques
            col1, col2 = st.columns(2)
            with col1:
                fig = px.scatter(df, x="p70", y="Pct_Muscle", color="Statut", title="Muscle vs Poids")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig_pie = px.pie(df, names='EUROP', title="Répartition EUROP")
                st.plotly_chart(fig_pie, use_container_width=True)
                

            st.subheader("📋 Liste des Sujets")
            st.dataframe(df[['id', 'race', 'sexe', 'p70', 'Pct_Muscle', 'EUROP', 'Statut', 'Index']], use_container_width=True)

    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de Carcasse")
        if not df.empty:
            target = st.selectbox("Animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            
            c1, c2 = st.columns([2,1])
            with c1:
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=[subj['Pct_Muscle'], subj['Pct_Gras'], subj['Pct_Os'], subj['IC']/2],
                    theta=['Muscle %', 'Gras %', 'Os %', 'Conformation'], fill='toself'
                ))
                st.plotly_chart(fig_radar, use_container_width=True)
                
            with c2:
                st.markdown(f"""<div class='analysis-box'><h3>ID: {target}</h3>
                <b>Classe:</b> {subj['EUROP']}<br><b>Muscle:</b> {subj['Pct_Muscle']}%<br>
                <b>Gras:</b> {subj['Gras_mm']}mm<br><b>Index:</b> {subj['Index']}</div>""", unsafe_allow_html=True)

    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("Générer 50 données de test"):
            ins, err, msg = insert_test_data()
            if ins > 0: st.success(f"{ins} sujets créés !"); st.rerun()
            else: st.error(f"Erreur: {msg}")
        
        if st.button("Tout supprimer"):
            with get_db_connection() as conn: 
                conn.execute("DELETE FROM beliers")
                conn.execute("DELETE FROM latest_measurements")
            st.rerun()

if __name__ == "__main__":
    main()
