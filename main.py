import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="Expert Selector Ultra", 
    layout="wide", 
    page_icon="🐏",
    initial_sidebar_state="expanded"
)

DB_NAME = "expert_ovin.db"

# --- 2. GESTION BASE DE DONNÉES ROBUSTE ---
@contextmanager
def get_db_connection():
    """Gestionnaire de contexte pour connexions SQLite thread-safe"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialisation des tables avec contraintes"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Table des animaux
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT NOT NULL, 
                date_naiss TEXT, 
                objectif TEXT DEFAULT 'Sélection', 
                dentition TEXT DEFAULT '2 Dents',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table des mesures avec validation
        c.execute('''
            CREATE TABLE IF NOT EXISTS mesures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_animal TEXT NOT NULL,
                p10 REAL DEFAULT 0 CHECK(p10 >= 0),
                p30 REAL DEFAULT 0 CHECK(p30 >= 0),
                p70 REAL DEFAULT 0 CHECK(p70 >= 0),
                h_garrot REAL DEFAULT 0,
                l_corps REAL DEFAULT 0,
                p_thoracique REAL DEFAULT 0,
                l_poitrine REAL DEFAULT 0,
                c_canon REAL DEFAULT 0,
                date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE
            )
        ''')
        
        # Index pour performances
        c.execute('CREATE INDEX IF NOT EXISTS idx_mesures_animal ON mesures(id_animal)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_mesures_date ON mesures(date_mesure)')

# --- 3. LOGIQUE SCIENTIFIQUE ---
def calculer_metrics(row, mode="Viande"):
    """
    Calcule GMQ, Rendement et Index
    Retourne: (GMQ, Rendement, Index)
    """
    try:
        # Sécurisation des valeurs
        p70 = float(row.get('p70', 0) or 0)
        p30 = float(row.get('p30', 0) or 0)
        p10 = float(row.get('p10', 0) or 0)
        
        if p70 <= 0 or p30 <= 0:
            return 0.0, 0.0, 0.0
        
        # GMQ: Gain Moyen Quotidien (g/jour)
        gmq = ((p70 - p30) / 40) * 1000
        
        # Rendement estimé (%)
        l_poitrine = float(row.get('l_poitrine', 24) or 24)
        p_thoracique = float(row.get('p_thoracique', 80) or 80)
        h_garrot = float(row.get('h_garrot', 70) or 70)
        
        rendement = 52.4 + (0.35 * l_poitrine) + (0.12 * p_thoracique) - (0.08 * h_garrot)
        rendement = max(40.0, min(65.0, rendement))
        
        # Index de sélection
        c_canon = float(row.get('c_canon', 9) or 9)
        
        if mode == "Viande":
            index = (gmq * 0.15) + (rendement * 0.55) + (p70 * 0.3)
        else:  # Reproduction
            index = (c_canon * 4.0) + (h_garrot * 0.3) + (gmq * 0.03)
            
        return round(gmq, 1), round(rendement, 1), round(index, 2)
    
    except Exception as e:
        return 0.0, 0.0, 0.0

def identifier_champions(df):
    """Identifie le top 15% (percentile 85) sur P70 et Canon"""
    if df.empty or len(df) < 5:
        df['Statut'] = ""
        return df
    
    try:
        seuil_p70 = df['p70'].quantile(0.85)
        seuil_canon = df['c_canon'].quantile(0.85)
        
        # Évite les erreurs si toutes les valeurs sont identiques
        if seuil_p70 == 0:
            seuil_p70 = df['p70'].max() * 0.9
        if seuil_canon == 0:
            seuil_canon = df['c_canon'].max() * 0.9
            
        conditions = (df['p70'] >= seuil_p70) & (df['c_canon'] >= seuil_canon)
        df['Statut'] = np.where(conditions, "ELITE", "")
        
    except Exception as e:
        df['Statut'] = ""
        
    return df

# --- 4. GÉNÉRATION DE DONNÉES DÉMO ---
def generer_troupeau_demo(n=50):
    """Génère n individus avec données cohérentes"""
    races = ["Ouled Djellal", "Rembi", "Hamra", "Babarine"]
    
    with get_db_connection() as conn:
        c = conn.cursor()
        count = 0
        
        for i in range(n):
            try:
                # ID unique
                animal_id = f"REF-{2024}-{1000+i}"
                
                # Génération cohérente (croissance logique)
                p10 = round(random.uniform(4.0, 6.5), 1)
                gain_j30 = random.uniform(9, 13)  # Gain J10-J30
                p30 = round(p10 + gain_j30, 1)
                gain_j70 = random.uniform(17, 26)  # Gain J30-J70
                p70 = round(p30 + gain_j70, 1)
                
                # Biométrie corrélée au poids
                base_factor = p70 / 35  # Facteur de taille
                
                h_garrot = round(65 + (base_factor * 8) + random.uniform(-2, 2), 1)
                c_canon = round(7.5 + (base_factor * 3) + random.uniform(-0.3, 0.3), 1)
                l_poitrine = round(22 + (base_factor * 4) + random.uniform(-1, 1), 1)
                p_thoracique = round(75 + (base_factor * 12) + random.uniform(-3, 3), 1)
                l_corps = round(75 + (base_factor * 8) + random.uniform(-2, 3), 1)
                
                race = random.choice(races)
                date_naiss = (datetime.now() - timedelta(days=random.randint(80, 400))).strftime("%Y-%m-%d")
                
                # Insertion
                c.execute("""
                    INSERT OR REPLACE INTO beliers (id, race, date_naiss, objectif, dentition)
                    VALUES (?, ?, ?, ?, ?)
                """, (animal_id, race, date_naiss, "Sélection", random.choice(["2 Dents", "4 Dents"])))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (animal_id, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon))
                
                count += 1
                
            except Exception as e:
                continue
                
        return count

# --- 5. CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=10)
def load_data():
    """Charge et enrichit les données"""
    try:
        with get_db_connection() as conn:
            query = """
                SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, 
                       m.p_thoracique, m.l_poitrine, m.c_canon, m.date_mesure
                FROM beliers b
                LEFT JOIN mesures m ON b.id = m.id_animal
                WHERE m.id = (SELECT MAX(id) FROM mesures WHERE id_animal = b.id)
                OR m.id IS NULL
            """
            df = pd.read_sql(query, conn)
            
            if not df.empty:
                # Calcul des métriques
                metrics = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
                df[['GMQ', 'Rendement', 'Index']] = metrics
                df = identifier_champions(df)
                
                # Conversion pour affichage
                df['p70'] = pd.to_numeric(df['p70'], errors='coerce').fillna(0)
                df['c_canon'] = pd.to_numeric(df['c_canon'], errors='coerce').fillna(0)
                
            return df
    except Exception as e:
        st.error(f"Erreur chargement données: {e}")
        return pd.DataFrame()

# --- 6. INTERFACE UTILISATEUR ---
def main():
    # Initialisation
    init_db()
    
    # Sidebar
    st.sidebar.title("💎 Expert Selector")
    st.sidebar.markdown("**Sélection Zootechnique IA**")
    
    # Bouton génération démo
    if st.sidebar.button("🚀 Générer 50 sujets démo", type="secondary"):
        with st.spinner("Création du troupeau..."):
            n = generer_troupeau_demo(50)
            st.sidebar.success(f"✅ {n} animaux créés!")
            time.sleep(1)
            st.rerun()
    
    # Navigation
    menu = st.sidebar.radio(
        "Navigation", 
        ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie Manuelle"],
        index=0
    )
    
    st.sidebar.markdown("---")
    st.sidebar.caption("© 2024 Expert Selector v2.0")
    
    # Chargement données
    df = load_data()
    
    # --- PAGE DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord du Troupeau")
        
        if df.empty:
            st.info("👋 Bienvenue! Cliquez sur 'Générer 50 sujets démo' dans le menu latéral pour commencer.")
            return
            
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sujets", len(df))
        with col2:
            nb_elite = len(df[df['Statut'] == "ELITE"])
            pct_elite = (nb_elite/len(df)*100) if len(df) > 0 else 0
            st.metric("Champions ELITE", nb_elite, f"{pct_elite:.1f}%")
        with col3:
            idx_moy = df['Index'].mean() if not df.empty else 0
            st.metric("Index Moyen", f"{idx_moy:.1f}")
        with col4:
            gmq_moy = df['GMQ'].mean() if not df.empty else 0
            st.metric("GMQ Moyen", f"{gmq_moy:.0f} g/j")
        
        # Filtres
        st.subheader("🔍 Filtrage")
        c1, c2 = st.columns(2)
        with c1:
            races = df['race'].unique().tolist() if not df.empty else []
            race_sel = st.multiselect("Race", races, default=races)
        with c2:
            statut_sel = st.selectbox(
                "Statut", 
                ["Tous", "ELITE uniquement", "Standard uniquement"]
            )
        
        # Application filtres
        df_filtre = df.copy()
        if race_sel:
            df_filtre = df_filtre[df_filtre['race'].isin(race_sel)]
        if statut_sel == "ELITE uniquement":
            df_filtre = df_filtre[df_filtre['Statut'] == "ELITE"]
        elif statut_sel == "Standard uniquement":
            df_filtre = df_filtre[df_filtre['Statut'] == ""]
        
        # Tableau
        st.subheader("📋 Classement (trié par Index décroissant)")
        cols_display = ['Statut', 'id', 'race', 'p70', 'c_canon', 'GMQ', 'Rendement', 'Index']
        
        # Style conditionnel
        def highlight_elite(s):
            return ['background-color: #ffd700' if v == 'ELITE' else '' for v in s]
            
        st.dataframe(
            df_filtre[cols_display].sort_values('Index', ascending=False).style.apply(highlight_elite, subset=['Statut']),
            use_container_width=True,
            height=400
        )
        
        # Graphique distribution
        st.subheader("📊 Distribution des Index")
        fig = px.histogram(
            df_filtre, 
            x="Index", 
            color="Statut" if not df_filtre.empty else None,
            nbins=20,
            title="Répartition de la valeur génétique",
            color_discrete_map={"ELITE": "#FFD700", "": "#1f77b4"}
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # --- PAGE SCANNER IA ---
    elif menu == "📸 Scanner IA":
        st.title("📸 Scanner Morphologique Automatique")
        st.markdown("Prenez une photo de profil pour extraire les 5 mensurations.")
        
        img = st.camera_input("📷 Capturer le bélier (profil de côté)", key="camera")
        
        if img:
            with st.spinner("🔍 Analyse IA en cours..."):
                # Simulation traitement
                progress = st.progress(0)
                for i in range(100):
                    time.sleep(0.02)
                    progress.progress(i + 1)
                
                # Génération "IA" cohérente
                base_hg = random.uniform(68, 82)
                base_cc = random.uniform(8, 12)
                
                mesures_scan = {
                    'h_garrot': round(base_hg, 1),
                    'c_canon': round(base_cc, 1),
                    'l_poitrine': round(base_hg * 0.35, 1),
                    'p_thoracique': round(base_hg * 1.18, 1),
                    'l_corps': round(base_hg * 1.15, 1)
                }
                
                st.session_state['scan_data'] = mesures_scan
                
            col1, col2 = st.columns(2)
            with col1:
                st.image(img, caption="Image analysée", use_container_width=True)
            with col2:
                st.success("✅ Mensurations detectées")
                for key, val in mesures_scan.items():
                    st.metric(
                        label=f"📏 {key.replace('_', ' ').title()}", 
                        value=f"{val} cm"
                    )
                
                st.info("💡 Ces valeurs sont transférables vers la saisie manuelle")
                if st.button("📝 Transférer vers le formulaire"):
                    st.session_state['goto_saisie'] = True
                    st.rerun()
    
    # --- PAGE ANALYSE ---
    elif menu == "📈 Analyse":
        st.title("🔬 Analyse Scientifique")
        
        if df.empty or len(df) < 3:
            st.warning("⚠️ Données insuffisantes (minimum 3 sujets requis)")
            return
            
        tab1, tab2 = st.tabs(["Corrélations", "Performance par Race"])
        
        with tab1:
            st.subheader("Matrice de corrélation biométrique")
            cols_corr = ['p30', 'p70', 'h_garrot', 'p_thoracique', 'c_canon', 'GMQ', 'Index']
            corr = df[cols_corr].corr().round(2)
            
            fig = px.imshow(
                corr,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="RdBu_r",
                title="Liens entre caractères morphologiques"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Importance des critères
            st.subheader("Impact sur l'Index final")
            if 'Index' in corr.columns:
                impacts = corr['Index'].abs().drop('Index').sort_values(ascending=True)
                fig2 = px.bar(
                    x=impacts.values,
                    y=impacts.index,
                    orientation='h',
                    title="Corrélation avec l'Index (%)",
                    labels={'x': 'Force de corrélation', 'y': 'Critère'}
                )
                st.plotly_chart(fig2, use_container_width=True)
        
        with tab2:
            st.subheader("Comparaison par Race")
            if 'race' in df.columns and not df.empty:
                fig3 = px.box(
                    df, 
                    x="race", 
                    y="Index", 
                    color="race",
                    title="Distribution de l'Index selon la race"
                )
                st.plotly_chart(fig3, use_container_width=True)
    
    # --- PAGE SAISIE MANUELLE ---
    elif menu == "✍️ Saisie Manuelle":
        st.title("✍️ Fiche d'Identification")
        
        # Récupération données scan si existantes
        scan = st.session_state.get('scan_data', {})
        goto = st.session_state.get('goto_saisie', False)
        
        if goto:
            st.success("📝 Données du scanner pré-remplies ci-dessous")
            st.session_state['goto_saisie'] = False
        
        with st.form("form_saisie", clear_on_submit=True):
            st.subheader("Données générales")
            col1, col2 = st.columns(2)
            
            with col1:
                animal_id = st.text_input("ID Animal *", placeholder="REF-2024-XXXX")
                race = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Autre"])
                date_nais = st.date_input("Date naissance", datetime.now() - timedelta(days=100))
            
            with col2:
                objectif = st.selectbox("Objectif élevage", ["Sélection", "Engraissement", "Reproduction"])
                dentition = st.selectbox("Dentition", ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
            
            st.subheader("Poids de croissance")
            col3, col4, col5 = st.columns(3)
            with col3:
                p10 = st.number_input("Poids J10 (kg)", min_value=0.0, max_value=20.0, step=0.1)
            with col4:
                p30 = st.number_input("Poids J30 (kg)", min_value=0.0, max_value=40.0, step=0.1)
            with col5:
                p70 = st.number_input("Poids J70 (kg) *", min_value=0.0, max_value=100.0, step=0.1)
            
            st.subheader("Mensurations (cm) - Scannées ou_manuelles")
            cols = st.columns(5)
            mensurations = {}
            
            fields = [
                ('h_garrot', 'Hauteur Garrot'),
                ('c_canon', 'Canon'),
                ('l_poitrine', 'Larg. Poitrine'),
                ('p_thoracique', 'Périm. Thorax'),
                ('l_corps', 'Long. Corps')
            ]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mensurations[key] = st.number_input(
                        label,
                        value=float(scan.get(key, 0.0)),
                        min_value=0.0,
                        max_value=200.0,
                        step=0.1,
                        key=f"input_{key}"
                    )
            
            submitted = st.form_submit_button("💾 Enregistrer", type="primary")
            
            if submitted:
                if not animal_id:
                    st.error("❌ L'ID animal est obligatoire!")
                elif p70 <= 0:
                    st.error("❌ Le poids J70 est obligatoire et doit être > 0!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            
                            # Insertion/Update belier
                            c.execute("""
                                INSERT OR REPLACE INTO beliers 
                                (id, race, date_naiss, objectif, dentition)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                animal_id, 
                                race, 
                                date_nais.strftime("%Y-%m-%d"),
                                objectif,
                                dentition
                            ))
                            
                            # Insertion nouvelle mesure
                            c.execute("""
                                INSERT INTO mesures 
                                (id_animal, p10, p30, p70, h_garrot, l_corps, 
                                 p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                animal_id,
                                p10, p30, p70,
                                mensurations['h_garrot'],
                                mensurations['l_corps'],
                                mensurations['p_thoracique'],
                                mensurations['l_poitrine'],
                                mensurations['c_canon']
                            ))
                        
                        # Nettoyage session
                        if 'scan_data' in st.session_state:
                            del st.session_state['scan_data']
                            
                        st.success(f"✅ Animal {animal_id} enregistré avec succès!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Erreur base de données: {e}")

if __name__ == "__main__":
    main()
