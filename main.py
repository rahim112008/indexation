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
    'z_score_max': 3.0,  # Augmente a 3.0 pour eviter trop de faux positifs
    'ratio_p70_canon_max': 8.0
}

# ==========================================
# INITIALISATION
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon=":")
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

def detecter_anomalies(df, seuil_z=3.0, seuil_ratio=8.0):
    """
    Detection d'anomalies avec seuils ajustables.
    Severite: 3=Critique (impossible), 2=Majeur (hors normes), 1=Leger (gras eleve/missing)
    """
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    df['Severite'] = 0
    
    cols_check = ['p70', 'c_canon', 'h_garrot', 'p_thoracique']
    
    for col in cols_check:
        if col in df.columns and len(df) >= 5:
            std_val = df[col].std()
            mean_val = df[col].mean()
            
            # Protection: ignorer Z-score si trop peu de variance (donnees homogenes)
            if std_val > 0 and (std_val / mean_val) > 0.05:
                z_scores = np.abs((df[col] - mean_val) / std_val)
                mask = z_scores > seuil_z
                
                # Limite: max 15% du troupeau pour eviter tout flagger
                if mask.sum() <= len(df) * 0.15:
                    df.loc[mask, 'Anomalie'] = True
                    df.loc[mask, 'Severite'] = np.maximum(df.loc[mask, 'Severite'], 2)
                    for idx in df[mask].index:
                        z_val = z_scores.loc[idx]
                        new_alert = col + " Z=" + str(round(z_val, 1)) + "; "
                        df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + new_alert
    
    # Ratio poids/canon - CRITIQUE (physiquement impossible)
    mask_ratio = (df['p70'] / df['c_canon'] > seuil_ratio) & (df['c_canon'] > 0) & (df['p70'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Severite'] = 3
    df.loc[mask_ratio, 'Alerte'] = df.loc[mask_ratio, 'Alerte'] + "Ratio poids/canon impossible (>8); "
    
    # Gras excessif - WARNING seulement (pas anomalie critique)
    if 'Pct_Gras' in df.columns:
        mask_gras = df['Pct_Gras'] > 45  # Tres eleve
        df.loc[mask_gras, 'Alerte'] = df.loc[mask_gras, 'Alerte'] + "Gras excessif (>45%); "
        df.loc[mask_gras, 'Severite'] = np.maximum(df.loc[mask_gras, 'Severite'], 1)
    
    # Donnees manquantes - Information uniquement
    mask_null = (df['p70'] == 0) | (df['c_canon'] == 0)
    df.loc[mask_null, 'Alerte'] = df.loc[mask_null, 'Alerte'] + "Donnees incomplete;"
    # NOTE: On ne met PAS Anomalie=True pour donnees manquantes seules
    
    return df

# ==========================================
# LOGIQUE METIER AVANCEE
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
            classe = "S (Superieur)"
        elif IC > 31 and pct_gras < 22 and gras_mm < 10:
            classe = "E (Excellent)"
        elif IC > 29 and pct_gras < 26:
            classe = "U (Tres bon)"
        elif IC > 27 and pct_gras < 30:
            classe = "R (Bon)"
        elif pct_gras > 35 or IC < 24:
            classe = "P (Mediocre)"
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
            return 0.0, 0.0, 0.0, "Donnees insuffisantes"
        
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
            commentaire = "Excellence genetique"
        elif index_final >= 70:
            commentaire = "Bon potentiel"
        elif index_final >= 50:
            commentaire = "Standard"
        else:
            commentaire = "A surveiller"
            
        return round(gmq, 1), round(rendement, 1), round(index_final, 1), commentaire
        
    except Exception as e:
        return 0.0, 0.0, 0.0, "Erreur"

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
                        return "~" + date_str
                    return date_str
                return "Non definie"
            
            def format_race(row):
                race = row.get('race', '')
                prec = row.get('race_precision')
                if pd.notna(prec) and prec and race in ['Non identifiee', 'Croise']:
                    return race + " (" + prec + ")"
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
        st.error("Erreur chargement donnees: " + str(e))
        return pd.DataFrame()

def generer_demo(n=30):
    """
    Generation avec 20% d'elites, 5% d'anomalies, 75% standard
    """
    races = ["Ouled Djellal", "Rembi", "Hamra"]
    count = 0
    
    with get_db_connection() as conn:
        c = conn.cursor()
        for i in range(n):
            try:
                # Tirage au sort du profil
                rand = random.random()
                is_super = rand < 0.20      # 20% Elite
                is_anomalie = rand > 0.95   # 5% Anomalie (0.95 a 1.0)
                
                if is_super:
                    # PROFIL ELITE : Gros, muscle, conformation exceptionnelle
                    p10 = round(random.uniform(5.5, 6.5), 1)
                    p30 = round(p10 + random.uniform(13, 16), 1)  # Bon GMQ
                    p70 = round(random.uniform(42, 52), 1)        # Poids eleve
                    cc = round(random.uniform(9.5, 11.5), 1)      # Gros canon
                    hg = round(76 + random.uniform(0, 3), 1)      # Grand gabarit
                    
                elif is_anomalie:
                    # PROFIL ANOMALIE : Donnees incoherentes
                    choix_anomalie = random.choice(['leg', 'canon'])
                    if choix_anomalie == 'leg':
                        p10 = round(random.uniform(3.0, 4.0), 1)   # Trop petit
                        p30 = round(p10 + random.uniform(5, 8), 1)
                        p70 = round(random.uniform(18, 24), 1)     # Non viable
                        cc = round(random.uniform(7.0, 8.5), 1)
                        hg = round(62 + random.uniform(-2, 2), 1)
                    else:  # canon anormal
                        p10 = round(random.uniform(4.5, 6.0), 1)
                        p30 = round(p10 + random.uniform(9, 13), 1)
                        p70 = round(random.uniform(35, 45), 1)
                        cc = round(random.uniform(4.5, 6.0), 1)    # Canon trop fin pour le poids
                        hg = round(68 + random.uniform(-2, 2), 1)
                else:
                    # PROFIL STANDARD : Performances moyennes
                    p10 = round(random.uniform(4.5, 6.0), 1)
                    p30 = round(p10 + random.uniform(9, 13), 1)
                    p70 = round(random.uniform(28, 38), 1)        # 30-35kg moyenne
                    cc = round(7.8 + random.uniform(-0.5, 0.8), 1) # 8cm moyen
                    hg = round(70 + random.uniform(-2, 3), 1)      # 70-73cm standard
                
                # Calculs derives coherents pour tous les profils
                pt = round(hg * 1.15 + random.uniform(-2, 2), 1)
                lp = round(24 + (p70 * 0.05), 1)
                lc = round(78 + (p70/40)*6, 1)  # Longueur proportionnelle au poids
                
                animal_id = "REF-2024-" + str(1000+i)
                race = random.choice(races)
                race_prec = None
                if race == "Non identifiee":
                    race_prec = "Possible croisement"
                
                date_estimee = random.choice([0, 1])
                date_nais = (datetime.now() - timedelta(days=random.randint(80,300))).strftime("%Y-%m-%d")
                
                c.execute("""
                    INSERT OR IGNORE INTO beliers (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                    VALUES (?,?,?,?,?,?,?)
                """, (animal_id, race, race_prec, date_nais, date_estimee, "Selection", "2 Dents"))
                
                c.execute("""
                    INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (animal_id, p10, p30, p70, hg, lc, pt, lp, cc))
                count += 1
                
            except Exception as e:
                continue
                
    return count

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    
    st.sidebar.title("Expert Selector Pro")
    st.sidebar.markdown("---")
    
    df_temp = load_data()
    if not df_temp.empty:
        st.sidebar.metric("Sujets en base", len(df_temp))
        # Afficher combien d'elites
        nb_elites = len(df_temp[df_temp['Statut'] == 'ELITE PRO'])
        if nb_elites > 0:
            st.sidebar.success(str(nb_elites) + " elites detectes")
    
    if st.sidebar.button("Generer 30 sujets test", use_container_width=True):
        with st.spinner("Creation..."):
            n = generer_demo(30)
            st.sidebar.success(str(n) + " crees!")
            time.sleep(0.5)
            st.rerun()
    
    if st.sidebar.button("Vider la base", use_container_width=True):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mesures")
            conn.execute("DELETE FROM beliers")
        st.sidebar.success("Base videe!")
        st.rerun()
    
    st.sidebar.markdown("---")
    
    menu = st.sidebar.radio("Menu", [
        "Dashboard", 
        "Composition", 
        "Controle Qualite", 
        "Stats",
        "Scanner", 
        "Saisie",
        "Administration"
    ])
    
    df = load_data()
    
    # ==========================================
    # DASHBOARD
    # ==========================================
    if menu == "Dashboard":
        st.title("Tableau de Bord Professionnel")
        
        if df.empty:
            st.info("Generez des donnees test pour commencer")
            return
        
        if 'anomalies_acquittees' not in st.session_state:
            st.session_state['anomalies_acquittees'] = []
        
        df['Anomalie_Active'] = df['Anomalie'] & (~df['id'].isin(st.session_state['anomalies_acquittees']))
        nb_anomalies_reelles = len(df[(df['Anomalie_Active']) & (df['Severite'] >= 2)])
        
        if nb_anomalies_reelles > 0:
            with st.expander("Attention: " + str(nb_anomalies_reelles) + " anomalies majeures", expanded=True):
                if st.button("Tout reinitialiser"):
                    st.session_state['anomalies_acquittees'] = []
                    st.rerun()
                df_anom = df[df['Anomalie_Active'] & (df['Severite'] >= 2)]
                for idx, row in df_anom.iterrows():
                    st.write(row['id'] + " - " + str(row['Alerte'])[:50])
                    if st.button("Valide " + row['id'], key="val_" + row['id']):
                        st.session_state['anomalies_acquittees'].append(row['id'])
                        st.rerun()
        else:
            st.success("Aucune anomalie majeure detectee")
        
        col1, col2, col3, col4 = st.columns(4)
        elite_mask = df['Statut'] == 'ELITE PRO'
        
        with col1:
            st.metric("Total Sujets", len(df))
        with col2:
            st.metric("Elite Pro", len(df[elite_mask]))
        with col3:
            st.metric("Muscle moyen", str(round(df['Pct_Muscle'].mean(), 1)) + "%")
        with col4:
            st.metric("Score S90 moyen", str(round(df['Indice_S90'].mean(), 1)))
        
        st.subheader("Classement")
        
        cols_display = ['Rang', 'Statut', 'id', 'race_affichage', 'date_affichage', 
                       'p70', 'Pct_Muscle', 'Pct_Gras', 'Gras_mm', 'Classe_EUROP', 'Index']
        
        df_display = df[cols_display].sort_values('Rang').copy()
        df_display.columns = ['Rang', 'Statut', 'ID', 'Race', 'Date', 'Poids', 
                             'Muscle%', 'Gras%', 'Gras_mm', 'EUROP', 'Index']
        st.dataframe(df_display, use_container_width=True, height=500)
    
    # ==========================================
    # COMPOSITION (ECHO-LIKE)
    # ==========================================
    elif menu == "Composition":
        st.title("Analyse Composition Corporelle")
        
        if df.empty:
            st.warning("Pas de donnees disponibles")
            return
        
        animal_id = st.selectbox("Selectionner un animal", df['id'].tolist())
        
        if not animal_id:
            return
            
        animal_data = df[df['id'] == animal_id]
        if animal_data.empty:
            st.error("Animal introuvable")
            return
            
        animal = animal_data.iloc[0]
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Composition Carcasse")
            
            val_muscle = 0.0
            val_gras = 0.0
            val_os = 0.0
            
            try:
                if 'Pct_Muscle' in animal and pd.notna(animal['Pct_Muscle']):
                    val_muscle = float(animal['Pct_Muscle'])
                if 'Pct_Gras' in animal and pd.notna(animal['Pct_Gras']):
                    val_gras = float(animal['Pct_Gras'])
                if 'Pct_Os' in animal and pd.notna(animal['Pct_Os']):
                    val_os = float(animal['Pct_Os'])
            except:
                pass
            
            val_muscle = max(0.0, val_muscle)
            val_gras = max(0.0, val_gras)
            val_os = max(0.0, val_os)
            
            total = val_muscle + val_gras + val_os
            val_autres = max(0.0, 100.0 - total)
            
            if total > 100.0:
                val_muscle = val_muscle * 100.0 / total
                val_gras = val_gras * 100.0 / total
                val_os = val_os * 100.0 / total
                val_autres = 0.0
            
            if total > 0:
                try:
                    fig = go.Figure(data=[go.Pie(
                        labels=['Muscle', 'Gras', 'Os', 'Autres'],
                        values=[val_muscle, val_gras, val_os, val_autres],
                        hole=0.4,
                        marker_colors=['#2ecc71', '#f1c40f', '#8b4513', '#95a5a6']
                    )])
                    fig.update_layout(
                        title_text=animal_id,
                        height=400,
                        showlegend=True
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error("Erreur graphique: " + str(e))
            else:
                st.info("Donnees composition insuffisantes")
            
            st.metric("Classe EUROP", str(animal.get('Classe_EUROP', 'N/A')))
            st.metric("Indice S90", str(round(float(animal.get('Indice_S90', 0)), 1)))
        
        with col2:
            st.subheader("Mesures Echographie")
            
            gras_mm = 0.0
            try:
                if 'Gras_mm' in animal and pd.notna(animal['Gras_mm']):
                    gras_mm = float(animal['Gras_mm'])
            except:
                pass
            
            if gras_mm > 0:
                try:
                    fig_gauge = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=gras_mm,
                        domain={'x': [0, 1], 'y': [0, 1]},
                        title={'text': "Epaisseur Gras (mm)"},
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
                    st.plotly_chart(fig_gauge, use_container_width=True)
                except:
                    st.write("Gras: " + str(gras_mm) + " mm")
            else:
                st.info("Donnee gras non disponible")
            
            smld = float(animal.get('SMLD', 0)) if pd.notna(animal.get('SMLD')) else 0
            ic = float(animal.get('IC', 0)) if pd.notna(animal.get('IC')) else 0
            
            st.metric("Surface Muscle", str(round(smld, 1)) + " cm2")
            st.metric("Indice Conformation", str(round(ic, 2)))
        
        with col3:
            st.subheader("Informations")
            
            race_disp = str(animal.get('race_affichage', 'N/A'))
            poids_disp = float(animal.get('p70', 0)) if pd.notna(animal.get('p70')) else 0
            
            st.write("**" + animal_id + "**")
            st.write("Race: " + race_disp)
            st.write("Poids: " + str(round(poids_disp, 1)) + " kg")
            st.write("EUROP: " + str(animal.get('Classe_EUROP', 'N/A')))
            
            if val_gras < 15:
                st.success("Profil maigre")
            elif val_gras < 25:
                st.success("Profil optimal")
            else:
                st.warning("Profil gras")
    
    # ==========================================
    # CONTROLE QUALITE - CORRIGE
    # ==========================================
    elif menu == "Controle Qualite":
        st.title("Validation des Donnees")
        
        if df.empty:
            st.info("Pas de donnees disponibles")
            return
        
        # Configuration et filtres
        col_filtre, col_conf = st.columns([1, 2])
        
        with col_filtre:
            voir_seulement = st.selectbox(
                "Afficher les alertes",
                options=[
                    "Toutes (y compris legeres)", 
                    "Anomalies majeures seulement (Rouge)", 
                    "Problemes critiques uniquement (Noir)"
                ],
                help="Filtrez pour voir seulement les vrais problemes"
            )
        
        with col_conf:
            with st.expander("Configuration des seuils de detection", expanded=True):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    seuil_z = st.slider(
                        "Z-Score (sensibilite)", 
                        min_value=2.0, 
                        max_value=5.0, 
                        value=3.0, 
                        step=0.1,
                        help="3.0 = standard | 2.5 = strict (plus d'alertes) | 4.0 = tolerant"
                    )
                
                with col2:
                    seuil_r = st.slider(
                        "Ratio Poids/Canon max", 
                        min_value=6.0, 
                        max_value=12.0, 
                        value=8.0, 
                        step=0.5,
                        help="Au-dela = physiquement impossible"
                    )
                
                with col3:
                    seuil_gras = st.slider(
                        "Seuil gras % (warning)", 
                        min_value=35, 
                        max_value=50, 
                        value=45, 
                        step=1,
                        help="Au-dela = flaggue comme gras excessif"
                    )
                
                if st.button("Recalculer avec ces seuils", type="primary"):
                    # Recalcul temporaire avec nouveaux seuils
                    df_temp = detecter_anomalies(df.copy(), seuil_z=seuil_z, seuil_ratio=seuil_r)
                    # Appliquer aussi le seuil gras custom
                    if 'Pct_Gras' in df_temp.columns:
                        mask_gras = df_temp['Pct_Gras'] > seuil_gras
                        df_temp.loc[mask_gras, 'Alerte'] = df_temp.loc[mask_gras, 'Alerte'] + "Gras eleve (>" + str(seuil_gras) + "%); "
                        df_temp.loc[mask_gras, 'Severite'] = np.maximum(df_temp.loc[mask_gras, 'Severite'], 1)
                    
                    st.session_state['df_filtered'] = df_temp
                    st.success("Recalcul effectue!")
        
        # Utiliser le dataframe filtre si disponible, sinon original
        if 'df_filtered' in st.session_state:
            df_display = st.session_state['df_filtered']
        else:
            df_display = df
        
        # Application du filtre d'affichage
        if voir_seulement == "Problemes critiques uniquement (Noir)":
            df_display = df_display[df_display['Severite'] == 3]
        elif voir_seulement == "Anomalies majeures seulement (Rouge)":
            df_display = df_display[df_display['Severite'] >= 2]
        # Sinon: afficher tout (y compris severity 1 et 0)
        
        # Comptage par niveau
        nb_critiques = len(df_display[df_display['Severite'] == 3])
        nb_majeures = len(df_display[df_display['Severite'] == 2])
        nb_legeres = len(df_display[df_display['Severite'] == 1])
        nb_ok = len(df_display[df_display['Severite'] == 0])
        
        # Resume
        st.markdown("---")
        res_cols = st.columns(4)
        with res_cols[0]:
            st.error("🔴 Critiques: " + str(nb_critiques))
        with res_cols[1]:
            st.warning("🟠 Majeures: " + str(nb_majeures))
        with res_cols[2]:
            st.info("🟡 Legeres: " + str(nb_legeres))
        with res_cols[3]:
            st.success("🟢 Normaux: " + str(nb_ok))
        
        # Affichage du tableau
        if len(df_display) > 0:
            # Preparer les colonnes a afficher
            cols_base = ['id', 'race_affichage', 'p70', 'c_canon', 'Pct_Gras', 'Severite', 'Alerte']
            cols_dispo = [c for c in cols_base if c in df_display.columns]
            
            # Fonction de coloration
            def color_severity(val):
                if val == 3:
                    return 'background-color: #ff4444; color: white; font-weight: bold'
                elif val == 2:
                    return 'background-color: #ffaa44; color: black'
                elif val == 1:
                    return 'background-color: #ffff88; color: black'
                else:
                    return 'background-color: #ccffcc; color: black'
            
            # Appliquer style
            styled_df = df_display[cols_dispo].style.applymap(
                color_severity, subset=['Severite'] if 'Severite' in cols_dispo else []
            )
            
            st.subheader("Details des anomalies")
            st.dataframe(styled_df, use_container_width=True, height=400)
            
            # Details des rayons (pour les anomalies critiques)
            if nb_critiques > 0:
                st.subheader("🔴 Details problèmes critiques")
                crit_df = df_display[df_display['Severite'] == 3]
                for idx, row in crit_df.iterrows():
                    with st.expander(str(row['id']) + " - " + str(row.get('race_affichage', 'N/A'))):
                        st.write("**Alerte:** " + str(row.get('Alerte', 'N/A')))
                        st.write("Poids: " + str(row.get('p70', 0)) + " kg | Canon: " + str(row.get('c_canon', 0)) + " cm")
                        ratio_calc = float(row.get('p70', 0)) / float(row.get('c_canon', 1))
                        st.write("Ratio calcule: " + str(round(ratio_calc, 1)) + " (seuil: 8.0)")
        else:
            st.success("Aucune donnee a afficher avec les filtres actuels")
        
        # Statistiques globales (toutes donnees)
        st.markdown("---")
        st.subheader("Statistiques globales du troupeau")
        stats_cols = ['p70', 'c_canon', 'Pct_Muscle', 'Pct_Gras', 'IC']
        stats_ok = [c for c in stats_cols if c in df.columns]
        if stats_ok:
            st.dataframe(df[stats_ok].describe(), use_container_width=True)
    
    # ==========================================
    # STATS & ANALYSE
    # ==========================================
    elif menu == "Stats":
        st.title("Analyse Scientifique")
        
        if df.empty or len(df) < 3:
            st.warning("Minimum 3 animaux requis")
            return
        
        tab1, tab2 = st.tabs(["Correlations", "Performance Race"])
        
        with tab1:
            vars_stats = ['p70', 'Gras_mm', 'Pct_Muscle', 'IC']
            valid_vars = [v for v in vars_stats if v in df.columns and df[v].std() > 0]
            if len(valid_vars) >= 2:
                corr = df[valid_vars].corr()
                fig = px.imshow(corr, text_auto=".2f", aspect="auto")
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            if df['race'].nunique() > 1:
                fig = px.box(df, x="race", y="Pct_Muscle")
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================
    # SCANNER
    # ==========================================
    elif menu == "Scanner":
        st.title("Scanner Morphologique")
        
        methode = st.radio("Methode", ["Profil Race", "IA Automatique"])
        
        if methode == "Profil Race":
            col1, col2 = st.columns(2)
            with col1:
                img = st.camera_input("Photo")
            with col2:
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Non identifiee"])
                corr = st.slider("Ajustement", -10, 10, 0)
                
                if img:
                    DATA_RACES = {
                        "Ouled Djellal": {"h_garrot": 72.0, "c_canon": 8.0, "l_poitrine": 24.0, "p_thoracique": 83.0, "l_corps": 82.0},
                        "Rembi": {"h_garrot": 76.0, "c_canon": 8.8, "l_poitrine": 26.0, "p_thoracique": 88.0, "l_corps": 86.0},
                        "Hamra": {"h_garrot": 70.0, "c_canon": 7.8, "l_poitrine": 23.0, "p_thoracique": 80.0, "l_corps": 78.0},
                        "Non identifiee": {"h_garrot": 73.0, "c_canon": 8.1, "l_poitrine": 24.5, "p_thoracique": 84.0, "l_corps": 82.5}
                    }
                    base = DATA_RACES[race].copy()
                    if corr != 0:
                        f = 1 + (corr / 100)
                        for k in base:
                            base[k] = base[k] * f
                    
                    st.session_state['scan'] = base
                    st.json(base)
                    if st.button("Transferer vers Saisie"):
                        st.session_state['go_saisie'] = True
                        st.rerun()
    
    # ==========================================
    # SAISIE
    # ==========================================
    elif menu == "Saisie":
        st.title("Nouvelle Fiche")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("Donnees importees!")
            st.session_state['go_saisie'] = False
        
        with st.form("form_saisie"):
            col_id1, col_id2 = st.columns(2)
            
            with col_id1:
                id_animal = st.text_input("ID", placeholder="REF-2024-001")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croise", "Non identifiee"])
            
            with col_id2:
                date_naiss = st.date_input("Date naissance", datetime.now() - timedelta(days=100))
                objectif = st.selectbox("Objectif", ["Selection", "Engraissement"])
            
            st.subheader("Poids")
            c1, c2, c3 = st.columns(3)
            with c1:
                p10 = st.number_input("J10", 0.0, 20.0, 0.0)
            with c2:
                p30 = st.number_input("J30", 0.0, 40.0, 0.0)
            with c3:
                p70 = st.number_input("J70", 0.0, 100.0, 0.0)
            
            st.subheader("Mensurations")
            cols = st.columns(5)
            mens = {}
            fields = [('h_garrot', 'Hauteur'), ('c_canon', 'Canon'), ('l_poitrine', 'Larg.Poitrine'), 
                     ('p_thoracique', 'Per.Thorax'), ('l_corps', 'Long.Corps')]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(label, 0.0, 200.0, float(scan.get(key, 0.0)), key=key)
            
            if st.form_submit_button("Enregistrer"):
                if not id_animal or p70 <= 0:
                    st.error("ID et Poids obligatoires!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT OR REPLACE INTO beliers (id, race, date_naiss, objectif)
                                VALUES (?, ?, ?, ?)
                            """, (id_animal, race, date_naiss.strftime("%Y-%m-%d"), objectif))
                            
                            c.execute("""
                                INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (id_animal, p10, p30, p70, mens['h_garrot'], 
                                  mens['l_corps'], mens['p_thoracique'], mens['l_poitrine'], mens['c_canon']))
                        
                        st.success("Enregistre!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error("Erreur: " + str(e))

    # ==========================================
    # ADMINISTRATION
    # ==========================================
    elif menu == "Administration":
        st.title("Administration BDD")
        
        tab1, tab2 = st.tabs(["Backup", "Export"])
        
        with tab1:
            if st.button("Creer Backup"):
                try:
                    backup_dir = "backups"
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)
                    backup_path = os.path.join(backup_dir, "backup_" + datetime.now().strftime('%Y%m%d_%H%M') + ".db")
                    shutil.copy2(DB_NAME, backup_path)
                    st.success("Cree: " + backup_path)
                except Exception as e:
                    st.error(str(e))
        
        with tab2:
            if st.button("Exporter CSV"):
                csv = df.to_csv(index=False)
                st.download_button("Telecharger CSV", csv, file_name="export.csv")

if __name__ == "__main__":
    main()
