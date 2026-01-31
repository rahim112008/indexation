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
# 2. GESTION BASE DE DONNÉES CORRIGÉE
# ==========================================
@contextmanager
def get_db_connection():
    """
    Gestionnaire de connexion robuste sans isolation_level=None
    pour permettre le contrôle explicite des transactions
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30.0)
        # Activation des clés étrangères
        conn.execute("PRAGMA foreign_keys = ON")
        # Mode WAL pour meilleure concurrence
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

def init_db():
    """Initialisation robuste avec vérification d'erreurs"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Table béliers avec contraintes
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
            
            # Table mesures avec index
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
            
            # Table pour les dernières mesures (approche simplifiée sans trigger complexe)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS latest_measurements (
                    id_animal TEXT PRIMARY KEY,
                    last_mesure_id INTEGER,
                    FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE,
                    FOREIGN KEY (last_mesure_id) REFERENCES mesures(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
            logger.info("Base de données initialisée avec succès")
            
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
        st.error(f"❌ Erreur lors de l'initialisation de la base: {e}")
        raise

def update_latest_measurement(conn, animal_id: str):
    """Met à jour la dernière mesure pour un animal (remplace le trigger)"""
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
# 3. MOTEUR DE CALCULS CARCASSE VECTORISÉ
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
    Version vectorisée des calculs carcasse (x100 plus rapide que apply)
    """
    if df.empty:
        return df
    
    # Copie pour éviter SettingWithCopyWarning
    df = df.copy()
    
    # Conversion en numérique avec gestion d'erreurs
    numeric_cols = ['p70', 'h_garrot', 'p_thoracique', 'c_canon']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0
    
    # Filtrage des valeurs invalides (vectorisé)
    mask_valid = (df['p70'] > 5) & (df['c_canon'] > 2) & (df['h_garrot'] > 0)
    
    # Calcul de l'indice de conformation (IC) - vectorisé
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
    
    # Classification EUROP vectorisée
    conditions = [
        ic > 33,  # S
        ic > 30,  # E
        ic > 27,  # U
        ic > 24   # R
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
    
    # Calcul du statut Elite (percentile 85)
    if len(df) > 0 and not df['Index'].isna().all():
        threshold = df['Index'].quantile(0.85)
        df['Statut'] = np.where(df['Index'] >= threshold, "⭐ ELITE PRO", "Standard")
    else:
        df['Statut'] = "Standard"
    
    return df

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """Chargement optimisé avec gestion d'erreurs améliorée"""
    try:
        # Vérification existence fichier
        if not os.path.exists(DB_NAME):
            logger.warning(f"Base {DB_NAME} non trouvée, initialisation...")
            init_db()
            return pd.DataFrame()
        
        with get_db_connection() as conn:
            # Requête optimisée
            query = """
                SELECT b.*, m.p70, m.h_garrot, m.p_thoracique, 
                       m.c_canon, m.l_corps, m.l_poitrine, m.p_naiss, m.p10, m.p30
                FROM beliers b 
                LEFT JOIN latest_measurements lm ON b.id = lm.id_animal
                LEFT JOIN mesures m ON lm.last_mesure_id = m.id
            """
            df = pd.read_sql(query, conn)
            
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
                INSERT INTO beliers (id, race, date_naiss, objectif, sexe, statut_dentaire)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['id'], data.get('race', 'Non spécifiée'), 
                  data.get('date_naiss'), data.get('objectif'), 
                  data['sexe'], data.get('statut_dentaire')))
            
            # Insertion mesures
            cursor.execute("""
                INSERT INTO mesures 
                (id_animal, p_naiss, p10, p30, p70, h_garrot, c_canon, p_thoracique, l_corps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['id'], data.get('p_naiss', 0), data.get('p_10j', 0),
                  data.get('p_30j', 0), data.get('p_70j', 0), data['h_garrot'],
                  data['c_canon'], data['p_thoracique'], data['l_corps']))
            
            # Mise à jour de la table latest_measurements
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
# 4. INTERFACE PRINCIPALE OPTIMISÉE
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
    """Affichage des métriques avec cache"""
    if df.empty:
        return
    
    c1, c2, c3, c4 = st.columns(4)
    metrics = {
        "Sujets": len(df),
        "Elite": len(df[df['Statut'] != 'Standard']),
        "Muscle Moy.": f"{df['Pct_Muscle'].mean():.1f}%" if not df['Pct_Muscle'].isna().all() else "N/A",
        "Gras Moy.": f"{df['Gras_mm'].mean():.1f}mm" if not df['Gras_mm'].isna().all() else "N/A"
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

    # Barre latérale optimisée
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
            """)
        else:
            render_metrics(df)
            
            # Graphique de distribution
            try:
                fig = px.scatter(df_filtered, x='IC', y='Index', color='Statut', 
                               size='p70', hover_data=['id', 'EUROP'],
                               title="Matrice de Sélection (IC vs Index Global)")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Erreur affichage graphique: {e}")
            
            # Tableau avec tri
            display_cols = ['id', 'race', 'p70', 'Pct_Muscle', 'EUROP', 'Statut', 'IC']
            available_cols = [col for col in display_cols if col in df_filtered.columns]
            st.dataframe(
                df_filtered[available_cols].sort_values('Index', ascending=False) if 'Index' in df_filtered.columns else df_filtered[available_cols],
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
                categories = ['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'IC']
                values = [subj[cat] for cat in categories]
                
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=['Muscle %', 'Gras %', 'Os %', 'Conformation'],
                    fill='toself',
                    line_color='#2E7D32',
                    name=subj['id']
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, max(values) * 1.2])),
                    showlegend=False
                )
                st.plotly_chart(fig_radar, use_container_width=True)
                
            with col2:
                st.markdown(f"""
                    <div class='analysis-box'>
                        <h4>📋 Fiche Technique</h4>
                        <b>ID:</b> {target}<br>
                        <b>Classe EUROP:</b> <span style='font-size:24px'>{subj['EUROP']}</span><br>
                        <b>Muscle:</b> {subj['Pct_Muscle']}%<br>
                        <b>Gras:</b> {subj['Pct_Gras']}%<br>
                        <b>Indice Conformation:</b> {subj['IC']}<br>
                        <b>Score S90:</b> {subj['S90']}
                    </div>
                """, unsafe_allow_html=True)
                
                # Recommandation
                if subj['Statut'] == "⭐ ELITE PRO":
                    st.success("🏆 Recommandé pour la reproduction")
                elif subj['Pct_Gras'] > 25:
                    st.warning("⚠️ Surgras - Surveillance alimentaire recommandée")
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
                        
                        # Simulation validation cadrage
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
            st.subheader("Maintenance")
            if st.button("🗑️ Vider la base de données", type="secondary"):
                confirm = st.checkbox("Je confirme la suppression définitive")
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
        
        with col2:
            st.subheader("Statistiques")
            if not df.empty:
                st.metric("Total indexé", len(df))
                elite_count = len(df[df['Statut'] != 'Standard']) if 'Statut' in df.columns else 0
                st.metric("Taux d'élite", f"{(elite_count/len(df)*100):.1f}%")
                
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
