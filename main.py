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

# ==========================================
# CONFIGURATION PROFESSIONNELLE
# ==========================================
SEUILS_PRO = {
    'p70_absolu': 22.0,
    'canon_absolu': 7.5,
    'percentile_elite': 0.85,
    'z_score_max': 2.5,
    'ratio_p70_canon_max': 8.0
}

# ==========================================
# INITIALISATION
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")
DB_NAME = "expert_ovin_pro.db"

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
        
        # Table principale avec nouvelles colonnes
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT, 
                race_precision TEXT,  -- NOUVEAU: précision si race=Croisé/Non identifiée
                date_naiss TEXT, 
                date_estimee INTEGER DEFAULT 0,  -- NOUVEAU: 0=exacte, 1=estimée via dentition
                objectif TEXT, 
                dentition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration si table existe déjà (ajout colonnes manquantes)
        try:
            c.execute("ALTER TABLE beliers ADD COLUMN race_precision TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE beliers ADD COLUMN date_estimee INTEGER DEFAULT 0")
        except:
            pass
        
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
        c.execute('CREATE INDEX IF NOT EXISTS idx_animal ON mesures(id_animal)')

# ==========================================
# UTILITAIRES
# ==========================================
def safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val):
            return default
        f = float(val)
        return f if not np.isnan(f) else default
    except:
        return default

def calculer_date_naissance(dentition, date_reference=None):
    """
    Convertit la dentition en date de naissance estimée
    Retourne: (date_naiss, age_jours_approx)
    """
    if date_reference is None:
        date_reference = datetime.now()
    
    ages_dentition = {
        "2 Dents": 90,      # ~3 mois
        "4 Dents": 180,     # ~6 mois  
        "6 Dents": 270,     # ~9 mois
        "Pleine bouche": 365 # ~12+ mois
    }
    
    if dentition in ages_dentition:
        age_jours = ages_dentition[dentition]
        date_naiss = date_reference - timedelta(days=age_jours)
        return date_naiss, age_jours
    return None, 0

