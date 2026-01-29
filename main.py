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
    'p70_absolu': 22.0,        # Poids minimum Elite (kg)
    'canon_absolu': 7.5,       # Canon minimum Elite (cm)  
    'percentile_elite': 0.85,  # Top 15%
    'z_score_max': 2.5,        # Détection anomalies
    'ratio_p70_canon_max': 8.0 # Alertes ratio
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
            query = """
                SELECT b.id, b.race, b.date_naiss, b.objectif, b.dentition,
                       m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, 
                       m.p_thoracique, m.l_poitrine, m.c_canon
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
            
            for col in ['p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'p_thoracique', 'l_poitrine', 'l_corps']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            df = detecter_anomalies(df)
            results = df.apply(lambda x: pd.Series(calculer_metrics_pro(x)), axis=1)
            df[['GMQ', 'Rendement', 'Index', 'Appreciation']] = results
            df = identifier_elite_pro(df)
            
            return df
    except Exception as e:
        st.error(f"Erreur chargement: {e}")
        return pd.DataFrame()

def generer_demo(n=30):
    races = ["Ouled Djellal", "Rembi", "Hamra"]
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
                
                c.execute("INSERT OR IGNORE INTO beliers VALUES (?,?,?,?,?,?)",
                    (animal_id, random.choice(races), 
                     (datetime.now() - timedelta(days=random.randint(80,300))).strftime("%Y-%m-%d"),
                     "Sélection", "2 Dents", datetime.now()))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (animal_id, p10, p30, p70, hg, 80, hg*1.2, 24, cc))
                count += 1
            except:
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
    
    # MENU COMPLET (5 onglets)
    menu = st.sidebar.radio("Menu", [
        "🏠 Dashboard", 
        "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse",  # <-- L'ONGLET MANQUANT EST ICI
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
        with col3:
            st.metric("Index Moyen", f"{df['Index'].mean():.1f}/100")
        with col4:
            st.metric("Anomalies", int(nb_anomalies), "Vérifier" if nb_anomalies > 0 else "OK", 
                     delta_color="inverse" if nb_anomalies > 0 else "normal")
        
        st.subheader("Classement officiel")
        df_display = df[['Rang', 'Statut', 'id', 'race', 'p70', 'c_canon', 'Index', 'Appreciation', 'Alerte']].sort_values('Rang')
        
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
            st.dataframe(df_anomalies[['id', 'p70', 'c_canon', 'h_garrot', 'Alerte', 'Index']], use_container_width=True)
            st.info("💡 Ces animaux sont exclus de l'Elite jusqu'à correction")
        else:
            st.success("✅ Aucune anomalie détectée")
        
        st.subheader("Statistiques globales")
        st.dataframe(df[['p70', 'c_canon', 'h_garrot', 'GMQ', 'Index']].describe(), use_container_width=True)
    
    # ==========================================
    # 3. STATS & ANALYSE (LE MANQUANT !)
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
            if 'race' in df.columns and df['race'].nunique() > 1:
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.box(df, x="race", y="Index", color="race", points="all")
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Radar chart comparatif
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
            race_scan = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine"], key="race_scanner")
            
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
                    "Babarine": {"h_garrot": 74.0, "c_canon": 8.2, "l_poitrine": 25.0, "p_thoracique": 85.0, "l_corps": 84.0}
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
    # 5. SAISIE MANUELLE
    # ==========================================
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("Données scanner importées!")
            st.session_state['go_saisie'] = False
        
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            with c1:
                id_animal = st.text_input("ID Animal *", placeholder="REF-2024-001")
                race = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine"])
            with c2:
                date_nais = st.date_input("Date naissance", datetime.now() - timedelta(days=100))
                obj = st.selectbox("Objectif", ["Sélection", "Reproduction"])
            
            st.subheader("Poids")
            c1, c2, c3 = st.columns(3)
            with c1:
                p10 = st.number_input("Poids J10", 0.0, 20.0, 0.0)
            with c2:
                p30 = st.number_input("Poids J30", 0.0, 40.0, 0.0)
            with c3:
                p70 = st.number_input("Poids J70 *", 0.0, 100.0, 0.0)
            
            st.subheader("Mensurations (cm)")
            cols = st.columns(5)
            mens = {}
            fields = [('h_garrot', 'Hauteur'), ('c_canon', 'Canon'), 
                     ('l_poitrine', 'Larg.Poitrine'), ('p_thoracique', 'Pér.Thorax'), ('l_corps', 'Long.Corps')]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(label, 0.0, 200.0, 
                                               float(scan.get(key, 0.0)), key=f"inp_{key}")
            
            if st.form_submit_button("💾 Enregistrer", type="primary"):
                if not id_animal or p70 <= 0:
                    st.error("ID et Poids J70 obligatoires!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?)",
                                (id_animal, race, date_nais.strftime("%Y-%m-%d"), obj, "2 Dents", datetime.now()))
                            c.execute("""
                                INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?,?,?,?,?,?,?,?,?)
                            """, (id_animal, p10, p30, p70, mens['h_garrot'], 
                                  mens['l_corps'], mens['p_thoracique'], mens['l_poitrine'], mens['c_canon']))
                        
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
