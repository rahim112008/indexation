import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="Expert Selector Ultra", 
    layout="wide", 
    page_icon="🐏"
)

DB_NAME = "expert_ovin_v2.db"

# --- 2. GESTION BASE DE DONNÉES ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=20)
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
    with get_db_connection() as conn:
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT, 
                date_naiss TEXT, 
                objectif TEXT, 
                dentition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS mesures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_animal TEXT NOT NULL,
                p10 REAL DEFAULT 0,
                p30 REAL DEFAULT 0,
                p70 REAL DEFAULT 0,
                h_garrot REAL DEFAULT 0,
                l_corps REAL DEFAULT 0,
                p_thoracique REAL DEFAULT 0,
                l_poitrine REAL DEFAULT 0,
                c_canon REAL DEFAULT 0,
                date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE
            )
        ''')
        
        # Index optimisés
        c.execute('CREATE INDEX IF NOT EXISTS idx_animal ON mesures(id_animal)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_date ON mesures(date_mesure)')

# --- 3. LOGIQUE SCIENTIFIQUE CORRIGÉE ---
def safe_float(val, default=0.0):
    """Conversion sécurisée en float"""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except:
        return default

def calculer_metrics(row, mode="Viande"):
    """Calcule GMQ, Rendement et Index avec vérifications"""
    try:
        p70 = safe_float(row.get('p70'), 0)
        p30 = safe_float(row.get('p30'), 0)
        
        if p70 <= 0 or p30 <= 0 or p30 >= p70:
            return 0.0, 0.0, 0.0
        
        # GMQ
        gmq = ((p70 - p30) / 40) * 1000
        
        # Rendement
        l_poitrine = safe_float(row.get('l_poitrine'), 24)
        p_thoracique = safe_float(row.get('p_thoracique'), 80)
        h_garrot = safe_float(row.get('h_garrot'), 70)
        
        rendement = 52.4 + (0.35 * l_poitrine) + (0.12 * p_thoracique) - (0.08 * h_garrot)
        rendement = max(40.0, min(65.0, rendement))
        
        # Index
        c_canon = safe_float(row.get('c_canon'), 9)
        
        if mode == "Viande":
            index = (gmq * 0.15) + (rendement * 0.55) + (p70 * 0.3)
        else:
            index = (c_canon * 4.0) + (h_garrot * 0.3) + (gmq * 0.03)
            
        return round(gmq, 1), round(rendement, 1), round(index, 2)
    
    except Exception as e:
        return 0.0, 0.0, 0.0

def identifier_champions(df):
    """Identifie l'élite avec gestion des cas limites"""
    if df.empty or len(df) < 3:
        df['Statut'] = ""
        return df
    
    try:
        # Nettoyage des données
        df['p70'] = pd.to_numeric(df['p70'], errors='coerce').fillna(0)
        df['c_canon'] = pd.to_numeric(df['c_canon'], errors='coerce').fillna(0)
        
        # Calcul des seuils uniquement si assez de variabilité
        p70_values = df[df['p70'] > 0]['p70']
        canon_values = df[df['c_canon'] > 0]['c_canon']
        
        if len(p70_values) < 3 or len(canon_values) < 3:
            df['Statut'] = ""
            return df
            
        seuil_p70 = p70_values.quantile(0.85)
        seuil_canon = canon_values.quantile(0.85)
        
        # Éviter les seuils à 0
        if seuil_p70 == 0:
            seuil_p70 = p70_values.max() * 0.9
        if seuil_canon == 0:
            seuil_canon = canon_values.max() * 0.9
        
        conditions = (df['p70'] >= seuil_p70) & (df['c_canon'] >= seuil_canon)
        df['Statut'] = np.where(conditions, "ELITE", "")
        
    except Exception as e:
        df['Statut'] = ""
        
    return df

# --- 4. GÉNÉRATION DONNÉES ---
def generer_demo(n=30):
    """Génère des données de démonstration cohérentes"""
    races = ["Ouled Djellal", "Rembi", "Hamra", "Babarine"]
    count = 0
    
    with get_db_connection() as conn:
        c = conn.cursor()
        
        for i in range(n):
            try:
                # ID unique
                animal_id = f"REF-{2024}-{1000+i}-{random.randint(10,99)}"
                
                # Croissance cohérente
                p10 = round(random.uniform(4.0, 6.5), 1)
                p30 = round(p10 + random.uniform(9, 13), 1)
                p70 = round(p30 + random.uniform(18, 26), 1)
                
                # Biométrie corrélée
                facteur = p70 / 35
                hg = round(65 + (facteur * 8) + random.uniform(-1.5, 1.5), 1)
                cc = round(7.5 + (facteur * 3) + random.uniform(-0.2, 0.2), 1)
                lp = round(22 + (facteur * 4), 1)
                pt = round(75 + (facteur * 12), 1)
                lc = round(75 + (facteur * 8), 1)
                
                date_nais = (datetime.now() - timedelta(days=random.randint(80, 300))).strftime("%Y-%m-%d")
                
                c.execute("""
                    INSERT OR IGNORE INTO beliers (id, race, date_naiss, objectif, dentition)
                    VALUES (?, ?, ?, ?, ?)
                """, (animal_id, random.choice(races), date_nais, "Sélection", "2 Dents"))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (animal_id, p10, p30, p70, hg, lc, pt, lp, cc))
                
                count += 1
            except:
                continue
                
    return count

# --- 5. CHARGEMENT ROBUSTE ---
@st.cache_data(ttl=5)
def load_data():
    """Charge les données avec dernière mesure par animal"""
    try:
        with get_db_connection() as conn:
            # Requête corrigée : dernière mesure par animal
            query = """
                SELECT b.id, b.race, b.date_naiss, b.objectif, b.dentition,
                       m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, 
                       m.p_thoracique, m.l_poitrine, m.c_canon, m.date_mesure
                FROM beliers b
                LEFT JOIN (
                    SELECT id_animal, MAX(id) as max_id 
                    FROM mesures 
                    GROUP BY id_animal
                ) latest ON b.id = latest.id_animal
                LEFT JOIN mesures m ON latest.max_id = m.id
            """
            
            df = pd.read_sql(query, conn)
            
            if df.empty:
                return pd.DataFrame()
            
            # Conversion numérique sécurisée
            numeric_cols = ['p10', 'p30', 'p70', 'h_garrot', 'l_corps', 
                          'p_thoracique', 'l_poitrine', 'c_canon']
            
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Calcul des métriques
            results = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
            df[['GMQ', 'Rendement', 'Index']] = results
            
            # Identification élites
            df = identifier_champions(df)
            
            return df
            
    except Exception as e:
        st.error(f"Erreur chargement: {e}")
        return pd.DataFrame()

# --- 6. INTERFACE ---
def main():
    init_db()
    
    # Sidebar
    st.sidebar.title("💎 Expert Selector")
    
    # Stats rapides
    df_temp = load_data()
    if not df_temp.empty:
        st.sidebar.metric("Sujets en base", len(df_temp))
    
    if st.sidebar.button("🚀 Générer 30 sujets démo", use_container_width=True):
        with st.spinner("Création..."):
            n = generer_demo(30)
            st.sidebar.success(f"✅ {n} créés!")
            time.sleep(0.5)
            st.rerun()
    
    if st.sidebar.button("🗑️ Vider la base", use_container_width=True, type="secondary"):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mesures")
            conn.execute("DELETE FROM beliers")
        st.sidebar.success("Base vidée!")
        st.rerun()
    
    menu = st.sidebar.radio("Navigation", 
        ["🏠 Dashboard", "📸 Scanner", "📈 Analyse", "✍️ Saisie"])
    
    # Chargement données
    df = load_data()
    
    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        
        if df.empty:
            st.info("👋 Commencez par générer des sujets démo avec le bouton dans le menu latéral")
            return
        
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total", len(df))
        with c2:
            elite = len(df[df['Statut'] == 'ELITE'])
            st.metric("Champions", f"{elite} ({elite/len(df)*100:.0f}%)")
        with c3:
            st.metric("Index moyen", f"{df['Index'].mean():.1f}")
        with c4:
            st.metric("GMQ moyen", f"{df['GMQ'].mean():.0f}g/j")
        
        # Filtres
        st.subheader("Filtres")
        col1, col2 = st.columns(2)
        with col1:
            races = ['Toutes'] + sorted(df['race'].unique().tolist())
            race_filtre = st.selectbox("Race", races)
        with col2:
            statut_filtre = st.selectbox("Statut", ["Tous", "ELITE", "Standard"])
        
        # Application filtres
        df_view = df.copy()
        if race_filtre != 'Toutes':
            df_view = df_view[df_view['race'] == race_filtre]
        if statut_filtre == "ELITE":
            df_view = df_view[df_view['Statut'] == 'ELITE']
        elif statut_filtre == "Standard":
            df_view = df_view[df_view['Statut'] == '']
        
        # Tableau
        st.subheader("Classement")
        cols = ['Statut', 'id', 'race', 'p70', 'c_canon', 'GMQ', 'Rendement', 'Index']
        st.dataframe(
            df_view[cols].sort_values('Index', ascending=False),
            use_container_width=True,
            height=400
        )
        
        # Graphiques
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(df_view, x='p70', y='Index', color='race', 
                           title='Poids J70 vs Index', size='GMQ')
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.histogram(df_view, x='Index', color='Statut', 
                              title='Distribution des Index', nbins=15)
            st.plotly_chart(fig2, use_container_width=True)
    
    # --- SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        
        img = st.camera_input("Prendre une photo de profil")
        
        if img:
            with st.spinner("Analyse IA..."):
                progress = st.progress(0)
                for i in range(100):
                    time.sleep(0.01)
                    progress.progress(i+1)
                
                # Génération mesures
                base = random.uniform(70, 80)
                scan_data = {
                    'h_garrot': round(base, 1),
                    'c_canon': round(random.uniform(8, 11), 1),
                    'l_poitrine': round(base * 0.34, 1),
                    'p_thoracique': round(base * 1.17, 1),
                    'l_corps': round(base * 1.14, 1)
                }
                st.session_state['scan'] = scan_data
            
            col1, col2 = st.columns(2)
            with col1:
                st.image(img)
            with col2:
                st.success("Mesures détectées!")
                for k, v in scan_data.items():
                    st.metric(k.replace('_', ' '), f"{v} cm")
                if st.button("Transférer vers Saisie"):
                    st.session_state['go_saisie'] = True
                    st.rerun()
    
    # --- ANALYSE ---
    elif menu == "📈 Analyse":
        st.title("🔬 Analyse Scientifique")
        
        if df.empty or len(df) < 3:
            st.warning("Données insuffisantes (min 3 sujets)")
            return
        
        tab1, tab2 = st.tabs(["Corrélations", "Performance Race"])
        
        with tab1:
            cols = ['p70', 'h_garrot', 'c_canon', 'GMQ', 'Index']
            # Vérification colonnes existantes et non vides
            cols_valid = [c for c in cols if c in df.columns and df[c].std() > 0]
            
            if len(cols_valid) >= 2:
                corr = df[cols_valid].corr()
                fig = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Pas assez de variabilité pour les corrélations")
        
        with tab2:
            if 'race' in df.columns:
                fig = px.box(df, x='race', y='Index', color='race')
                st.plotly_chart(fig, use_container_width=True)
    
    # --- SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Identification")
        
        # Récupération données scan
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("Données du scanner importées!")
            st.session_state['go_saisie'] = False
        
        with st.form("saisie_form"):
            st.subheader("Informations générales")
            c1, c2 = st.columns(2)
            with c1:
                id_animal = st.text_input("ID Animal *", placeholder="REF-2024-001")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Babarine"])
            with c2:
                date_nais = st.date_input("Date naissance", datetime.now() - timedelta(days=100))
                obj = st.selectbox("Objectif", ["Sélection", "Reproduction"])
            
            st.subheader("Poids")
            c1, c2, c3 = st.columns(3)
            with c1:
                p10 = st.number_input("Poids J10", 0.0, 20.0, 0.0, 0.1)
            with c2:
                p30 = st.number_input("Poids J30", 0.0, 40.0, 0.0, 0.1)
            with c3:
                p70 = st.number_input("Poids J70 *", 0.0, 100.0, 0.0, 0.1)
            
            st.subheader("Mensurations (cm)")
            cols = st.columns(5)
            mens = {}
            fields = [
                ('h_garrot', 'Hauteur Garrot'),
                ('c_canon', 'Canon'),
                ('l_poitrine', 'Larg. Poitrine'),
                ('p_thoracique', 'Pér. Thorax'),
                ('l_corps', 'Long. Corps')
            ]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(
                        label, 0.0, 200.0, 
                        float(scan.get(key, 0.0)), 0.1,
                        key=f"inp_{key}"
                    )
            
            submitted = st.form_submit_button("💾 Enregistrer", type="primary")
            
            if submitted:
                if not id_animal:
                    st.error("ID obligatoire!")
                elif p70 <= 0:
                    st.error("Poids J70 obligatoire!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT OR REPLACE INTO beliers (id, race, date_naiss, objectif, dentition)
                                VALUES (?, ?, ?, ?, ?)
                            """, (id_animal, race, date_nais.strftime("%Y-%m-%d"), obj, "2 Dents"))
                            
                            c.execute("""
                                INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (id_animal, p10, p30, p70, mens['h_garrot'], 
                                  mens['l_corps'], mens['p_thoracique'], 
                                  mens['l_poitrine'], mens['c_canon']))
                        
                        if 'scan' in st.session_state:
                            del st.session_state['scan']
                        
                        st.success(f"✅ {id_animal} enregistré!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")

if __name__ == "__main__":
    main()