def detecter_anomalies(df):
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    
    cols_check = ['p70', 'c_canon', 'h_garrot']
    for col in cols_check:
        if col in df.columns and df[col].std() > 0:
            z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
            mask = z_scores > SEUILS_PRO['z_score_max']
            df.loc[mask, 'Anomalie'] = True
            df.loc[mask, 'Alerte'] += f"{col} anormal; "
    
    mask_ratio = (df['p70'] / df['c_canon'] > SEUILS_PRO['ratio_p70_canon_max']) & (df['c_canon'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Alerte'] += "Ratio poids/canon incohérent;"
    
    mask_null = (df['p70'] == 0) | (df['c_canon'] == 0)
    df.loc[mask_null, 'Alerte'] += "Données manquantes;"
    
    return df

# ==========================================
# LOGIQUE MÉTIER
# ==========================================
def calculer_metrics_pro(row):
    try:
        p70 = safe_float(row.get('p70'), 0)
        p30 = safe_float(row.get('p30'), 0)
        hg = safe_float(row.get('h_garrot'), 0)
        l_poitrine = safe_float(row.get('l_poitrine'), 24)
        p_thoracique = safe_float(row.get('p_thoracique'), 80)
        
        if p70 <= 0 or p30 <= 0 or p30 >= p70:
            return 0.0, 0.0, 0.0, "Données insuffisantes"
        
        gmq = ((p70 - p30) / 40) * 1000
        rendement = 52.4 + (0.35 * l_poitrine) + (0.12 * p_thoracique) - (0.08 * hg)
        rendement = max(40.0, min(65.0, rendement))
        
        kleiber = p70 / (hg ** 0.75) if hg > 0 else 0
        
        score_rendement = (rendement - 40) / 25 * 100
        score_gmq = min(gmq / 4, 100)
        score_poids = min(p70 / 35 * 100, 100)
        score_kleiber = min(max((kleiber - 2) * 20, 0), 100)
        
        index_final = (score_rendement * 0.4 + score_gmq * 0.3 + score_poids * 0.2 + score_kleiber * 0.1)
        
        if index_final >= 85:
            commentaire = "Excellence génétique"
        elif index_final >= 70:
            commentaire = "Bon potentiel"
        elif index_final >= 50:
            commentaire = "Standard"
        else:
            commentaire = "À surveiller"
            
        return round(gmq, 1), round(rendement, 1), round(index_final, 1), commentaire
        
    except Exception as e:
        return 0.0, 0.0, 0.0, f"Erreur: {str(e)[:30]}"

def identifier_elite_pro(df):
    if df.empty or len(df) < 3:
        df['Statut'] = ""
        df['Rang'] = 0
        return df
    
    df['p70'] = pd.to_numeric(df['p70'], errors='coerce').fillna(0)
    df['c_canon'] = pd.to_numeric(df['c_canon'], errors='coerce').fillna(0)
    
    seuil_p70_rel = df['p70'].quantile(SEUILS_PRO['percentile_elite'])
    seuil_canon_rel = df['c_canon'].quantile(SEUILS_PRO['percentile_elite'])
    
    seuil_p70 = max(SEUILS_PRO['p70_absolu'], seuil_p70_rel)
    seuil_canon = max(SEUILS_PRO['canon_absolu'], seuil_canon_rel)
    
    df['Rang'] = df['Index'].rank(ascending=False, method='min').astype(int)
    
    critere_p70 = df['p70'] >= seuil_p70
    critere_canon = df['c_canon'] >= seuil_canon
    critere_sain = ~df['Anomalie']
    
    df['Statut'] = np.where(critere_p70 & critere_canon & critere_sain, "ELITE PRO", "")
    
    return df

# ==========================================
# GESTION DONNÉES
# ==========================================
@st.cache_data(ttl=5)
def load_data():
    try:
        with get_db_connection() as conn:
            # Récupération des nouvelles colonnes race_precision et date_estimee
            query = """
                SELECT b.id, b.race, b.race_precision, b.date_naiss, b.date_estimee,
                       b.objectif, b.dentition, m.p10, m.p30, m.p70, m.h_garrot, 
                       m.l_corps, m.p_thoracique, m.l_poitrine, m.c_canon
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
            
            # Conversion numérique
            for col in ['p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'p_thoracique', 'l_poitrine', 'l_corps']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Formater l'affichage de la date (avec ~ si estimée)
            def format_date(row):
                if pd.notna(row.get('date_naiss')) and row.get('date_naiss'):
                    date_str = str(row['date_naiss'])[:10]
                    if row.get('date_estimee') == 1:
                        return f"~{date_str}"
                    return date_str
                return "Non définie"
            
            df['date_affichage'] = df.apply(format_date, axis=1)
            
            # Formater la race avec précision si existe
            def format_race(row):
                race = row.get('race', '')
                prec = row.get('race_precision')
                if pd.notna(prec) and prec and race in ['Non identifiée', 'Croisé']:
                    return f"{race} ({prec})"
                return race
            
            df['race_affichage'] = df.apply(format_race, axis=1)
            
            df = detecter_anomalies(df)
            results = df.apply(lambda x: pd.Series(calculer_metrics_pro(x)), axis=1)
            df[['GMQ', 'Rendement', 'Index', 'Appreciation']] = results
            df = identifier_elite_pro(df)
            
            return df
    except Exception as e:
        st.error(f"Erreur chargement données: {e}")
        return pd.DataFrame()

def generer_demo(n=30):
    races = ["Ouled Djellal", "Rembi", "Hamra", "Non identifiée"]
    count = 0
    
    with get_db_connection() as conn:
        c = conn.cursor()
        for i in range(n):
            try:
                is_anomalie = random.random() < 0.05
                p10 = round(random.uniform(4.0, 6.5), 1)
                p30 = round(p10 + random.uniform(9, 13), 1)
                
                if is_anomalie:
                    p70 = round(random.uniform(15, 50), 1)
                    cc = round(random.uniform(5, 15), 1)
                else:
                    p70 = round(p30 + random.uniform(18, 26), 1)
                    cc = round(7.5 + (p70/35)*3 + random.uniform(-0.5, 0.5), 1)
                
                hg = round(65 + (p70/35)*8 + random.uniform(-2, 2), 1)
                animal_id = f"REF-2024-{1000+i}"
                race = random.choice(races)
                race_prec = "Type lourd" if race == "Non identifiée" else None
                
                # Date aléatoire ou estimée
                date_estimee = random.choice([0, 1])
                if date_estimee:
                    date_nais = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
                else:
                    date_nais = (datetime.now() - timedelta(days=random.randint(80,300))).strftime("%Y-%m-%d")
                
                c.execute("""
                    INSERT OR IGNORE INTO beliers (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                    VALUES (?,?,?,?,?,?,?)
                """, (animal_id, race, race_prec, date_nais, date_estimee, "Sélection", "2 Dents"))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (animal_id, p10, p30, p70, hg, 80, hg*1.2, 24, cc))
                count += 1
            except Exception as e:
                continue
    return count

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    
    # Sidebar
    st.sidebar.title("💎 Expert Selector Pro")
    st.sidebar.markdown("---")
    
    df_temp = load_data()
    if not df_temp.empty:
        st.sidebar.metric("Sujets en base", len(df_temp))
    
    if st.sidebar.button("🚀 Générer 30 sujets test", use_container_width=True):
        with st.spinner("Création..."):
            n = generer_demo(30)
            st.sidebar.success(f"✅ {n} créés!")
            time.sleep(0.5)
            st.rerun()
    
    if st.sidebar.button("🗑️ Vider la base", use_container_width=True):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mesures")
            conn.execute("DELETE FROM beliers")
        st.sidebar.success("Base vidée!")
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Seuil Elite: >{SEUILS_PRO['p70_absolu']}kg & >{SEUILS_PRO['canon_absolu']}cm")
    
    menu = st.sidebar.radio("Menu", [
        "🏠 Dashboard", 
        "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse",
        "📸 Scanner", 
        "✍️ Saisie"
    ])
    
    df = load_data()
    
    # ==========================================
    # 1. DASHBOARD
    # ==========================================
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord Professionnel")
        
        if df.empty:
            st.info("👋 Générez des données test pour commencer")
            return
        
        nb_anomalies = df['Anomalie'].sum()
        if nb_anomalies > 0:
            st.warning(f"⚠️ {nb_anomalies} anomalie(s) détectée(s). Allez dans 'Contrôle Qualité'.")
        
        col1, col2, col3, col4 = st.columns(4)
        elite_mask = df['Statut'] == 'ELITE PRO'
        
        with col1:
            st.metric("Total Sujets", len(df))
        with col2:
            st.metric("Elite Pro", len(df[elite_mask]), f"{len(df[elite_mask])/len(df)*100:.1f}%")
        with col3:  # CORRECTION: col3 (pas c3)
            st.metric("Index Moyen", f"{df['Index'].mean():.1f}/100")
        with col4:
            st.metric("Anomalies", int(nb_anomalies), "Vérifier" if nb_anomalies > 0 else "OK", 
                     delta_color="inverse" if nb_anomalies > 0 else "normal")
        
        st.subheader("Classement officiel")
        
        # Colonnes d'affichage avec race et date formatées
        cols_display = ['Rang', 'Statut', 'id', 'race_affichage', 'date_affichage', 'p70', 'c_canon', 'Index', 'Appreciation', 'Alerte']
        df_display = df[cols_display].sort_values('Rang').copy()
        df_display.columns = ['Rang', 'Statut', 'ID', 'Race', 'Date Naiss.', 'P70(kg)', 'Canon(cm)', 'Index', 'Appreciation', 'Alerte']
        
        def color_status(val):
            if val == 'ELITE PRO':
                return 'background-color: #FFD700; color: black; font-weight: bold'
            return ''
        
        def color_alert(val):
            if val != "":
                return 'background-color: #ffcccc'
            return ''
        
        styled_df = df_display.style.applymap(color_status, subset=['Statut']).applymap(color_alert, subset=['Alerte'])
        st.dataframe(styled_df, use_container_width=True, height=500)
        
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(df, x='p70', y='Index', color='Statut', 
                           title='Sélection: Poids vs Index', hover_data=['id', 'Alerte'])
            fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Seuil Elite")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig2 = px.histogram(df, x='Index', color='Anomalie', 
                              title="Distribution avec anomalies", color_discrete_map={True: 'red', False: 'blue'})
            st.plotly_chart(fig2, use_container_width=True)
    
    # ==========================================
    # 2. CONTRÔLE QUALITÉ
    # ==========================================
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Données")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        df_anomalies = df[df['Anomalie'] == True]
        
        if not df_anomalies.empty:
            st.error(f"⚠️ {len(df_anomalies)} mesures suspectes")
            st.dataframe(df_anomalies[['id', 'race_affichage', 'p70', 'c_canon', 'h_garrot', 'Alerte', 'Index']], use_container_width=True)
            st.info("💡 Ces animaux sont exclus de l'Elite jusqu'à correction")
        else:
            st.success("✅ Aucune anomalie détectée")
        
        st.subheader("Statistiques globales")
        st.dataframe(df[['p70', 'c_canon', 'h_garrot', 'GMQ', 'Index']].describe(), use_container_width=True)
    
    # ==========================================
    # 3. STATS & ANALYSE
    # ==========================================
    elif menu == "📈 Stats & Analyse":
        st.title("📈 Analyse Scientifique")
        
        if df.empty or len(df) < 3:
            st.warning("⚠️ Minimum 3 animaux requis")
            return
        
        tab1, tab2, tab3 = st.tabs(["📊 Corrélations", "🎯 Race vs Race", "📉 Seuils Elite"])
        
        with tab1:
            st.subheader("Matrice de corrélation")
            vars_stats = ['p70', 'h_garrot', 'c_canon', 'GMQ', 'Index']
            valid_vars = [v for v in vars_stats if v in df.columns and df[v].std() > 0]
            
            if len(valid_vars) >= 2:
                corr = df[valid_vars].corr()
                fig = px.imshow(corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r")
                st.plotly_chart(fig, use_container_width=True)
                st.info("🔴 Rouge = corrélation positive forte | 🔵 Bleu = négative")
            else:
                st.error("Pas assez de variabilité")
        
        with tab2:
            st.subheader("Performance par Race")
            if 'race_affichage' in df.columns and df['race'].nunique() > 1:
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.box(df, x="race", y="Index", color="race", points="all")
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    races = df['race'].unique()[:3]
                    if len(races) >= 2:
                        stats_race = df.groupby('race')[['p70', 'GMQ', 'c_canon', 'Rendement']].mean()
                        fig_radar = go.Figure()
                        for race in races:
                            fig_radar.add_trace(go.Scatterpolar(
                                r=[
                                    stats_race.loc[race, 'p70']/35*100,
                                    stats_race.loc[race, 'GMQ']/400*100,
                                    stats_race.loc[race, 'c_canon']/12*100,
                                    stats_race.loc[race, 'Rendement']/65*100
                                ],
                                theta=['Poids', 'GMQ', 'Canon', 'Rendement'],
                                fill='toself',
                                name=race
                            ))
                        fig_radar.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), showlegend=True)
                        st.plotly_chart(fig_radar, use_container_width=True)
            else:
                st.info("Données insuffisantes pour comparer les races")
        
        with tab3:
            st.subheader("Carte de sélection Elite")
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.scatter(df, x='p70', y='c_canon', color='Statut',
                               color_discrete_map={'ELITE PRO': '#FFD700', '': '#1f77b4'},
                               title="Scatter plot P70 vs Canon", hover_data=['id'])
                fig.add_hline(y=SEUILS_PRO['canon_absolu'], line_dash="dash", line_color="red")
                fig.add_vline(x=SEUILS_PRO['p70_absolu'], line_dash="dash", line_color="red")
                fig.update_layout(xaxis_title="Poids J70 (kg)", yaxis_title="Canon (cm)")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                comparaison = pd.DataFrame({
                    'Elite': df[df['Statut'] == 'ELITE PRO'][['p70', 'c_canon', 'Index']].mean(),
                    'Standard': df[df['Statut'] != 'ELITE PRO'][['p70', 'c_canon', 'Index']].mean()
                }).round(1)
                st.dataframe(comparaison)
                
                df_elite = df[df['Statut'] == 'ELITE PRO']
                if not df_elite.empty:
                    st.metric("Index Elite moyen", f"{df_elite['Index'].mean():.1f}", 
                             delta=f"+{df_elite['Index'].mean() - df[df['Statut'] != 'ELITE PRO']['Index'].mean():.1f}")
    
    # ==========================================
    # 4. SCANNER INTELLIGENT
    # ==========================================
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Intelligent (Option 1)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            img = st.camera_input("📷 Photo de profil")
        
        with col2:
            race_scan = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Non identifiée"], key="race_scanner")
            
            if race_scan == "Non identifiée":
                st.warning("⚠️ Profil moyen standard appliqué (précision réduite)")
            
            st.info(f"**Profil type {race_scan}** chargé")
            
            correction = st.slider("Ajustement (%)", -10, 10, 0)
        
        if img:
            with st.spinner("Analyse..."):
                progress = st.progress(0)
                for i in range(0, 101, 20):
                    time.sleep(0.1)
                    progress.progress(i)
                
                DATA_RACES = {
                    "Ouled Djellal": {"h_garrot": 72.0, "c_canon": 8.0, "l_poitrine": 24.0, "p_thoracique": 83.0, "l_corps": 82.0},
                    "Rembi": {"h_garrot": 76.0, "c_canon": 8.8, "l_poitrine": 26.0, "p_thoracique": 88.0, "l_corps": 86.0},
                    "Hamra": {"h_garrot": 70.0, "c_canon": 7.8, "l_poitrine": 23.0, "p_thoracique": 80.0, "l_corps": 78.0},
                    "Babarine": {"h_garrot": 74.0, "c_canon": 8.2, "l_poitrine": 25.0, "p_thoracique": 85.0, "l_corps": 84.0},
                    "Non identifiée": {"h_garrot": 73.0, "c_canon": 8.1, "l_poitrine": 24.5, "p_thoracique": 84.0, "l_corps": 82.5}  # Profil moyen
                }
                
                base = DATA_RACES[race_scan].copy()
                if correction != 0:
                    facteur = 1 + (correction / 100)
                    for key in base:
                        base[key] = round(base[key] * facteur, 1)
                
                st.session_state['scan'] = base
                st.session_state['scan_mode'] = f"Profil {race_scan}"
                
                st.success(f"✅ Profil {race_scan} chargé")
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Hauteur Garrot", f"{base['h_garrot']} cm")
                    st.metric("Longueur Corps", f"{base['l_corps']} cm")
                with c2:
                    st.metric("Circonf. Canon", f"{base['c_canon']} cm")
                    st.metric("Larg. Poitrine", f"{base['l_poitrine']} cm")
                with c3:
                    st.metric("Périm. Thorax", f"{base['p_thoracique']} cm")
                
                if st.button("📝 Transférer vers Saisie", type="primary"):
                    st.session_state['go_saisie'] = True
                    st.rerun()
    
    # ==========================================
    # 5. SAISIE MANUELLE (AMÉLIORÉE)
    # ==========================================
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche d'Identification")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("✅ Données du scanner importées! Vérifiez et complétez.")
            st.session_state['go_saisie'] = False
        
        with st.form("form_saisie_pro"):
            # SECTION 1: IDENTIFICATION
            st.subheader("🆔 Identification de l'animal")
            col_id1, col_id2 = st.columns(2)
            
            with col_id1:
                id_animal = st.text_input("ID Animal *", placeholder="ex: REF-2024-001", key="id_anim")
                
                # RACE avec gestion incertitude
                race_options = ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Croisé", "Non identifiée"]
                race = st.selectbox("Race *", race_options, help="Sélectionnez 'Non identifiée' si doute persiste")
                
                # Champ précision conditionnel
                race_precision = ""
                if race in ["Non identifiée", "Croisé"]:
                    race_precision = st.text_input(
                        "Descriptif / Croisement supposé", 
                        placeholder="ex: Type Rembi, possible croisement",
                        help="Informations pour aider à l'identification future"
                    )
            
            with col_id2:
                st.markdown("**📅Âge de l'animal**")
                
                # Choix méthode: Date exacte vs Dentition
                methode_age = st.radio(
                    "Méthode de détermination de l'âge", 
                    ["Date de naissance connue (registre)", "Estimation par dentition"],
                    index=0,
                    help="La dentition permet d'estimer l'âge si la date est inconnue"
                )
                
                date_naiss = None
                dentition = "2 Dents"
                date_estimee_flag = 0
                
                if methode_age == "Date de naissance connue (registre)":
                    date_naiss = st.date_input(
                        "Date naissance exacte", 
                        datetime.now() - timedelta(days=100),
                        help="Date issue du registre d'élevage"
                    )
                    dentition = st.selectbox(
                        "Dentition observée (confirmation)", 
                        ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"]
                    )
                    date_estimee_flag = 0
                    
                else:
                    # MODE ESTIMATION PAR DENTITION
                    st.info("📏 L'âge sera calculé automatiquement")
                    
                    dentition = st.selectbox(
                        "Dentition actuelle *", 
                        ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"],
                        help="2 Dents = ~3 mois | 4 Dents = ~6 mois | 6 Dents = ~9 mois | Pleine = 12+ mois"
                    )
                    
                    # Calcul automatique
                    date_calculee, age_jours = calculer_date_naissance(dentition)
                    if date_calculee:
                        date_naiss = date_calculee
                        date_estimee_flag = 1
                        
                        st.success(f"📅 **Date estimée: {date_naiss.strftime('%d/%m/%Y')}**")
                        st.caption(f"Âge approximatif: {age_jours} jours (~{age_jours//30} mois)")
                        
                        # Avertissement si cohérence douteuse avec poids
                        st.info("💡 Vérifiez que le poids saisi ci-dessous correspond à cet âge")
                
                objectif = st.selectbox("Objectif élevage", ["Sélection", "Engraissement", "Reproduction"])
            
            # SECTION 2: POIDS
            st.subheader("⚖️ Poids de croissance")
            col_p1, col_p2, col_p3 = st.columns(3)
            
            with col_p1:
                p10 = st.number_input("Poids J10 (kg)", 0.0, 20.0, 0.0, 0.1,
                                    help="Si inconnu, laisser 0")
            with col_p2:
                p30 = st.number_input("Poids J30 (kg)", 0.0, 40.0, 0.0, 0.1,
                                    help="Si inconnu, laisser 0")
            with col_p3:
                if date_estimee_flag == 1:
                    # Si date estimée, le p70 est en fait le poids ACTUEL à la dentition observée
                    p70 = st.number_input("Poids ACTUEL (kg) *", 0.0, 100.0, 0.0, 0.1,
                                        help=f"Poids à {dentition} (obligatoire pour le calcul)")
                else:
                    p70 = st.number_input("Poids J70 (kg) *", 0.0, 100.0, 0.0, 0.1,
                                        help="Poids à 70 jours (ou poids actuel si plus âgé)")
            
            # SECTION 3: MENSURATIONS
            st.subheader("📏 Mensurations morphologiques (cm)")
            cols = st.columns(5)
            mens = {}
            fields = [
                ('h_garrot', 'Hauteur Garrot'),
                ('c_canon', 'Circonf. Canon'),
                ('l_poitrine', 'Larg. Poitrine'),
                ('p_thoracique', 'Périm. Thorax'),
                ('l_corps', 'Long. Corps')
            ]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(
                        label,
                        min_value=0.0,
                        max_value=200.0,
                        value=float(scan.get(key, 0.0)),
                        step=0.5,
                        key=f"input_{key}"
                    )
            
            # BOUTON SAUVEGARDE
            submitted = st.form_submit_button("💾 Enregistrer la fiche", type="primary", use_container_width=True)
            
            if submitted:
                # VALIDATIONS
                erreurs = []
                if not id_animal:
                    erreurs.append("L'ID animal est obligatoire")
                if p70 <= 0:
                    erreurs.append("Le poids est obligatoire")
                if date_naiss is None:
                    erreurs.append("Date de naissance ou dentition obligatoire")
                
                if erreurs:
                    for err in erreurs:
                        st.error(f"❌ {err}")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            
                            # Insertion avec nouvelles colonnes
                            c.execute("""
                                INSERT OR REPLACE INTO beliers 
                                (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                id_animal,
                                race,
                                race_precision if race_precision else None,
                                date_naiss.strftime("%Y-%m-%d"),
                                date_estimee_flag,
                                objectif,
                                dentition
                            ))
                            
                            c.execute("""
                                INSERT INTO mesures 
                                (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                id_animal, p10, p30, p70,
                                mens['h_garrot'],
                                mens['l_corps'],
                                mens['p_thoracique'],
                                mens['l_poitrine'],
                                mens['c_canon']
                            ))
                        
                        # Message de confirmation
                        type_date = "📅 Date estimée" if date_estimee_flag else "📅 Date exacte"
                        type_race = race
                        if race_precision:
                            type_race += f" ({race_precision})"
                        
                        st.success(f"✅ {id_animal} enregistré avec succès!")
                        st.info(f"**{type_date}** | **Race:** {type_race} | **Dentition:** {dentition}")
                        
                        # Nettoyage session
                        if 'scan' in st.session_state:
                            del st.session_state['scan']
                        
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Erreur base de données: {e}")

if __name__ == "__main__":
    main()
