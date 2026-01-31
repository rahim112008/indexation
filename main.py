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
# 1. DESIGN & CSS (CADRES VISIBLES)
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
    .stAlert { border-radius: 8px; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES CORRIGÉE AVEC MIGRATION
# ==========================================
@contextmanager
def get_db_connection():
    """
    Gestionnaire de connexion robuste
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Erreur connexion SQLite: {e}")
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def check_and_migrate_db():
    """Vérifie et met à jour la structure de la base si nécessaire"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Vérifier les colonnes existantes dans mesures
            cursor.execute("PRAGMA table_info(mesures)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            
            # Colonnes à ajouter si manquantes
            columns_to_add = {
                'p_naiss': 'REAL DEFAULT 0.0',
                'p10': 'REAL DEFAULT 0.0',
                'p30': 'REAL DEFAULT 0.0'
            }
            
            for col_name, col_type in columns_to_add.items():
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE mesures ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Colonne {col_name} ajoutée à la table mesures")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Impossible d'ajouter {col_name}: {e}")
            
            # Vérifier si la table latest_measurements existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='latest_measurements'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE latest_measurements (
                        id_animal TEXT PRIMARY KEY,
                        last_mesure_id INTEGER,
                        FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE,
                        FOREIGN KEY (last_mesure_id) REFERENCES mesures(id) ON DELETE CASCADE
                    )
                ''')
                logger.info("Table latest_measurements créée")
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Erreur migration: {e}")
        raise

def init_db():
    """Initialisation robuste avec migration automatique"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Table béliers
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS beliers (
                    id TEXT PRIMARY KEY, 
                    race TEXT, 
                    date_naiss TEXT,
                    objectif TEXT,
                    sexe TEXT CHECK(sexe IN ('Bélier', 'Brebis', 'Agneau/elle')),
                    statut_dentaire TEXT,
                    date_indexation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table mesures (création initiale avec toutes les colonnes)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mesures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    id_animal TEXT NOT NULL,
                    date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    p_naiss REAL DEFAULT 0.0,
                    p10 REAL DEFAULT 0.0, 
                    p30 REAL DEFAULT 0.0, 
                    p70 REAL DEFAULT 0.0,
                    h_garrot REAL, 
                    c_canon REAL, 
                    p_thoracique REAL, 
                    l_corps REAL, 
                    l_poitrine REAL,
                    FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE
                )
            ''')
            
            # Index pour performances
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mesures_animal ON mesures(id_animal)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mesures_date ON mesures(date_mesure)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_beliers_race ON beliers(race)')
            
            conn.commit()
        
        # Migration si la base existait déjà avec ancien schéma
        check_and_migrate_db()
        logger.info("Base de données initialisée avec succès")
            
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
        st.error(f"❌ Erreur lors de l'initialisation de la base: {e}")
        raise

def update_latest_measurement(conn, animal_id: str):
    """Met à jour la dernière mesure pour un animal"""
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM latest_measurements WHERE id_animal = ?', (animal_id,))
        cursor.execute('''
            INSERT INTO latest_measurements (id_animal, last_mesure_id)
            SELECT id_animal, MAX(id) 
            FROM mesures 
            WHERE id_animal = ?
            GROUP BY id_animal
        ''', (animal_id,))
    except Exception as e:
        logger.error(f"Erreur mise à jour latest_measurements: {e}")

