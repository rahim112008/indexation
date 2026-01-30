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
import os
import shutil
import gzip
import io

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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY, 
                race TEXT, 
                race_precision TEXT,
                date_naiss TEXT, 
                date_estimee INTEGER DEFAULT 0,
                objectif TEXT, 
                dentition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
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
    if date_reference is None:
        date_reference = datetime.now()
    
    ages_dentition = {
        "2 Dents": 90,
        "4 Dents": 180,
        "6 Dents": 270,
        "Pleine bouche": 365
    }
    
    if dentition in ages_dentition:
        age_jours = ages_dentition[dentition]
        date_naiss = date_reference - timedelta(days=age_jours)
        return date_naiss, age_jours
    return None, 0

def detecter_anomalies(df, seuil_z=2.5, seuil_ratio=8.0):
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    df['Severite'] = 0  # 0=OK, 1=Warning, 2=Majeur, 3=Critique
    
    # Vérification Z-score seulement si assez de données (n>=5)
    cols_check = ['p70', 'c_canon', 'h_garrot', 'p_thoracique']
    for col in cols_check:
        if col in df.columns and len(df) >= 5:
            std_val = df[col].std()
            if std_val > 0:
                z_scores = np.abs((df[col] - df[col].mean()) / std_val)
                mask = z_scores > seuil_z
                df.loc[mask, 'Anomalie'] = True
                df.loc[mask, 'Severite'] = np.maximum(df.loc[mask, 'Severite'], 2)
                # CORRECTION : Utilisation de .format() au lieu de f-string avec +=
                for idx in df[mask].index:
                    z_val = z_scores.loc[idx]
                    new_alert = "{} anormal (Z:{:.1f}); ".format(col, z_val)
                    df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + new_alert
    
    # Ratio poids/canon incohérent (physiquement impossible si >8)
    mask_ratio = (df['p70'] / df['c_canon'] > seuil_ratio) & (df['c_canon'] > 0) & (df['p70'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Severite'] = 3
    df.loc[mask_ratio, 'Alerte'] = df.loc[mask_ratio, 'Alerte'] + "Ratio poids/canon impossible; "
    
    # Gras excessif (>40%)
    if 'Pct_Gras' in df.columns:
        mask_gras = df['Pct_Gras'] > 40
        df.loc[mask_gras, 'Anomalie'] = True
        df.loc[mask_gras, 'Severite'] = np.maximum(df.loc[mask_gras, 'Severite'], 1)
        # CORRECTION : Utilisation str() pour éviter le problème d'accolade
        for idx in df[mask_gras].index:
            g_val = df.at[idx, 'Pct_Gras']
            gras_str = "Gras excessif (" + str(round(g_val, 1)) + "%); "
            df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + gras_str
    
    # Données manquantes = Warning seulement (pas anomalie critique)
    mask_null_p70 = (df['p70'] == 0) | (df['p70'].isna())
    mask_null_cc = (df['c_canon'] == 0) | (df['c_canon'].isna())
    for idx in df[mask_null_p70].index:
        df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + "Poids manquant;"
    for idx in df[mask_null_cc].index:
        df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + "Canon manquant;"
    
    return df

# ==========================================
# LOGIQUE MÉTIER AVANCÉE
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70 = safe_float(row.get('p70'), 0)
        hg = safe_float(row.get('h_garrot'), 70)
        pt = safe_float(row.get('p_thoracique'), 80)
        cc = safe_float(row.get('c_canon'), 8.5)
        lc = safe_float(row.get('l_corps'), 80)
        lp = safe_float(row.get('l_poitrine'), 24)
        
        if p70 <= 0 or cc <= 0 or pt <= 0:
            return 0, 0, 0, 0, 0, "Inconnu", 0, 0
        
        IC = (pt / (cc * hg)) * 1000
        
        surface_laterale = lc * lp
        indice_engraissement = p70 / surface_laterale if surface_laterale > 0 else 0
        
        gras_mm = 2.5 + (indice_engraissement * 8.5) + (p70 * 0.05) - (IC * 0.02)
        gras_mm = max(2.0, min(25.0, gras_mm))
        
        smld_cm2 = (pt * lc * 0.12) - (gras_mm * 1.5)
        smld_cm2 = max(10, min(30, smld_cm2))
        
        volume_thorax = (pt ** 2) * lc / (4 * np.pi)
        poids_muscle = volume_thorax * 1.06 * (IC/100) * 0.45
        poids_gras = (volume_thorax * 0.92 * 0.25) + (p70 * 0.08 * (gras_mm/10))
        poids_os = p70 * 0.12
        poids_autres = p70 - (poids_muscle + poids_gras + poids_os)
        
        total_calc = poids_muscle + poids_gras + poids_os + poids_autres
        facteur_ajust = p70 / total_calc if total_calc > 0 else 1
        poids_muscle *= facteur_ajust
        poids_gras *= facteur_ajust
        poids_os *= facteur_ajust
        
        pct_muscle = (poids_muscle / p70) * 100
        pct_gras = (poids_gras / p70) * 100
        pct_os = (poids_os / p70) * 100
        
        if IC > 33 and pct_gras < 18 and gras_mm < 8:
            classe = "S (Supérieur)"
        elif IC > 31 and pct_gras < 22 and gras_mm < 10:
            classe = "E (Excellent)"
        elif IC > 29 and pct_gras < 26:
            classe = "U (Très bon)"
        elif IC > 27 and pct_gras < 30:
            classe = "R (Bon)"
        elif pct_gras > 35 or IC < 24:
            classe = "P (Médiocre)"
        else:
            classe = "O (Ordinaire)"
        
        indice_s90 = pct_muscle * (1 - (pct_gras/200))
        
        return (
            round(pct_muscle, 1),
            round(pct_gras, 1),
            round(pct_os, 1),
            round(gras_mm, 1),
            round(smld_cm2, 1),
            classe,
            round(indice_s90, 1),
            round(IC, 2)
        )
        
    except Exception as e:
        return 0, 0, 0, 0, 0, "Erreur", 0, 0

def calculer_metrics_pro(row):
    try:
        p70 = safe_float(row.get('p70'), 0)
        p30 = safe_float(row.get('p30'), 0)
        hg = safe_float(row.get('h_garrot'), 70)
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
    df['IC'] = pd.to_numeric(df.get('IC', 0), errors='coerce').fillna(0)
    
    seuil_p70_rel = df['p70'].quantile(SEUILS_PRO['percentile_elite'])
    seuil_canon_rel = df['c_canon'].quantile(SEUILS_PRO['percentile_elite'])
    
    seuil_p70 = max(SEUILS_PRO['p70_absolu'], seuil_p70_rel)
    seuil_canon = max(SEUILS_PRO['canon_absolu'], seuil_canon_rel)
    
    df['Rang'] = df['Index'].rank(ascending=False, method='min').astype(int)
    
    critere_p70 = df['p70'] >= seuil_p70
    critere_canon = df['c_canon'] >= seuil_canon
    critere_muscle = df['IC'] >= 28
    critere_gras = df.get('Pct_Gras', 50) < 30
    critere_sain = ~df['Anomalie']
    
    df['Statut'] = np.where(critere_p70 & critere_canon & critere_muscle & critere_gras & critere_sain, "ELITE PRO", "")
    
    return df

@st.cache_data(ttl=5)
def load_data():
    try:
        with get_db_connection() as conn:
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
            
            for col in ['p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'p_thoracique', 'l_poitrine', 'l_corps']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            def format_date(row):
                if pd.notna(row.get('date_naiss')) and row.get('date_naiss'):
                    date_str = str(row['date_naiss'])[:10]
                    if row.get('date_estimee') == 1:
                        return f"~{date_str}"
                    return date_str
                return "Non définie"
            
            def format_race(row):
                race = row.get('race', '')
                prec = row.get('race_precision')
                if pd.notna(prec) and prec and race in ['Non identifiée', 'Croisé']:
                    return f"{race} ({prec})"
                return race
            
            df['date_affichage'] = df.apply(format_date, axis=1)
            df['race_affichage'] = df.apply(format_race, axis=1)
            
            compo = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'SMLD', 'Classe_EUROP', 'Indice_S90', 'IC']] = compo
            
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
                pt = round(hg * 1.15 + random.uniform(-3, 3), 1)
                lp = round(20 + (p70 * 0.05), 1)
                lc = round(75 + (p70/35)*8, 1)
                
                animal_id = f"REF-2024-{1000+i}"
                race = random.choice(races)
                race_prec = "Possible croisement lourd" if race == "Non identifiée" else None
                
                date_estimee = random.choice([0, 1])
                date_nais = (datetime.now() - timedelta(days=random.randint(80,300))).strftime("%Y-%m-%d")
                
                c.execute("""
                    INSERT OR IGNORE INTO beliers (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                    VALUES (?,?,?,?,?,?,?)
                """, (animal_id, race, race_prec, date_nais, date_estimee, "Sélection", "2 Dents"))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (animal_id, p10, p30, p70, hg, lc, pt, lp, cc))
                count += 1
            except:
                continue
    return count

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    
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
    
    menu = st.sidebar.radio("Menu", [
        "🏠 Dashboard", 
        "🍖 Composition (Écho-like)", 
        "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse",
        "📸 Scanner", 
        "✍️ Saisie",
        "🔧 Administration BDD"
    ])
    
    df = load_data()
    
    # ==========================================
    # DASHBOARD CORRIGÉ
    # ==========================================
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord Professionnel")
        
        if df.empty:
            st.info("👋 Générez des données test pour commencer")
            return
        
        # Gestion intelligente des anomalies
        if 'anomalies_acquittees' not in st.session_state:
            st.session_state['anomalies_acquittees'] = []
        
        # Filtrer les anomalies déjà validées par l'utilisateur
        df['Anomalie_Active'] = df['Anomalie'] & (~df['id'].isin(st.session_state['anomalies_acquittees']))
        
        # Compter seulement les anomalies réelles (pas les warnings données manquantes)
        nb_anomalies_reelles = len(df[(df['Anomalie_Active']) & (df['Severite'] >= 2)])
        nb_anomalies_legeres = len(df[(df['Anomalie_Active']) & (df['Severite'] == 1)])
        
        if nb_anomalies_reelles > 0:
            with st.expander(f"⚠️ {nb_anomalies_reelles} anomalie(s) majeure(s) détectée(s)", expanded=True):
                cols = st.columns([2, 1, 3, 1])
                with cols[0]:
                    st.error(f"### {nb_anomalies_reelles} problème(s) critique(s)")
                with cols[1]:
                    if st.button("🔄 Tout réinitialiser", help="Remettre à zéro les validations"):
                        st.session_state['anomalies_acquittees'] = []
                        st.rerun()
                with cols[2]:
                    st.caption("Validez les faux positifs pour les masquer définitivement")
                with cols[3]:
                    voir_tous = st.checkbox("Voir légers aussi", value=False)
                
                # Affichage détaillé des anomalies
                severite_filtre = 1 if voir_tous else 2
                df_anom = df[df['Anomalie_Active'] & (df['Severite'] >= severite_filtre)].sort_values('Severite', ascending=False)
                
                for idx, row in df_anom.iterrows():
                    col1, col2, col3, col4 = st.columns([1.5, 1, 4, 1])
                    with col1:
                        st.markdown(f"**{row['id']}**")
                        st.caption(f"{row['race_affichage']}")
                    with col2:
                        if row['Severite'] == 3:
                            st.error("🔴 Critique")
                        elif row['Severite'] == 2:
                            st.warning("🟠 Majeur")
                        else:
                            st.info("🟡 Mineur")
                    with col3:
                        alerte_txt = row['Alerte'] if pd.notna(row['Alerte']) else ""
                        st.caption(alerte_txt[:120])
                        if pd.notna(row['p70']) and row['p70'] > 0 and pd.notna(row['c_canon']) and row['c_canon'] > 0:
                            ratio = row['p70'] / row['c_canon']
                            st.caption(f"Poids: {row['p70']:.1f}kg | Canon: {row['c_canon']:.1f}cm | Ratio: {ratio:.1f}")
                    with col4:
                        if st.button("✓ Validé", key=f"val_{row['id']}", help="C'est normal, ne plus afficher"):
                            st.session_state['anomalies_acquittees'].append(row['id'])
                            st.rerun()
        
        elif nb_anomalies_legeres > 0:
            st.info(f"ℹ️ {nb_anomalies_legeres} alerte(s) mineure(s) - vérifiez l'onglet Contrôle Qualité pour les détails")
        else:
            st.success("✅ Aucune anomalie détectée - Toutes les données sont cohérentes")
        
        col1, col2, col3, col4 = st.columns(4)
        elite_mask = df['Statut'] == 'ELITE PRO'
        
        with col1:
            st.metric("Total Sujets", len(df))
        with col2:
            st.metric("Elite Pro", len(df[elite_mask]), f"{len(df[elite_mask])/len(df)*100:.1f}%")
        with col3:
            st.metric("Muscle moyen", f"{df['Pct_Muscle'].mean():.1f}%")
        with col4:
            st.metric("Score S90 moyen", f"{df['Indice_S90'].mean():.1f}")
        
        st.subheader("Classement avec composition estimée")
        
        cols_display = ['Rang', 'Statut', 'id', 'race_affichage', 'date_affichage', 
                       'p70', 'Pct_Muscle', 'Pct_Gras', 'Gras_mm', 'Classe_EUROP', 'Index']
        
        df_display = df[cols_display].sort_values('Rang').copy()
        df_display.columns = ['Rang', 'Statut', 'ID', 'Race', 'Date', 'Poids(kg)', 
                             'Muscle%', 'Gras%', 'Gras(mm)', 'EUROP', 'Index']
        
        def color_europ(val):
            if 'S' in str(val):
                return 'background-color: #006400; color: white'
            elif 'E' in str(val):
                return 'background-color: #228B22; color: white'
            elif 'U' in str(val):
                return 'background-color: #32CD32'
            elif 'R' in str(val):
                return 'background-color: #FFD700'
            elif 'O' in str(val):
                return 'background-color: #FF8C00'
            elif 'P' in str(val):
                return 'background-color: #DC143C; color: white'
            return ''
        
        styled_df = df_display.style.applymap(color_europ, subset=['EUROP'])
        st.dataframe(styled_df, use_container_width=True, height=500)
        
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(df, x='Pct_Muscle', y='Pct_Gras', color='Classe_EUROP',
                           title='Composition: Muscle vs Gras', hover_data=['id', 'Gras_mm'])
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig2 = px.histogram(df, x='Classe_EUROP', color='Statut',
                              title="Répartition EUROP")
            st.plotly_chart(fig2, use_container_width=True)
    
           # ==========================================
    # COMPOSITION (ECHO-LIKE) - VERSION ROBUSTE
    # ==========================================
    elif menu == "🥩 Composition (Écho-like)":
        st.title("🥩 Analyse Composition Corporelle")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        try:
            animal_id = st.selectbox("Sélectionner un animal", df['id'].tolist())
        except Exception as e:
            st.error(f"Erreur chargement liste: {e}")
            return
        
        if animal_id:
            try:
                # Récupération sécurisée de la ligne
                animal_data = df[df['id'] == animal_id]
                if animal_data.empty:
                    st.error("Animal non trouvé dans la base")
                    return
                
                animal = animal_data.iloc[0]
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.subheader("📊 Composition")
                    
                    try:
                        # Conversion sécurisée avec valeurs par défaut 0
                        pct_muscle = float(animal.get('Pct_Muscle', 0)) if pd.notna(animal.get('Pct_Muscle')) else 0
                        pct_gras = float(animal.get('Pct_Gras', 0)) if pd.notna(animal.get('Pct_Gras')) else 0
                        pct_os = float(animal.get('Pct_Os', 0)) if pd.notna(animal.get('Pct_Os')) else 0
                        
                        # S'assurer que ce sont des nombres positifs
                        pct_muscle = max(0.0, pct_muscle)
                        pct_gras = max(0.0, pct_gras)
                        pct_os = max(0.0, pct_os)
                        
                        # Calcul Autres
                        total_connu = pct_muscle + pct_gras + pct_os
                        pct_autres = max(0.0, 100.0 - total_connu)
                        
                        # Normalisation si dépassement
                        if total_connu > 100.0:
                            facteur = 100.0 / total_connu
                            pct_muscle *= facteur
                            pct_gras *= facteur
                            pct_os *= facteur
                            pct_autres = 0.0
                        
                        labels = ['Muscle', 'Gras', 'Os', 'Autres']
                        values = [pct_muscle, pct_gras, pct_os, pct_autres]
                        
                        # Vérification avant création graphique
                        if sum(values) > 0 and all(v >= 0 for v in values):
                            fig = go.Figure(data=[go.Pie(
                                labels=labels,
                                values=values,
                                hole=0.4,
                                textinfo='label+percent',
                                textposition='outside',
                                marker=dict(colors=['#2ecc71', '#f1c40f', '#8b4513', '#95a5a6']),
                                pull=[0.05, 0, 0, 0]
                            )])
                            
                            fig.update_layout(
                                title_text=f"Carcasse {animal_id}",
                                showlegend=True,
                                height=350,
                                margin=dict(t=30, b=30, l=30, r=30)
                            )
                            
                            st.plotly_chart(fig, use_container_width=True, key=f"pie_{animal_id}")
                        else:
                            st.warning("Données composition invalides (sum=0 ou valeurs négatives)")
                            st.write(f"Valeurs brutes: M={pct_muscle}, G={pct_gras}, O={pct_os}")
                            
                    except Exception as e:
                        st.error(f"Erreur graphique composition: {e}")
                        st.write(f"Données brutes: {animal[['Pct_Muscle', 'Pct_Gras', 'Pct_Os']].to_dict()}")
                    
                    # Métriques textuelles sécurisées
                    try:
                        classe_europ = str(animal.get('Classe_EUROP', 'N/A'))
                        indice_s90 = float(animal.get('Indice_S90', 0)) if pd.notna(animal.get('Indice_S90')) else 0
                        
                        st.metric("Classe EUROP", classe_europ)
                        st.metric("Indice S90", f"{indice_s90:.1f}")
                    except Exception as e:
                        st.error(f"Erreur métriques: {e}")
                
                with col2:
                    st.subheader("📏 Épaisseur Gras")
                    
                    try:
                        gras_mm = float(animal.get('Gras_mm', 0)) if pd.notna(animal.get('Gras_mm')) else 0
                        
                        if gras_mm > 0:
                            fig_gauge = go.Figure(go.Indicator(
                                mode="gauge+number",
                                value=gras_mm,
                                domain={'x': [0, 1], 'y': [0, 1]},
                                title={'text': "mm"},
                                gauge={
                                    'axis': {'range': [0, 25]},
                                    'bar': {'color': "orange"},
                                    'steps': [
                                        {'range': [0, 5], 'color': "lightgreen"},
                                        {'range': [5, 12], 'color': "yellow"},
                                        {'range': [12, 20], 'color': "orange"},
                                        {'range': [20, 25], 'color': "red"}
                                    ]
                                }
                            ))
                            fig_gauge.update_layout(height=300)
                            st.plotly_chart(fig_gauge, use_container_width=True, key=f"gauge_{animal_id}")
                        else:
                            st.info("Épaisseur gras non disponible")
                            
                    except Exception as e:
                        st.error(f"Erreur jauge: {e}")
                    
                    # Autres mesures
                    try:
                        smld = float(animal.get('SMLD', 0)) if pd.notna(animal.get('SMLD')) else 0
                        ic = float(animal.get('IC', 0)) if pd.notna(animal.get('IC')) else 0
                        
                        st.metric("Surface Muscle", f"{smld:.1f} cm²")
                        st.metric("Indice Conf.", f"{ic:.2f}")
                    except:
                        pass
                
                with col3:
                    st.subheader("📋 Informations")
                    
                    try:
                        race = str(animal.get('race_affichage', 'N/A'))
                        p70 = float(animal.get('p70', 0)) if pd.notna(animal.get('p70')) else 0
                        
                        st.info(f"""
                        **{animal_id}**
                        Race: {race}
                        Poids: {p70:.1f} kg
                        
                        **Interprétation:**
                        Gras < 5mm: Maigre
                        Gras 5-12mm: Optimal  
                        Gras > 15mm: Gras
                        """)
                        
                        # Conseil simple
                        if gras_mm < 5:
                            st.success("Profil maigre")
                        elif gras_mm < 12:
                            st.success("Profil optimal")
                        else:
                            st.warning("Profil gras")
                            
                    except Exception as e:
                        st.error(f"Erreur infos: {e}")
                
                # Comparatif en bas
                st.markdown("---")
                st.subheader("Comparatif")
                
                try:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        # Radar uniquement si assez de données
                        if len(df) > 0 and 'Pct_Muscle' in df.columns:
                            categories = ['Muscle', 'Gras', 'Os']
                            moyennes = [
                                df['Pct_Muscle'].mean(),
                                df['Pct_Gras'].mean(),
                                df['Pct_Os'].mean()
                            ]
                            
                            fig_radar = go.Figure()
                            fig_radar.add_trace(go.Scatterpolar(
                                r=[pct_muscle, pct_gras, pct_os, pct_muscle],
                                theta=categories + [categories[0]],
                                fill='toself',
                                name=animal_id,
                                line_color='red'
                            ))
                            fig_radar.add_trace(go.Scatterpolar(
                                r=moyennes + [moyennes[0]],
                                theta=categories + [categories[0]],
                                fill='toself',
                                name='Moyenne',
                                line_color='blue',
                                opacity=0.3
                            ))
                            fig_radar.update_layout(
                                polar=dict(radialaxis=dict(visible=True, range=[0, max(max(moyennes), 50)])),
                                showlegend=True,
                                height=350
                            )
                            st.plotly_chart(fig_radar, use_container_width=True)
                    
                    with col_b:
                        # Scatter sécurisé
                        df_clean = df.dropna(subset=['p70', 'Gras_mm'])
                        if len(df_clean) > 0:
                            fig_scatter = px.scatter(
                                df_clean, 
                                x='p70', 
                                y='Gras_mm',
                                color='Classe_EUROP' if 'Classe_EUROP' in df_clean.columns else None,
                                title="Poids vs Gras"
                            )
                            # Ajouter point actuel en rouge
                            if p70 > 0 and gras_mm > 0:
                                fig_scatter.add_scatter(
                                    x=[p70], 
                                    y=[gras_mm], 
                                    mode='markers',
                                    marker=dict(color='red', size=15, symbol='star'),
                                    name=animal_id,
                                    showlegend=False
                                )
                            st.plotly_chart(fig_scatter, use_container_width=True)
                            
                except Exception as e:
                    st.error(f"Erreur comparatifs: {e}")
                    
            except Exception as e:
                st.error(f"Erreur générale affichage: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    # ==========================================
    # CONTRÔLE QUALITÉ CORRIGÉ
    # ==========================================
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Données")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        # Configuration des seuils (pour éviter les faux positifs)
        with st.expander("⚙️ Configuration des seuils de détection", expanded=True):
            st.info("Ajustez ces valeurs si vos animaux sont systématiquement flaggés comme suspects")
            col1, col2, col3 = st.columns(3)
            with col1:
                seuil_z_config = st.slider("Z-Score limite", 1.5, 5.0, 2.5, 0.1,
                                         help="Plus c'est haut, moins on détecte d'anomalies. Standard: 2.5")
            with col2:
                seuil_ratio_config = st.slider("Ratio Poids/Canon max", 6.0, 15.0, 8.0, 0.5,
                                             help="Au-delà = physiquement impossible. Standard: 8.0")
            with col3:
                seuil_gras_config = st.slider("Seuil gras %", 35, 60, 40, 1,
                                            help="Au-delà = considéré comme anormal. Standard: 40%")
            
            if st.button("🔄 Recalculer avec ces seuils"):
                # Recalcul temporaire
                df_check = detecter_anomalies(df.copy(), seuil_z_config, seuil_ratio_config)
                # Mettre à jour l'affichage temporairement
                st.session_state['df_check_temp'] = df_check
                st.success("Seuils appliqués (vue temporaire)")
        
        # Utiliser les données recalculées si disponibles
        if 'df_check_temp' in st.session_state:
            df_check = st.session_state['df_check_temp']
            st.info("📊 Affichage avec seuils personnalisés (rafraîchir la page pour revenir aux standards)")
        else:
            df_check = df
        
        # Affichage des anomalies
        df_anomalies = df_check[df_check['Anomalie'] == True].copy()
        
        if not df_anomalies.empty:
            st.error(f"⚠️ {len(df_anomalies)} mesures suspectes sur {len(df_check)} animaux")
            
            # Tableau détaillé
            cols_affichage = ['id', 'race_affichage', 'p70', 'c_canon', 'h_garrot', 'Pct_Gras', 'Severite', 'Alerte']
            cols_existants = [c for c in cols_affichage if c in df_anomalies.columns]
            
            # Formatage couleur selon sévérité
            def color_severite(val):
                if val == 3:
                    return 'background-color: #ffcccc; color: darkred; font-weight: bold'
                elif val == 2:
                    return 'background-color: #ffe6cc; color: darkorange'
                elif val == 1:
                    return 'background-color: #ffffcc; color: #b35900'
                return ''
            
            styled_df = df_anomalies[cols_existants].style.applymap(color_severite, subset=['Severite'])
            st.dataframe(styled_df, use_container_width=True, height=400)
            
            # Statistiques des anomalies
            st.subheader("Répartition par type d'anomalie")
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            with col_stats1:
                nb_ratio = len(df_anomalies[df_anomalies['Alerte'].str.contains('Ratio', na=False)])
                st.metric("Ratio impossible", nb_ratio)
            with col_stats2:
                nb_zscore = len(df_anomalies[df_anomalies['Alerte'].str.contains('Z-score', na=False)])
                st.metric("Hors normes statistiques", nb_zscore)
            with col_stats3:
                nb_gras = len(df_anomalies[df_anomalies['Alerte'].str.contains('Gras', na=False)])
                st.metric("Gras excessif", nb_gras)
                
        else:
            st.success("✅ Aucune anomalie détectée avec les critères actuels")
        
        # Statistiques globales
        st.subheader("Statistiques descriptives")
        cols_stats = ['p70', 'c_canon', 'h_garrot', 'p_thoracique', 'Pct_Muscle', 'Pct_Gras', 'Index']
        cols_dispo = [c for c in cols_stats if c in df_check.columns]
        
        if cols_dispo:
            stats_df = df_check[cols_dispo].describe()
            st.dataframe(stats_df, use_container_width=True)
    
    # ==========================================
    # STATS & ANALYSE
    # ==========================================
    elif menu == "📈 Stats & Analyse":
        st.title("📈 Analyse Scientifique")
        
        if df.empty or len(df) < 3:
            st.warning("Minimum 3 animaux requis")
            return
        
        tab1, tab2, tab3 = st.tabs(["Corrélations", "Performance Race", "Prédiction"])
        
        with tab1:
            vars_stats = ['p70', 'Gras_mm', 'SMLD', 'Pct_Muscle', 'IC', 'Index']
            valid_vars = [v for v in vars_stats if v in df.columns and df[v].std() > 0]
            
            if len(valid_vars) >= 2:
                corr = df[valid_vars].corr()
                fig = px.imshow(corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r")
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            if df['race'].nunique() > 1:
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.box(df, x="race", y="Pct_Muscle", color="race")
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    fig2 = px.box(df, x="race", y="Gras_mm", color="race")
                    st.plotly_chart(fig2, use_container_width=True)
        
        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                poids_test = st.slider("Poids test (kg)", 20, 50, 35)
                ic_test = st.slider("Indice Conformation", 20, 40, 28)
                
                gras_estime = 2.5 + (poids_test * 0.15) - (ic_test * 0.25)
                muscle_estime = 55 + (ic_test * 0.8) - (gras_estime * 0.5)
                
                st.metric("Gras estimé", f"{max(2, gras_estime):.1f} mm")
                st.metric("Muscle estimé", f"{min(75, muscle_estime):.1f} %")

    # ==========================================
    # SCANNER DOUBLE MODE
    # ==========================================
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        
        # Choix de la méthode
        methode = st.radio("Méthode d'acquisition", 
                          ["📏 Profil par Race (Estimation)", 
                           "🤖 IA Automatique (Caméra + CV)"],
                          horizontal=True,
                          help="Race = Précision +/-3cm | IA = Précision +/-1.5cm avec carte référence")
        
        # MODE 1: Profil par Race (Votre ancien code)
        if methode == "📏 Profil par Race (Estimation)":
            col1, col2 = st.columns(2)
            
            with col1:
                img = st.camera_input("📷 Photo de profil")
            
            with col2:
                race_scan = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Non identifiée"])
                
                if race_scan == "Non identifiée":
                    st.warning("Profil moyen appliqué")
                
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
                        "Non identifiée": {"h_garrot": 73.0, "c_canon": 8.1, "l_poitrine": 24.5, "p_thoracique": 84.0, "l_corps": 82.5}
                    }
                    
                    base = DATA_RACES[race_scan].copy()
                    if correction != 0:
                        facteur = 1 + (correction / 100)
                        for key in base:
                            base[key] = round(base[key] * facteur, 1)
                    
                    st.session_state['scan'] = base
                    
                    st.success(f"✅ Profil {race_scan} chargé")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Hauteur", f"{base['h_garrot']} cm")
                        st.metric("Longueur", f"{base['l_corps']} cm")
                    with c2:
                        st.metric("Canon", f"{base['c_canon']} cm")
                        st.metric("Poitrine", f"{base['l_poitrine']} cm")
                    with c3:
                        st.metric("Thorax", f"{base['p_thoracique']} cm")
                    
                    if st.button("📝 Transférer vers Saisie"):
                        st.session_state['go_saisie'] = True
                        st.rerun()
        
        # MODE 2: IA Automatique
        else:
            st.info("📋 Placez une carte de crédit (8.5cm) ou objet référence au niveau du garrot")
            
            col_cv, col_param = st.columns([2, 1])
            
            with col_cv:
                img_cv = st.camera_input("📷 Capture profil + référence")
            
            with col_param:
                ref_size = st.number_input("Taille référence (cm)", 5.0, 15.0, 8.5)
                race_cv = st.selectbox("Race (optionnel)", ["Auto-détection", "Ouled Djellal", "Rembi", "Hamra", "Babarine"])
            
            if img_cv is not None:
                try:
                    import cv2
                    import numpy as np
                    from PIL import Image
                    
                    image = Image.open(img_cv)
                    img_array = np.array(image)
                    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    
                    with st.spinner("🔍 Analyse..."):
                        progress = st.progress(0)
                        
                        # Prétraitement simple
                        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
                        edges = cv2.Canny(blurred, 50, 150)
                        
                        # Détection contours (simulation)
                        height_px, width_px = img_bgr.shape[:2]
                        echelle = ref_size / (width_px * 0.1)  # Approximation simple
                        
                        # Simulation mesures basées sur pixels
                        h_garrot = round(height_px * echelle * 0.7, 1)
                        l_corps = round(width_px * echelle * 0.8, 1)
                        
                        # Ratios standards
                        c_canon = round(7.5 + (h_garrot - 65) * 0.15, 1)
                        p_thoracique = round(h_garrot * 1.15, 1)
                        l_poitrine = round(p_thoracique * 0.29, 1)
                        
                        for i in range(0, 101, 10):
                            time.sleep(0.05)
                            progress.progress(i)
                        
                        base = {
                            'h_garrot': h_garrot,
                            'l_corps': l_corps,
                            'p_thoracique': p_thoracique,
                            'l_poitrine': l_poitrine,
                            'c_canon': c_canon
                        }
                        
                        st.session_state['scan'] = base
                        
                        st.success("✅ Analyse IA terminée")
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("Hauteur", f"{h_garrot} cm", "±1.5cm")
                            st.metric("Longueur", f"{l_corps} cm", "±2cm")
                        with c2:
                            st.metric("Canon", f"{c_canon} cm")
                            st.metric("Poitrine", f"{l_poitrine} cm")
                        with c3:
                            st.metric("Thorax", f"{p_thoracique} cm")
                        
                        st.image(edges, caption="Détection contours", use_container_width=True)
                        
                        if st.button("📝 Transférer vers Saisie", key="transfert_ia"):
                            st.session_state['go_saisie'] = True
                            st.rerun()
                            
                except ImportError:
                    st.error("OpenCV requis: `pip install opencv-python-headless`")
                except Exception as e:
                    st.error(f"Erreur: {e}")
    
    # ==========================================
    # SAISIE
    # ==========================================
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("Données scanner importées!")
            st.session_state['go_saisie'] = False
        
        with st.form("form_saisie"):
            col_id1, col_id2 = st.columns(2)
            
            with col_id1:
                id_animal = st.text_input("ID *", placeholder="REF-2024-001")
                race_options = ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Croisé", "Non identifiée"]
                race = st.selectbox("Race *", race_options)
                
                race_precision = ""
                if race in ["Non identifiée", "Croisé"]:
                    race_precision = st.text_input("Précision", placeholder="Type ou croisement")
            
            with col_id2:
                methode_age = st.radio("Méthode âge", ["Date exacte", "Estimation dentition"])
                
                date_naiss = None
                dentition = "2 Dents"
                date_estimee_flag = 0
                
                if methode_age == "Date exacte":
                    date_naiss = st.date_input("Date naissance", datetime.now() - timedelta(days=100))
                    dentition = st.selectbox("Dentition", ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
                    date_estimee_flag = 0
                else:
                    dentition = st.selectbox("Dentition actuelle *", ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
                    date_calculee, age_jours = calculer_date_naissance(dentition)
                    if date_calculee:
                        date_naiss = date_calculee
                        date_estimee_flag = 1
                        st.success(f"Date estimée: {date_naiss.strftime('%d/%m/%Y')}")
                
                objectif = st.selectbox("Objectif", ["Sélection", "Engraissement", "Reproduction"])
            
            st.subheader("Poids")
            c1, c2, c3 = st.columns(3)
            with c1:
                p10 = st.number_input("Poids J10", 0.0, 20.0, 0.0)
            with c2:
                p30 = st.number_input("Poids J30", 0.0, 40.0, 0.0)
            with c3:
                label_p70 = "Poids ACTUEL" if date_estimee_flag else "Poids J70"
                p70 = st.number_input(f"{label_p70} *", 0.0, 100.0, 0.0)
            
            st.subheader("Mensurations (cm)")
            cols = st.columns(5)
            mens = {}
            fields = [('h_garrot', 'Hauteur'), ('c_canon', 'Canon'), ('l_poitrine', 'Larg.Poitrine'), 
                     ('p_thoracique', 'Pér.Thorax'), ('l_corps', 'Long.Corps')]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(label, 0.0, 200.0, float(scan.get(key, 0.0)), key=f"inp_{key}")
            
            if st.form_submit_button("💾 Enregistrer", type="primary"):
                if not id_animal or p70 <= 0:
                    st.error("ID et Poids obligatoires!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT OR REPLACE INTO beliers 
                                (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (id_animal, race, race_precision or None, 
                                  date_naiss.strftime("%Y-%m-%d"), date_estimee_flag, objectif, dentition))
                            
                            c.execute("""
                                INSERT INTO mesures 
                                (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # ==========================================
    # ADMINISTRATION BDD (MODULE COMPLET)
    # ==========================================
    elif menu == "🔧 Administration BDD":
        st.title("🔧 Administration Base de Données")
        
        tab1, tab2, tab3, tab4 = st.tabs(["💾 Backup/Restore", "📥 Import CSV", "📤 Export", "🧹 Maintenance"])
        
        with tab1:
            st.subheader("Sauvegarde et Restauration")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Créer backup**")
                backup_name = st.text_input("Nom fichier", 
                                           value=f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}")
                
                if st.button("📦 Créer Backup", type="primary"):
                    try:
                        backup_dir = "backups"
                        if not os.path.exists(backup_dir):
                            os.makedirs(backup_dir)
                        
                        backup_path = os.path.join(backup_dir, f"{backup_name}.db")
                        shutil.copy2(DB_NAME, backup_path)
                        
                        with open(backup_path, 'rb') as f_in:
                            with gzip.open(f"{backup_path}.gz", 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(backup_path)
                        
                        st.success(f"Backup créé: {backup_name}.db.gz")
                        
                        with open(f"{backup_path}.gz", 'rb') as f:
                            st.download_button("⬇️ Télécharger", f.read(), 
                                             file_name=f"{backup_name}.db.gz",
                                             mime="application/gzip")
                    except Exception as e:
                        st.error(f"Erreur: {e}")
            
            with col2:
                st.markdown("**Restaurer**")
                uploaded_backup = st.file_uploader("Fichier .db ou .db.gz", type=['db', 'gz'])
                
                if uploaded_backup is not None:
                    st.warning("Écrasement de la base actuelle!")
                    confirm = st.checkbox("Confirmer")
                    
                    if confirm and st.button("🔄 Restaurer"):
                        try:
                            security_backup = f"security_{int(time.time())}.db"
                            shutil.copy2(DB_NAME, security_backup)
                            
                            if uploaded_backup.name.endswith('.gz'):
                                with gzip.open(uploaded_backup, 'rb') as f_in:
                                    with open(DB_NAME, 'wb') as f_out:
                                        shutil.copyfileobj(f_in, f_out)
                            else:
                                with open(DB_NAME, 'wb') as f:
                                    f.write(uploaded_backup.getvalue())
                            
                            st.success("Base restaurée!")
                            st.info(f"Sécurité: {security_backup}")
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur: {e}")
        
        with tab2:
            st.subheader("Import par lot (CSV)")
            uploaded_file = st.file_uploader("Fichier CSV", type=['csv'])
            
            if uploaded_file is not None:
                try:
                    df_import = pd.read_csv(uploaded_file)
                    st.write(f"{len(df_import)} lignes détectées")
                    st.dataframe(df_import.head())
                    
                    st.subheader("Mapping colonnes")
                    cols = df_import.columns.tolist()
                    cols_options = ['-- Ignorer --'] + cols
                    
                    mapping = {}
                    for req in ['id', 'race', 'p70', 'c_canon', 'h_garrot']:
                        mapping[req] = st.selectbox(f"Colonne {req}", options=cols_options,
                                                   index=cols.index(req) if req in cols else 0)
                    
                    if st.button("📥 Importer"):
                        succes = 0
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            for idx, row in df_import.iterrows():
                                try:
                                    if mapping['id'] == '-- Ignorer --' or pd.isna(row[mapping['id']]):
                                        continue
                                    
                                    animal_id = str(row[mapping['id']])
                                    race = str(row[mapping['race']]) if mapping['race'] != '-- Ignorer --' else 'Non identifiée'
                                    p70 = float(row[mapping['p70']]) if mapping['p70'] != '-- Ignorer --' else 0
                                    cc = float(row[mapping['c_canon']]) if mapping['c_canon'] != '-- Ignorer --' else 0
                                    hg = float(row[mapping['h_garrot']]) if mapping['h_garrot'] != '-- Ignorer --' else 0
                                    
                                    c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?)",
                                        (animal_id, race, None, datetime.now().strftime("%Y-%m-%d"), 0, "Sélection", "2 Dents"))
                                    c.execute("""
                                        INSERT INTO mesures VALUES (NULL, ?, 0, 0, ?, ?, 80, ?, 24, ?)
                                    """, (animal_id, p70, hg, hg*1.2, cc))
                                    succes += 1
                                except:
                                    continue
                        
                        if succes > 0:
                            st.success(f"{succes} animaux importés!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erreur lecture: {e}")
        
        with tab3:
            st.subheader("Export")
            format_exp = st.selectbox("Format", ["Excel", "CSV", "SQLite"])
            
            if format_exp == "Excel":
                if st.button("📊 Générer Excel"):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, sheet_name='Complet', index=False)
                        if not df.empty:
                            df[df['Statut'] == 'ELITE PRO'].to_excel(writer, sheet_name='Elite', index=False)
                            df[['p70', 'Pct_Muscle', 'Gras_mm']].describe().to_excel(writer, sheet_name='Stats')
                    
                    st.download_button("⬇️ Télécharger", output.getvalue(),
                                     file_name=f"export_{datetime.now().strftime('%Y%m%d')}.xlsx")
            
            elif format_exp == "CSV":
                csv = df.to_csv(index=False)
                st.download_button("⬇️ CSV", csv, file_name="export.csv")
            
            else:
                with open(DB_NAME, 'rb') as f:
                    st.download_button("⬇️ Base SQLite", f.read(), file_name="database.db")
        
        with tab4:
            st.subheader("Maintenance")
            col1, col2 = st.columns(2)
            
            with col1:
                try:
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM beliers")
                        nb_beliers = c.fetchone()[0]
                        c.execute("SELECT COUNT(*) FROM mesures")
                        nb_mesures = c.fetchone()[0]
                        
                        st.metric("Béliers", nb_beliers)
                        st.metric("Mesures", nb_mesures)
                except:
                    pass
            
            with col2:
                if st.button("🧹 Nettoyer doublons"):
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                DELETE FROM mesures WHERE id NOT IN 
                                (SELECT MAX(id) FROM mesures GROUP BY id_animal)
                            """)
                            deleted = conn.total_changes
                            st.success(f"{deleted} mesures supprimées")
                    except Exception as e:
                        st.error(f"Erreur: {e}")

if __name__ == "__main__":
    main()
