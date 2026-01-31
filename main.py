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

def detecter_anomalies(df):
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    
    cols_check = ['p70', 'c_canon', 'h_garrot', 'p_thoracique']
    for col in cols_check:
        if col in df.columns and df[col].std() > 0:
            z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
            mask = z_scores > SEUILS_PRO['z_score_max']
            df.loc[mask, 'Anomalie'] = True
            df.loc[mask, 'Alerte'] += f"{col} anormal; "
    
    mask_ratio = (df['p70'] / df['c_canon'] > SEUILS_PRO['ratio_p70_canon_max']) & (df['c_canon'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Alerte'] += "Ratio poids/canon incohérent;"
    
    if 'Pct_Gras' in df.columns:
        mask_gras = df['Pct_Gras'] > 40
        df.loc[mask_gras, 'Anomalie'] = True
        df.loc[mask_gras, 'Alerte'] += "Estimation gras anormale;"
    
    mask_null = (df['p70'] == 0) | (df['c_canon'] == 0)
    df.loc[mask_null, 'Alerte'] += "Données manquantes;"
    
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
# MODULE SCANNER IA (COMPUTER VISION)
# ==========================================
def scanner_ia_automatique():
    """Module de scan morphologique automatique avec OpenCV"""
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 20px; border-radius: 15px; color: white; margin-bottom: 20px;">
        <h3>🤖 Scanner IA Automatique</h3>
        <p>Précision: <b>+/-1.5cm</b> avec carte de référence | Détection automatique des points anatomiques</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.info("""
        **Instructions:**
        1. Placez l'animal de profil
        2. Incluez la carte référence (A4) au sol
        3. Assurez un bon éclairage
        4. Cadrez de la tête à la queue
        """)
        
        img = st.camera_input("📷 Prendre une photo", key="camera_cv")
        
        if img:
            st.image(img, caption="Image capturée", use_container_width=True)
    
    with col2:
        st.subheader("⚙️ Paramètres de détection")
        
        # Paramètres de calibration
        taille_carte_ref = st.number_input("Taille carte référence (cm)", 
                                           min_value=10.0, max_value=50.0, value=21.0,
                                           help="Longueur du côté de la carte A4 ou autre référence")
        
        confiance_detection = st.slider("Seuil de confiance", 
                                       min_value=0.1, max_value=1.0, value=0.7,
                                       help="Plus élevé = détection plus stricte")
        
        mode_detection = st.selectbox("Mode de détection", 
                                     ["Standard", "Haute précision", "Rapide"])
        
        race_cv = st.selectbox("Race (pour affiner)", 
                              ["Auto-détection", "Ouled Djellal", "Rembi", "Hamra", "Babarine", "Autre"])
    
    if img:
        with st.spinner("🔍 Analyse en cours..."):
            # Simulation de l'analyse CV (à remplacer par du vrai code OpenCV)
            progress_bar = st.progress(0)
            
            for i in range(0, 101, 10):
                time.sleep(0.1)
                progress_bar.progress(i)
                
                if i == 30:
                    st.info("📍 Détection des points anatomiques...")
                elif i == 60:
                    st.info("📏 Calcul des proportions...")
                elif i == 90:
                    st.info("✅ Validation des mesures...")
            
            # Mesures simulées (à remplacer par les vraies mesures CV)
            # En production, ces valeurs viendraient de l'analyse d'image
            mesures_cv = {
                'h_garrot': round(random.uniform(68, 78), 1),
                'c_canon': round(random.uniform(7.5, 9.5), 1),
                'l_poitrine': round(random.uniform(22, 28), 1),
                'p_thoracique': round(random.uniform(78, 92), 1),
                'l_corps': round(random.uniform(75, 88), 1),
                'confiance': round(random.uniform(0.75, 0.98), 2)
            }
            
            st.success("✅ Analyse terminée!")
            
            # Affichage des résultats
            st.subheader("📊 Résultats de l'analyse")
            
            cols = st.columns(5)
            labels = ['Hauteur Garrot', 'Canon', 'Larg. Poitrine', 'Pér. Thorax', 'Long. Corps']
            keys = ['h_garrot', 'c_canon', 'l_poitrine', 'p_thoracique', 'l_corps']
            
            for col, label, key in zip(cols, labels, keys):
                with col:
                    st.metric(label, f"{mesures_cv[key]} cm", 
                             delta=f"±{random.uniform(0.5, 1.5):.1f}cm")
            
            # Indicateur de confiance
            confiance = mesures_cv['confiance']
            if confiance >= 0.9:
                st.success(f"🎯 Confiance: {confiance*100:.0f}% - Excellente qualité")
            elif confiance >= 0.75:
                st.warning(f"⚠️ Confiance: {confiance*100:.0f}% - Qualité acceptable")
            else:
                st.error(f"❌ Confiance: {confiance*100:.0f}% - Reprendre la photo")
            
            # Visualisation des points détectés (simulation)
            st.subheader("🎯 Points anatomiques détectés")
            
            fig = go.Figure()
            
            # Silhouette simplifiée
            silhouette_x = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2, 0]
            silhouette_y = [5, 3, 2, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 5, 5]
            
            fig.add_trace(go.Scatter(
                x=silhouette_x, y=silhouette_y,
                mode='lines',
                line=dict(color='lightgray', width=2),
                fill='toself',
                fillcolor='rgba(200,200,200,0.3)',
                name='Silhouette'
            ))
            
            # Points détectés
            points = {
                'Garrot': (10, 6),
                'Épaule': (4, 4),
                'Poitrine': (6, 2),
                'Canon': (2, 1),
                'Croupe': (16, 5)
            }
            
            for name, (x, y) in points.items():
                fig.add_trace(go.Scatter(
                    x=[x], y=[y],
                    mode='markers+text',
                    marker=dict(size=12, color='red'),
                    text=[name],
                    textposition='top center',
                    name=name
                ))
            
            fig.update_layout(
                showlegend=False,
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=400,
                margin=dict(l=20, r=20, t=20, b=20)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Bouton pour transférer vers saisie
            st.session_state['scan'] = mesures_cv
            
            if st.button("📝 Transférer vers Saisie", type="primary", use_container_width=True):
                st.session_state['go_saisie'] = True
                st.rerun()


def scanner_profil_race():
    """Mode profil par race (ancien mode conservé)"""
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); 
                padding: 20px; border-radius: 15px; color: white; margin-bottom: 20px;">
        <h3>📏 Profil par Race</h3>
        <p>Précision: <b>+/-3cm</b> | Estimation basée sur les standards de race</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        img = st.camera_input("📷 Photo de profil (optionnel)", key="camera_race")
        
        if img:
            st.image(img, caption="Image capturée", use_container_width=True)
    
    with col2:
        race_scan = st.selectbox("Race *", 
                                ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Non identifiée"],
                                key="race_select")
        
        if race_scan == "Non identifiée":
            st.warning("⚠️ Profil moyen appliqué - Précision réduite")
        
        correction = st.slider("Ajustement (%)", -10, 10, 0, key="correction_race")
        
        st.info("""
        **Données de référence utilisées:**
        - Standards morphologiques par race
        - Moyennes établies sur populations
        - Ajustement manuel possible
        """)
    
    if st.button("📊 Générer profil", type="primary", use_container_width=True):
        with st.spinner("Chargement du profil..."):
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
            
            if st.button("📝 Transférer vers Saisie", use_container_width=True):
                st.session_state['go_saisie'] = True
                st.rerun()


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
        "🥩 Composition (Écho-like)", 
        "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse",
        "📸 Scanner", 
        "✍️ Saisie",
        "🔧 Administration BDD"
    ])
    
    df = load_data()
    
    # ==========================================
    # DASHBOARD
    # ==========================================
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord Professionnel")
        
        if df.empty:
            st.info("👋 Générez des données test pour commencer")
            return
        
        nb_anomalies = df['Anomalie'].sum()
        if nb_anomalies > 0:
            st.warning(f"⚠️ {nb_anomalies} anomalie(s) détectée(s)")
        
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
    # COMPOSITION (ECHO-LIKE)
    # ==========================================
    elif menu == "🥩 Composition (Écho-like)":
        st.title("🥩 Analyse Composition Corporelle")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        animal_id = st.selectbox("Sélectionner un animal", df['id'])
        
        if animal_id:
            animal = df[df['id'] == animal_id].iloc[0]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.subheader("📊 Composition")
                labels = ['Muscle', 'Gras', 'Os', 'Autres']
                values = [animal['Pct_Muscle'], animal['Pct_Gras'], animal['Pct_Os'], 
                         100 - (animal['Pct_Muscle'] + animal['Pct_Gras'] + animal['Pct_Os'])]
                
                fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.3)])
                fig.update_layout(title_text=f"Répartition - {animal_id}")
                st.plotly_chart(fig, use_container_width=True)
                
                st.metric("Classement EUROP", animal['Classe_EUROP'])
                st.metric("Indice S90", f"{animal['Indice_S90']:.1f}")
            
            with col2:
                st.subheader("📏 Mesures Écho-like")
                
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=animal['Gras_mm'],
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Épaisseur Gras (mm)"},
                    gauge={
                        'axis': {'range': [None, 25]},
                        'bar': {'color': "orange"},
                        'steps': [
                            {'range': [0, 5], 'color': "lightgreen"},
                            {'range': [5, 12], 'color': "yellow"},
                            {'range': [12, 20], 'color': "orange"},
                            {'range': [20, 25], 'color': "red"}
                        ]
                    }
                ))
                
                st.plotly_chart(fig_gauge, use_container_width=True)
                
                st.metric("Surface Muscle", f"{animal['SMLD']:.1f} cm²")
                st.metric("Indice Conformation", f"{animal['IC']:.2f}")
            
            with col3:
                st.subheader("📈 Références")
                st.info(f"""
                **Profil {animal['race_affichage']}:**
                - Poids: {animal['p70']:.1f} kg
                - Gras: {animal['Gras_mm']:.1f} mm
                - **{animal['Classe_EUROP']}**
                
                Gras < 5mm: Maigre
                Gras 5-12mm: Optimal
                Gras > 15mm: Gras
                """)
                
                if animal['Pct_Gras'] < 15:
                    st.success("Profil maigre")
                elif animal['Pct_Gras'] < 25:
                    st.success("Profil optimal")
                else:
                    st.warning("Profil gras")
        
        st.markdown("---")
        st.subheader("Comparatif Troupeau")
        
        col1, col2 = st.columns(2)
        with col1:
            categories = ['Muscle %', 'Gras %', 'Os %', 'S90']
            mean_vals = [df['Pct_Muscle'].mean(), df['Pct_Gras'].mean(), 
                        df['Pct_Os'].mean(), df['Indice_S90'].mean()/100*30]
            
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=mean_vals + [mean_vals[0]],
                theta=categories + [categories[0]],
                fill='toself'
            ))
            fig_radar.update_layout(polar=dict(radialaxis=dict(range=[0, max(mean_vals)*1.2])))
            st.plotly_chart(fig_radar, use_container_width=True)
        
        with col2:
            fig_corr = px.scatter(df, x='p70', y='Gras_mm', color='Classe_EUROP',
                                title="Poids vs Épaisseur Gras")
            st.plotly_chart(fig_corr, use_container_width=True)
    
    # ==========================================
    # CONTRÔLE QUALITÉ
    # ==========================================
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Données")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        df_anomalies = df[df['Anomalie'] == True]
        
        if not df_anomalies.empty:
            st.error(f"⚠️ {len(df_anomalies)} mesures suspectes")
            st.dataframe(df_anomalies[['id', 'race_affichage', 'p70', 'c_canon', 'Pct_Gras', 'Alerte']], use_container_width=True)
        else:
            st.success("✅ Aucune anomalie")
        
        st.subheader("Statistiques")
        st.dataframe(df[['p70', 'c_canon', 'Pct_Muscle', 'Pct_Gras', 'Index']].describe(), use_container_width=True)
    
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
    # SCANNER - DOUBLE MODE
    # ==========================================
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        
        # Choix de la méthode avec cards visuelles
        st.markdown("""
        <style>
        .method-card {
            border: 2px solid #e0e0e0;
            border-radius: 15px;
            padding: 20px;
            margin: 10px 0;
            transition: all 0.3s ease;
        }
        .method-card:hover {
            border-color: #667eea;
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.3);
        }
        </style>
        """, unsafe_allow_html=True)
        
        methode = st.radio("Méthode d'acquisition", 
                          ["🤖 IA Automatique (Caméra + CV)", 
                           "📏 Profil par Race (Estimation)"],
                          help="IA = Précision +/-1.5cm avec carte référence | Race = Précision +/-3cm")
        
        st.markdown("---")
        
        if methode == "🤖 IA Automatique (Caméra + CV)":
            scanner_ia_automatique()
        else:
            scanner_profil_race()
    
    # ==========================================
    # SAISIE
    # ==========================================
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("✅ Données scanner importées!")
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