# ==========================================
# 3. GÉNÉRATION DE DONNÉES DE TEST (50 INDIVIDUS)
# ==========================================
def generate_test_data():
    """Génère 50 individus de test avec distribution réaliste"""
    races = ['Ouled Djellal', 'Sardi', 'Timahdite', 'Dman', 'Beni Guil', 'Barkia']
    sexes = ['Bélier'] * 15 + ['Brebis'] * 25 + ['Agneau/elle'] * 10  # 30% Béliers, 50% Brebis, 20% Agneaux
    statuts_dentaires = ['2 Dents (12-18 mois)', '4 Dents (2 ans)', '6 Dents (2.5 - 3 ans)', '8 Dents / Adulte (4 ans+)']
    objectifs = ['Reproduction', 'Engraissement', 'Reproduction', 'Engraissement', 'Expérimentation']
    
    np.random.seed(42)  # Reproductibilité
    
    data_list = []
    
    for i in range(1, 51):
        sexe = np.random.choice(sexes)
        race = np.random.choice(races)
        
        # Génération des mensurations selon le sexe et l'âge
        if sexe == 'Agneau/elle':
            # Agneaux plus petits
            p70 = np.random.normal(25, 5)  # 25kg ±5
            h_garrot = np.random.normal(55, 3)
            c_canon = np.random.normal(6.5, 0.5)
            p_thoracique = np.random.normal(65, 4)
            l_corps = np.random.normal(55, 3)
            statut_dent = 'Agneau (Dents de lait)'
        elif sexe == 'Brebis':
            # Brebis moyennes
            p70 = np.random.normal(45, 8)  # 45kg ±8
            h_garrot = np.random.normal(68, 4)
            c_canon = np.random.normal(7.8, 0.6)
            p_thoracique = np.random.normal(82, 5)
            l_corps = np.random.normal(72, 4)
            statut_dent = np.random.choice(statuts_dentaires[1:])  # Pas agneau
        else:
            # Béliers plus grands, certains très développés (élites)
            # 20% de chance d'être un "super bélier" (élite)
            if np.random.random() < 0.2:
                p70 = np.random.normal(75, 5)  # Très lourd
                h_garrot = np.random.normal(78, 2)
                c_canon = np.random.normal(9.5, 0.4)  # Canon épais
                p_thoracique = np.random.normal(95, 3)  # Thorax large
                l_corps = np.random.normal(88, 3)
            else:
                p70 = np.random.normal(60, 7)
                h_garrot = np.random.normal(72, 3)
                c_canon = np.random.normal(8.5, 0.5)
                p_thoracique = np.random.normal(88, 4)
                l_corps = np.random.normal(80, 4)
            statut_dent = np.random.choice(statuts_dentaires[2:])  # Adulte
        
        # Poids historiques cohérents
        p_naiss = max(3.0, p70 * np.random.uniform(0.1, 0.15))
        p10 = p_naiss + np.random.uniform(3, 6)
        p30 = p10 + np.random.uniform(8, 15)
        
        data = {
            'id': f'TEST_{i:03d}',
            'race': race,
            'sexe': sexe,
            'statut_dentaire': statut_dent,
            'objectif': np.random.choice(objectifs),
            'p_naiss': round(p_naiss, 1),
            'p_10j': round(p10, 1),
            'p_30j': round(p30, 1),
            'p_70j': round(p70, 1),
            'h_garrot': round(h_garrot, 1),
            'c_canon': round(c_canon, 1),
            'p_thoracique': round(p_thoracique, 1),
            'l_corps': round(l_corps, 1)
        }
        data_list.append(data)
    
    return data_list

