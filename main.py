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

def detecter_anomalies(df, seuil_z=2.5, seuil_ratio=8.0):
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    df['Severite'] = 0
    
    cols_check = ['p70', 'c_canon', 'h_garrot', 'p_thoracique']
    for col in cols_check:
        if col in df.columns and len(df) >= 5:
            std_val = df[col].std()
            if std_val > 0:
                z_scores = np.abs((df[col] - df[col].mean()) / std_val)
                mask = z_scores > seuil_z
                df.loc[mask, 'Anomalie'] = True
                df.loc[mask, 'Severite'] = np.maximum(df.loc[mask, 'Severite'], 2)
                for idx in df[mask].index:
                    z_val = z_scores.loc[idx]
                    new_alert = col + " anormal (Z:" + str(round(z_val, 1)) + "); "
                    df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + new_alert
    
    mask_ratio = (df['p70'] / df['c_canon'] > seuil_ratio) & (df['c_canon'] > 0) & (df['p70'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Severite'] = 3
    df.loc[mask_ratio, 'Alerte'] = df.loc[mask_ratio, 'Alerte'] + "Ratio poids/canon impossible; "
    
    if 'Pct_Gras' in df.columns:
        mask_gras = df['Pct_Gras'] > 40
        df.loc[mask_gras, 'Anomalie'] = True
        df.loc[mask_gras, 'Severite'] = np.maximum(df.loc[mask_gras, 'Severite'], 1)
        for idx in df[mask_gras].index:
            g_val = df.at[idx, 'Pct_Gras']
            gras_str = "Gras excessif (" + str(round(g_val, 1)) + "%); "
            df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + gras_str
    
    mask_null_p70 = (df['p70'] == 0) | (df['p70'].isna())
    mask_null_cc = (df['c_canon'] == 0) | (df['c_canon'].isna())
    for idx in df[mask_null_p70].index:
        df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + "Poids manquant;"
    for idx in df[mask_null_cc].index:
        df.at[idx, 'Alerte'] = df.at[idx, 'Alerte'] + "Canon manquant;"
    
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
    races = ["Ouled Djellal", "Rembi", "Hamra", "Non identifiee"]
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
                
                animal_id = "REF-2024-" + str(1000+i)
                race = random.choice(races)
                race_prec = "Possible croisement lourd" if race == "Non identifiee" else None
                
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
            except:
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
            st.success("Aucune anomalie detectee")
        
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
    # COMPOSITION (ECHO-LIKE) - VERSION CORRIGEE
    # ==========================================
    elif menu == "Composition":
        st.title("Analyse Composition Corporelle")
        
        if df.empty:
            st.warning("Pas de donnees disponibles")
            return
        
        # Selection avec verification
        animal_id = st.selectbox("Selectionner un animal", df['id'].tolist())
        
        if not animal_id:
            return
            
        # Recuperation securisee
        animal_data = df[df['id'] == animal_id]
        if animal_data.empty:
            st.error("Animal introuvable")
            return
            
        animal = animal_data.iloc[0]
        
        # Colonnes pour layout
        col1, col2, col3 = st.columns(3)
        
        # ========== COLONNE 1: COMPOSITION ==========
        with col1:
            st.subheader("Composition Carcasse")
            
            # Extraction securisee des valeurs
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
            
            # Protection contre negatives
            val_muscle = max(0.0, val_muscle)
            val_gras = max(0.0, val_gras)
            val_os = max(0.0, val_os)
            
            # Calcul autres
            total = val_muscle + val_gras + val_os
            val_autres = max(0.0, 100.0 - total)
            
            # Normalisation si > 100
            if total > 100.0:
                val_muscle = val_muscle * 100.0 / total
                val_gras = val_gras * 100.0 / total
                val_os = val_os * 100.0 / total
                val_autres = 0.0
            
            # Affichage graphique uniquement si valeurs valides
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
            
            # Metriques textuelles
            st.metric("Classe EUROP", str(animal.get('Classe_EUROP', 'N/A')))
            st.metric("Indice S90", str(round(float(animal.get('Indice_S90', 0)), 1)))
        
        # ========== COLONNE 2: MESURES ==========
        with col2:
            st.subheader("Mesures Echographie")
            
            # Gras mm
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
            
            # Autres mesures
            smld = float(animal.get('SMLD', 0)) if pd.notna(animal.get('SMLD')) else 0
            ic = float(animal.get('IC', 0)) if pd.notna(animal.get('IC')) else 0
            
            st.metric("Surface Muscle", str(round(smld, 1)) + " cm2")
            st.metric("Indice Conformation", str(round(ic, 2)))
        
        # ========== COLONNE 3: INFOS ==========
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
    # CONTROLE QUALITE
    # ==========================================
    elif menu == "Controle Qualite":
        st.title("Validation des Donnees")
        
        if df.empty:
            st.info("Pas de donnees")
            return
        
        with st.expander("Configuration des seuils", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                seuil_z = st.slider("Z-Score", 1.0, 5.0, 2.5, 0.1)
            with col2:
                seuil_r = st.slider("Ratio max", 5.0, 15.0, 8.0, 0.5)
            
            if st.button("Recalculer"):
                df = detecter_anomalies(df, seuil_z, seuil_r)
                st.session_state['df_check'] = df
                st.success("Recalcule effectue")
        
        if 'df_check' in st.session_state:
            df = st.session_state['df_check']
        
        df_anom = df[df['Anomalie'] == True]
        if not df_anom.empty:
            st.error(str(len(df_anom)) + " anomalies detectees")
            st.dataframe(df_anom[['id', 'p70', 'c_canon', 'Alerte']], use_container_width=True)
        else:
            st.success("Aucune anomalie")
        
        st.subheader("Statistiques")
        st.dataframe(df[['p70', 'c_canon', 'Pct_Muscle', 'Pct_Gras']].describe())
    
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
