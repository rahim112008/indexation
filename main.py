import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
from datetime import datetime, timedelta
import io
from contextlib import contextmanager

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

DB_NAME = "expert_ultra_final.db"

@contextmanager
def get_db_connection():
    """Gestionnaire de contexte pour les connexions DB"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# --- 2. LOGIQUE SCIENTIFIQUE & IA ---
def identifier_champions(df):
    """Identifie les champions Élite (top 15% P70 et Canon)"""
    if df.empty or len(df) < 5:
        df['Statut'] = ""
        return df
    
    seuil_p70 = df['p70'].quantile(0.85)
    seuil_canon = df['c_canon'].quantile(0.85)
    
    conditions = (df['p70'] >= seuil_p70) & (df['c_canon'] >= seuil_canon)
    df['Statut'] = np.where(conditions, "⭐ Élite", "")
    return df

def calculer_metrics(row, mode="Viande"):
    """
    Calcule GMQ, Rendement et Index de sélection
    Retourne: (GMQ, Rendement, Index)
    """
    try:
        if row['p70'] <= 0 or row['p30'] <= 0:
            return 0.0, 0.0, 0.0
        
        # Gain Moyen Quotidien (g/jour)
        gmq = ((row['p70'] - row['p30']) / 40) * 1000
        
        # Formule de rendement estimée (corrigée avec vérifications)
        rendement = 52.4 + (0.35 * row.get('l_poitrine', 24)) + \
                   (0.12 * row.get('p_thoracique', 80)) - \
                   (0.08 * row.get('h_garrot', 75))
        rendement = max(min(rendement, 65.0), 40.0)
        
        # Calcul de l'index selon l'objectif
        if mode == "Viande":
            index = (gmq * 0.15) + (rendement * 0.55) + (row['p70'] * 0.3)
        else:  # Mode Reproduction
            index = (row.get('c_canon', 10) * 4.0) + \
                   (row.get('h_garrot', 75) * 0.3) + \
                   (gmq * 0.03)
        
        return round(gmq, 1), round(rendement, 1), round(index, 2)
    
    except Exception as e:
        st.error(f"Erreur calcul métriques: {e}")
        return 0.0, 0.0, 0.0

# --- 3. INITIALISATION DB ---
def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        # Table des béliers avec contraintes
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT NOT NULL, 
                date_naiss TEXT, 
                objectif TEXT, 
                dentition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Table des mesures avec clé étrangère
        c.execute('''
            CREATE TABLE IF NOT EXISTS mesures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_animal TEXT NOT NULL,
                p10 REAL CHECK(p10 >= 0),
                p30 REAL CHECK(p30 >= 0),
                p70 REAL CHECK(p70 >= 0),
                h_garrot REAL,
                l_corps REAL,
                p_thoracique REAL,
                l_poitrine REAL,
                c_canon REAL,
                date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE
            )
        ''')
        # Index pour performances
        c.execute('CREATE INDEX IF NOT EXISTS idx_mesures_animal ON mesures(id_animal)')

init_db()

# --- 4. NAVIGATION ---
st.sidebar.title("💎 Selector Ultra")
st.sidebar.info("Expert Mode : IA & Biométrie")

# Génération de données démo améliorée
if st.sidebar.button("🚀 GÉNÉRER 500 SUJETS (DÉMO)"):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            races = ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "D'man"]
            
            data_beliers = []
            data_mesures = []
            
            for i in range(500):
                a_id = f"REF-{5000 + i}"
                race = random.choice(races)
                
                # Génération cohérente des poids (croissance réaliste)
                p10 = round(random.uniform(4, 6), 1)
                p30 = round(p10 + random.uniform(8, 12), 1)  # Gain J10-J30
                p70 = round(p30 + random.uniform(18, 25), 1)  # Gain J30-J70
                
                # Biométrie corrélée au poids
                hg = round(65 + (p70 * 0.25) + random.uniform(-2, 2), 1)
                cc = round(7.5 + (p70 * 0.09) + random.uniform(-0.5, 0.5), 1)
                pt = round(hg * 1.15 + random.uniform(-3, 3), 1)
                lp = round(20 + (p70 * 0.05), 1)
                
                date_naiss = (datetime.now() - timedelta(days=random.randint(70, 300))).strftime("%Y-%m-%d")
                
                data_beliers.append((a_id, race, date_naiss, "Sélection", "2 Dents"))
                data_mesures.append((a_id, p10, p30, p70, hg, 80.0, pt, lp, cc))
            
            c.executemany("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,NULL)", data_beliers)
            c.executemany("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon) VALUES (?,?,?,?,?,?,?,?,?)", data_mesures)
            
        st.sidebar.success(f"✅ {len(data_beliers)} sujets injectés avec succès !")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ Erreur: {e}")

menu = st.sidebar.radio("Navigation", [
    "🏠 Dashboard", 
    "📸 Scanner IA", 
    "📈 Analyse Scientifique", 
    "✍️ Saisie Manuelle"
])

# Chargement des données avec cache
@st.cache_data(ttl=30)
def load_data():
    try:
        with get_db_connection() as conn:
            query = """
                SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, 
                       m.p_thoracique, m.l_poitrine, m.c_canon, m.date_mesure
                FROM beliers b
                LEFT JOIN mesures m ON b.id = m.id_animal
                WHERE m.id = (SELECT MAX(id) FROM mesures WHERE id_animal = b.id)
            """
            df = pd.read_sql(query, conn)
            
            if not df.empty:
                # Calcul vectorisé des métriques
                metrics = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
                df[['GMQ', 'Rendement', 'Index']] = metrics
                df = identifier_champions(df)
            return df
    except Exception as e:
        st.error(f"Erreur chargement données: {e}")
        return pd.DataFrame()

df = load_data()

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("🏆 Tableau de Bord du Troupeau")
    
    if not df.empty:
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sujets", len(df))
        with col2:
            nb_elites = len(df[df['Statut'] == "⭐ Élite"])
            st.metric("Nombre d'Élites ⭐", nb_elites, f"{nb_elites/len(df)*100:.1f}%")
        with col3:
            st.metric("Index Moyen", f"{df['Index'].mean():.1f}")
        with col4:
            st.metric("GMQ Moyen", f"{df['GMQ'].mean():.0f} g/j")
        
        # Filtres
        st.subheader("🔍 Filtrage")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            race_filter = st.multiselect("Race", options=df['race'].unique(), default=df['race'].unique())
        with col_f2:
            statut_filter = st.selectbox("Statut", ["Tous", "Élite uniquement", "Standard uniquement"])
        
        # Application des filtres
        df_filtered = df[df['race'].isin(race_filter)]
        if statut_filter == "Élite uniquement":
            df_filtered = df_filtered[df_filtered['