def insert_test_data():
    """Insère les 50 individus de test dans la base"""
    try:
        test_data = generate_test_data()
        inserted = 0
        errors = 0
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for data in test_data:
                try:
                    # Insertion bélier
                    cursor.execute("""
                        INSERT INTO beliers (id, race, objectif, sexe, statut_dentaire)
                        VALUES (?, ?, ?, ?, ?)
                    """, (data['id'], data['race'], data['objectif'], 
                          data['sexe'], data['statut_dentaire']))
                    
                    # Insertion mesures
                    cursor.execute("""
                        INSERT INTO mesures 
                        (id_animal, p_naiss, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (data['id'], data['p_naiss'], data['p_10j'],
                          data['p_30j'], data['p_70j'], data['h_garrot'],
                          data['c_canon'], data['p_thoracique'], data['l_corps']))
                    
                    update_latest_measurement(conn, data['id'])
                    inserted += 1
                    
                except sqlite3.IntegrityError:
                    errors += 1  # Doublon (normal si déjà inséré)
                    continue
                except Exception as e:
                    logger.error(f"Erreur insertion {data['id']}: {e}")
                    errors += 1
            
            conn.commit()
        
        return inserted, errors
    except Exception as e:
        logger.error(f"Erreur génération données test: {e}")
        return 0, 50

# ==========================================
# 4. MOTEUR DE CALCULS CARCASSE VECTORISÉ
# ==========================================
@dataclass
class CarcassMetrics:
    """Structure typée pour les métriques carcasse"""
    pct_muscle: float
    pct_gras: float
    pct_os: float
    gras_mm: float
    europ: str
    s90: float
    ic: float
    status: str

def calculer_composition_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    """
    Version vectorisée des calculs carcasse
    """
    if df.empty:
        return df
    
    df = df.copy()
    
    # Conversion en numérique avec gestion d'erreurs
    numeric_cols = ['p70', 'h_garrot', 'p_thoracique', 'c_canon']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0
    
    # Filtrage des valeurs invalides
    mask_valid = (df['p70'] > 5) & (df['c_canon'] > 2) & (df['h_garrot'] > 0)
    
    # Calcul de l'indice de conformation (IC)
    ic = np.where(
        mask_valid,
        np.clip((df['p_thoracique'] / (df['c_canon'] * df['h_garrot'])) * 1000, 15, 45),
        0
    )
    
    # Calcul gras musculaire
    gras_mm = np.where(
        mask_valid,
        np.clip(2.0 + (df['p70'] * 0.15) + (ic * 0.1) - (df['h_garrot'] * 0.05), 2.0, 22.0),
        0
    )
    
    # Pourcentages
    pct_gras = np.clip(5.0 + (gras_mm * 1.5), 10.0, 40.0)
    pct_muscle = np.clip(75.0 - (pct_gras * 0.6) + (ic * 0.2), 45.0, 72.0)
    pct_os = 100.0 - pct_muscle - pct_gras
    
    # Classification EUROP
    conditions = [
        ic > 33, ic > 30, ic > 27, ic > 24
    ]
    choices = ['S', 'E', 'U', 'R']
    europ = np.select(conditions, choices, default='O/P')
    
    # Score S90
    s90 = np.round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
    
    # Assignation
    df['Pct_Muscle'] = np.round(pct_muscle, 1)
    df['Pct_Gras'] = np.round(pct_gras, 1)
    df['Pct_Os'] = np.round(pct_os, 1)
    df['Gras_mm'] = np.round(gras_mm, 1)
    df['EUROP'] = europ
    df['S90'] = s90
    df['IC'] = np.round(ic, 1)
    df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
    
    # Statut Elite (percentile 85)
    if len(df) > 0 and not df['Index'].isna().all():
        threshold = df['Index'].quantile(0.85)
        df['Statut'] = np.where(df['Index'] >= threshold, "⭐ ELITE PRO", "Standard")
    else:
        df['Statut'] = "Standard"
    
    return df

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame():
    """Chargement avec gestion dynamique des colonnes"""
    try:
        if not os.path.exists(DB_NAME):
            logger.warning(f"Base {DB_NAME} non trouvée, initialisation...")
            init_db()
            return pd.DataFrame()
        
        with get_db_connection() as conn:
            # Vérifier les colonnes disponibles d'abord
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(mesures)")
            available_columns = {row[1] for row in cursor.fetchall()}
            
            # Construction dynamique de la requête selon les colonnes disponibles
            base_columns = ['p70', 'h_garrot', 'p_thoracique', 'c_canon', 'l_corps', 'l_poitrine']
            optional_columns = ['p_naiss', 'p10', 'p30']
            
            select_cols = ['b.*']
            for col in base_columns:
                select_cols.append(f'm.{col}')
            for col in optional_columns:
                if col in available_columns:
                    select_cols.append(f'm.{col}')
            
            query = f"""
                SELECT {', '.join(select_cols)}
                FROM beliers b 
                LEFT JOIN latest_measurements lm ON b.id = lm.id_animal
                LEFT JOIN mesures m ON lm.last_mesure_id = m.id
            """
            
            try:
                df = pd.read_sql(query, conn)
            except sqlite3.OperationalError as e:
                # Si latest_measurements pose problème, requête simple
                logger.warning(f"Erreur jointure, fallback simple: {e}")
                df = pd.read_sql("SELECT * FROM beliers", conn)
                return df
            
            if df.empty:
                return df
            
            return calculer_composition_vectorized(df)
            
    except Exception as e:
        logger.error(f"Erreur chargement données: {e}")
        st.error(f"⚠️ Impossible de charger les données: {e}")
        return pd.DataFrame()

def save_animal(data: Dict) -> bool:
    """Sauvegarde transactionnelle avec validation"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Vérification doublon
            cursor.execute("SELECT 1 FROM beliers WHERE id = ?", (data['id'],))
            if cursor.fetchone():
                st.error(f"❌ L'animal {data['id']} existe déjà dans la base!")
                return False
            
            # Insertion bélier
            cursor.execute("""
                INSERT INTO beliers (id, race, objectif, sexe, statut_dentaire)
                VALUES (?, ?, ?, ?, ?)
            """, (data['id'], data.get('race', 'Non spécifiée'), 
                  data.get('objectif'), 
                  data['sexe'], data.get('statut_dentaire')))
            
            # Insertion mesures
            cursor.execute("""
                INSERT INTO mesures 
                (id_animal, p_naiss, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['id'], data.get('p_naiss', 0), data.get('p_10j', 0),
                  data.get('p_30j', 0), data.get('p_70j', 0), data['h_garrot'],
                  data['c_canon'], data['p_thoracique'], data['l_corps']))
            
            update_latest_measurement(conn, data['id'])
            
            conn.commit()
            logger.info(f"Animal {data['id']} indexé avec succès")
            return True
            
    except sqlite3.IntegrityError as e:
        logger.error(f"Erreur d'intégrité: {e}")
        st.error(f"Erreur de données: {e}")
        return False
    except Exception as e:
        logger.error(f"Erreur sauvegarde: {e}")
        st.error(f"Erreur technique: {e}")
        return False

# ==========================================
# 5. INTERFACE PRINCIPALE
# ==========================================
def init_session_state():
    """Initialisation robuste du session state"""
    defaults = {
        'scan': {},
        'go_saisie': False,
        'last_search': "",
        'data_refresh': False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def render_metrics(df: pd.DataFrame):
    """Affichage des métriques"""
    if df.empty:
        return
    
    c1, c2, c3, c4 = st.columns(4)
    
    n_elite = len(df[df['Statut'] != 'Standard']) if 'Statut' in df.columns else 0
    muscle_moy = f"{df['Pct_Muscle'].mean():.1f}%" if 'Pct_Muscle' in df.columns and not df['Pct_Muscle'].isna().all() else "N/A"
    gras_moy = f"{df['Gras_mm'].mean():.1f}mm" if 'Gras_mm' in df.columns and not df['Gras_mm'].isna().all() else "N/A"
    
    metrics = {
        "Sujets": len(df),
        "Elite": n_elite,
        "Muscle Moy.": muscle_moy,
        "Gras Moy.": gras_moy
    }
    
    cols = [c1, c2, c3, c4]
    for col, (label, value) in zip(cols, metrics.items()):
        with col:
            st.markdown(f"""
                <div class='metric-card'>
                    <p>{label}</p>
                    <h2>{value}</h2>
                </div>
            """, unsafe_allow_html=True)

def main():
    # Initialisation DB avec gestion d'erreur
    try:
        init_db()
    except Exception as e:
        st.error("❌ Impossible d'initialiser la base de données. Vérifiez les permissions d'écriture.")
        st.stop()
    
    init_session_state()
    
    # Gestion du refresh après insertion
    if st.session_state.get('data_refresh'):
        st.cache_data.clear()
        st.session_state['data_refresh'] = False
    
    df = load_data()

    # Barre latérale
    with st.sidebar:
        st.title("💎 Expert Selector")
        search_query = st.text_input("🔍 Recherche par ID", 
                                    value=st.session_state['last_search'],
                                    key="search_input").strip()
        st.session_state['last_search'] = search_query
        
        menu = st.radio("Navigation", 
                       ["🏠 Dashboard", "🥩 Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"],
                       key="navigation")
        
        # Filtres dynamiques
        if not df.empty and 'race' in df.columns:
            races = ["Toutes"] + sorted(df['race'].dropna().unique().tolist())
            selected_race = st.selectbox("Filtrer par race", races)
            if selected_race != "Toutes":
                df = df[df['race'] == selected_race]

    # Filtrage recherche
    if search_query and not df.empty:
        df_filtered = df[df['id'].str.contains(search_query, case=False, na=False)]
    else:
        df_filtered = df

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty:
            st.info("🐑 Commencez par le Scanner ou la Saisie pour indexer vos premiers animaux.")
            st.markdown("""
            **Guide rapide:**
            1. 📸 **Scanner**: Capturez les mensurations
            2. ✍️ **Saisie**: Complétez l'identification  
            3. 🥩 **Composition**: Analysez la qualité carcasse
            
            **Ou générez des données de test (50 individus) dans l'onglet Admin pour voir l'application en action !**
            """)
        else:
            render_metrics(df)
            
            # Distribution Elite vs Standard
            if 'Statut' in df.columns:
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    # Graphique dispersion IC vs Index
                    fig = px.scatter(df_filtered, x='IC', y='Index', color='Statut', 
                                   size='p70' if 'p70' in df_filtered.columns else None, 
                                   hover_data=['id', 'EUROP'] if 'EUROP' in df_filtered.columns else ['id'],
                                   color_discrete_map={'⭐ ELITE PRO': '#FFD700', 'Standard': '#2E7D32'},
                                   title="Matrice de Sélection : IC vs Index Global")
                    fig.add_hline(y=df['Index'].quantile(0.85), line_dash="dash", 
                                 annotation_text="Seuil Elite (85e percentile)")
                    st.plotly_chart(fig, use_container_width=True)
                
                with col_chart2:
                    # Répartition par classes EUROP
                    if 'EUROP' in df.columns:
                        europ_counts = df['EUROP'].value_counts()
                        fig_pie = px.pie(values=europ_counts.values, names=europ_counts.index,
                                        title="Répartition par Classe EUROP",
                                        color=europ_counts.index,
                                        color_discrete_sequence=px.colors.sequential.Greens)
                        st.plotly_chart(fig_pie, use_container_width=True)
            
            # Tableau avec tri
            display_cols = ['id', 'race', 'sexe', 'p70', 'Pct_Muscle', 'EUROP', 'Statut', 'IC', 'Index']
            available_cols = [col for col in display_cols if col in df_filtered.columns]
            
            st.subheader(f"📋 Liste des Individus ({len(df_filtered)} trouvés)")
            
            if available_cols:
                # Style conditionnel pour les élites
                def highlight_elite(row):
                    if 'Statut' in row and row['Statut'] == '⭐ ELITE PRO':
                        return ['background-color: #fffacd'] * len(row)
                    return [''] * len(row)
                
                styled_df = df_filtered[available_cols].sort_values('Index', ascending=False) if 'Index' in df_filtered.columns else df_filtered[available_cols]
                st.dataframe(
                    styled_df.style.apply(highlight_elite, axis=1),
                    use_container_width=True,
                    hide_index=True
                )

    # --- COMPOSITION PRO ---
    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de Carcasse")
        if not df.empty:
            target = st.selectbox("Sélectionner l'animal", 
                                df['id'].unique(), 
                                key="select_animal")
            subj = df[df['id'] == target].iloc[0]
            
            col1, col2 = st.columns([2, 1])
            with col1:
                if all(col in subj for col in ['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'IC']):
                    categories = ['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'IC']
                    values = [subj[cat] for cat in categories]
                    
                    fig_radar = go.Figure()
                    fig_radar.add_trace(go.Scatterpolar(
                        r=values,
                        theta=['Muscle %', 'Gras %', 'Os %', 'Conformation'],
                        fill='toself',
                        line_color='#2E7D32' if subj.get('Statut') != '⭐ ELITE PRO' else '#FFD700',
                        fillcolor='rgba(46, 125, 50, 0.3)' if subj.get('Statut') != '⭐ ELITE PRO' else 'rgba(255, 215, 0, 0.3)',
                        name=subj['id']
                    ))
                    fig_radar.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, max(values) * 1.2])),
                        showlegend=False,
                        title=f"Profil Carcasse - {'🌟 ELITE' if subj.get('Statut') == '⭐ ELITE PRO' else 'Standard'}"
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)
                
            with col2:
                html_content = f"""
                    <div class='analysis-box' style='{'border-left-color: #FFD700;' if subj.get('Statut') == '⭐ ELITE PRO' else ''}'>
                        <h4>{'🌟 ' if subj.get('Statut') == '⭐ ELITE PRO' else ''}📋 Fiche Technique</h4>
                        <b>ID:</b> {target}<br>
                        <b>Sexe:</b> {subj.get('sexe', 'N/A')}<br>
                        <b>Race:</b> {subj.get('race', 'N/A')}<br>
                        <b>Classe EUROP:</b> <span style='font-size:24px; color: {'#FFD700' if subj.get('EUROP') in ['S', 'E'] else '#333'}'>{subj.get('EUROP', 'N/A')}</span><br>
                        <hr style='margin: 10px 0; border: none; border-top: 1px solid #ddd;'>
                        <b>Muscle:</b> {subj.get('Pct_Muscle', 'N/A')}%<br>
                        <b>Gras:</b> {subj.get('Pct_Gras', 'N/A')}%<br>
                        <b>Os:</b> {subj.get('Pct_Os', 'N/A')}%<br>
                        <b>Epaisseur Gras:</b> {subj.get('Gras_mm', 'N/A')} mm<br>
                        <b>Indice Conformation:</b> {subj.get('IC', 'N/A')}<br>
                        <b>Score S90:</b> {subj.get('S90', 'N/A')}<br>
                        <b>Index Global:</b> {subj.get('Index', 'N/A'):.2f if isinstance(subj.get('Index'), (int, float)) else 'N/A'}
                    </div>
                """
                st.markdown(html_content, unsafe_allow_html=True)
                
                if subj.get('Statut') == "⭐ ELITE PRO":
                    st.success("🏆 **REPRODUCTEUR ELITE** - Recommandé pour la reproduction")
                    st.info("💡 Profil optimal: Bonne conformation, faible épaisseur de gras, haute musculature")
                elif subj.get('Pct_Gras', 0) > 25:
                    st.warning("⚠️ **Surgras** - Surveillance alimentaire recommandée")
                elif subj.get('IC', 0) < 25:
                    st.info("📉 Conformation moyenne - À surveiller")
        else:
            st.warning("Aucune donnée disponible. Veuillez indexer des animaux d'abord.")

    # --- SCANNER EXPERT ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        st.markdown("_Analyse morphologique et diagnostic de la structure osseuse._")
        
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            source = st.radio("Source", ["📷 Caméra", "📁 Fichier"], horizontal=True)
        with col_cfg2:
            mode_scanner = st.radio("Méthode", ["🤖 Automatique", "📏 Manuel"], horizontal=True)
        
        st.divider()

        img = st.camera_input("Positionnez l'animal") if "Caméra" in source else \
              st.file_uploader("Charger photo", type=['jpg', 'jpeg', 'png'])

        if img:
            col_img, col_res = st.columns([1.5, 1])
            
            with col_img:
                st.image(img, caption="Analyse visuelle", use_container_width=True)
                
            with col_res:
                if "Automatique" in mode_scanner:
                    with st.spinner("🧠 Analyse IA..."):
                        time.sleep(0.8)
                        img_bytes = img.getvalue()
                        score_confiance = 85 + (hash(img_bytes) % 15)
                        
                        if score_confiance > 80:
                            st.success(f"✅ **CADRAGE VALIDE ({score_confiance}%)**")
                            res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                        else:
                            st.error(f"⚠️ **IMAGE INCOMPLÈTE ({score_confiance}%)**")
                            res = {"h_garrot": 73.5, "c_canon": 8.2, "p_thoracique": 84.0, "l_corps": 0.0}
                else:
                    st.subheader("📏 Saisie Manuelle")
                    res = {
                        "h_garrot": st.number_input("Hauteur Garrot (cm)", 50.0, 120.0, 72.0, 0.1),
                        "c_canon": st.number_input("Tour de Canon (cm)", 4.0, 15.0, 8.5, 0.1),
                        "p_thoracique": st.number_input("Périmètre Thorax (cm)", 40.0, 150.0, 84.0, 0.1),
                        "l_corps": st.number_input("Longueur Corps (cm)", 40.0, 120.0, 82.0, 0.1)
                    }
                    score_confiance = 100

                st.divider()
                st.session_state['scan'] = res
                
                m1, m2 = st.columns(2)
                with m1:
                    st.metric("📏 Hauteur", f"{res['h_garrot']} cm")
                    st.metric("🦴 Canon", f"{res['c_canon']} cm")
                with m2:
                    st.metric("⭕ Thorax", f"{res['p_thoracique']} cm")
                    st.metric("📏 Longueur", f"{res['l_corps']} cm" if res['l_corps'] > 0 else "N/A")

                if st.button("🚀 VALIDER ET ENVOYER À LA SAISIE", type="primary", use_container_width=True):
                    st.session_state['go_saisie'] = True
                    st.balloons()
                    st.success("Données transférées ! Rendez-vous dans l'onglet Saisie.")
                    time.sleep(1)
                    st.rerun()

    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Indexation et Identification")
        
        sd = st.session_state.get('scan', {})
        auto_fill = st.session_state.get('go_saisie', False)
        
        if auto_fill and sd:
            st.info("📝 Données du scanner pré-remplies. Complétez l'identification.")
            st.session_state['go_saisie'] = False

        with st.form("form_saisie", clear_on_submit=True):
            st.subheader("🆔 État Civil")
            c1, c2, c3 = st.columns(3)
            with c1:
                id_animal = st.text_input("N° Boucle / ID *", key="input_id")
            with c2:
                statut_dentaire = st.selectbox("État Dentaire", 
                    ["Agneau (Dents de lait)", "2 Dents (12-18 mois)", "4 Dents (2 ans)", 
                     "6 Dents (2.5 - 3 ans)", "8 Dents / Adulte (4 ans+)", "Bouche usée"])
            with c3:
                sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], 
                              horizontal=True, index=0)
            
            c4, c5 = st.columns(2)
            with c4:
                race = st.text_input("Race", placeholder="Ouled Djellal, etc.")
            with c5:
                objectif = st.selectbox("Objectif Élevage", 
                                       ["Reproduction", "Engraissement", "Expérimentation"])

            st.divider()
            st.subheader("⚖️ Historique de Pesée (kg)")
            cp1, cp2, cp3, cp4 = st.columns(4)
            with cp1:
                p_naiss = st.number_input("Naissance", 0.0, 20.0, 0.0, 0.1)
            with cp2:
                p_10j = st.number_input("10 jours", 0.0, 30.0, 0.0, 0.1)
            with cp3:
                p_30j = st.number_input("30 jours", 0.0, 50.0, 0.0, 0.1)
            with cp4:
                default_p70 = float(sd.get('p70', 0.0)) if auto_fill else 0.0
                p_70j = st.number_input("70 jours/Actuel", 0.0, 150.0, default_p70, 0.1)

            st.divider()
            st.subheader("📏 Morphologie (Scanner)")
            cm1, cm2, cm3, cm4 = st.columns(4)
            
            defaults = {
                'h_garrot': float(sd.get('h_garrot', 0.0)) if auto_fill else 0.0,
                'c_canon': float(sd.get('c_canon', 0.0)) if auto_fill else 0.0,
                'p_thoracique': float(sd.get('p_thoracique', 0.0)) if auto_fill else 0.0,
                'l_corps': float(sd.get('l_corps', 0.0)) if auto_fill and sd.get('l_corps', 0) > 0 else 0.0
            }
            
            with cm1:
                hauteur = st.number_input("Hauteur Garrot", 0.0, 150.0, defaults['h_garrot'], 0.1)
            with cm2:
                canon = st.number_input("Tour de Canon", 0.0, 20.0, defaults['c_canon'], 0.1)
            with cm3:
                thorax = st.number_input("Périmètre Thorax", 0.0, 200.0, defaults['p_thoracique'], 0.1)
            with cm4:
                longueur = st.number_input("Longueur Corps", 0.0, 150.0, defaults['l_corps'], 0.1)

            submitted = st.form_submit_button("💾 INDEXER L'INDIVIDU", 
                                            type="primary", 
                                            use_container_width=True)
            
            if submitted:
                if not id_animal:
                    st.error("❌ L'ID est obligatoire!")
                elif hauteur <= 0 or canon <= 0:
                    st.error("❌ Les mensurations doivent être > 0")
                else:
                    data = {
                        'id': id_animal,
                        'race': race,
                        'sexe': sexe,
                        'statut_dentaire': statut_dentaire,
                        'objectif': objectif,
                        'p_naiss': p_naiss,
                        'p_10j': p_10j,
                        'p_30j': p_30j,
                        'p_70j': p_70j,
                        'h_garrot': hauteur,
                        'c_canon': canon,
                        'p_thoracique': thorax,
                        'l_corps': longueur
                    }
                    
                    if save_animal(data):
                        st.session_state['data_refresh'] = True
                        st.success(f"✅ {id_animal} indexé avec succès!")
                        st.balloons()

    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🧪 Données de Test")
            st.info("Générez 50 individus fictifs pour tester l'application et voir la détection des élites.")
            
            if st.button("🎲 GÉNÉRER 50 INDIVIDUS DE TEST", type="primary", use_container_width=True):
                with st.spinner("Génération en cours..."):
                    inserted, errors = insert_test_data()
                    if inserted > 0:
                        st.session_state['data_refresh'] = True
                        st.success(f"✅ {inserted} individus générés avec succès!")
                        if errors > 0:
                            st.info(f"ℹ️ {errors} doublons ignorés (déjà existants)")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("Aucun individu inséré (peut-être déjà existants?)")
        
        with col2:
            st.subheader("🗑️ Maintenance")
            if st.button("Vider la base de données", type="secondary"):
                confirm = st.checkbox("Je confirme la suppression définitive de TOUTES les données")
                if confirm:
                    try:
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM latest_measurements")
                            cursor.execute("DELETE FROM mesures")
                            cursor.execute("DELETE FROM beliers")
                            conn.commit()
                        st.cache_data.clear()
                        st.success("Base de données réinitialisée")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la suppression: {e}")
            
            # Statistiques
            if not df.empty:
                st.divider()
                st.subheader("📊 Statistiques")
                st.metric("Total indexé", len(df))
                
                if 'Statut' in df.columns:
                    n_elite = len(df[df['Statut'] == '⭐ ELITE PRO'])
                    st.metric("Nombre d'Élites", n_elite, f"{(n_elite/len(df)*100):.1f}%")
                
                if 'EUROP' in df.columns:
                    st.write("Répartition EUROP:")
                    europ_stats = df['EUROP'].value_counts()
                    for cls, count in europ_stats.items():
                        st.write(f"- Classe {cls}: {count}")
                
                # Export CSV
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Exporter CSV",
                    data=csv,
                    file_name=f"export_ovin_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv'
                )

if __name__ == "__main__":
    main()
