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
# CONFIGURATION PROFESSIONNELLE (Modifiable sans risque)
# ==========================================
SEUILS_PRO = {
    'p70_absolu': 22.0,        # Poids minimum pour être Elite (kg)
    'canon_absolu': 7.5,       # Canon minimum pour être Elite (cm)  
    'percentile_elite': 0.85,  # Top 15% du troupeau
    'z_score_max': 2.5,        # Détection d'anomalies (écarts > 2.5σ)
    'ratio_p70_canon_max': 8.0 # Alertes si poids disproportionnel au canon
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
    """Base de données inchangée pour compatibilité"""
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
# UTILITAIRES ROBUSTES
# ==========================================
def safe_float(val, default=0.0):
    """Conversion ultra-sécurisée"""
    try:
        if val is None or pd.isna(val):
            return default
        f = float(val)
        return f if not np.isnan(f) else default
    except:
        return default

def detecter_anomalies(df):
    """
    Détecte les erreurs de saisie sans bloquer l'application.
    Retourne un DataFrame avec colonne 'Alerte'
    """
    if df.empty:
        return df
    
    df['Alerte'] = ""
    df['Anomalie'] = False
    
    # 1. Détection Z-Score pour chaque colonne numérique
    cols_check = ['p70', 'c_canon', 'h_garrot']
    for col in cols_check:
        if col in df.columns and df[col].std() > 0:
            z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
            mask = z_scores > SEUILS_PRO['z_score_max']
            df.loc[mask, 'Anomalie'] = True
            df.loc[mask, 'Alerte'] += f"{col} anormal; "
    
    # 2. Ratio biologique impossible
    mask_ratio = (df['p70'] / df['c_canon'] > SEUILS_PRO['ratio_p70_canon_max']) & (df['c_canon'] > 0)
    df.loc[mask_ratio, 'Anomalie'] = True
    df.loc[mask_ratio, 'Alerte'] += "Ratio poids/canon incohérent;"
    
    # 3. Valeurs nulles critiques
    mask_null = (df['p70'] == 0) | (df['c_canon'] == 0)
    df.loc[mask_null, 'Alerte'] += "Données manquantes;"
    
    return df

# ==========================================
# LOGIQUE MÉTIER PROFESSIONNELLE
# ==========================================
def calculer_metrics_pro(row):
    """
    Calcul amélioré avec index normalisé 0-100
    et détection de cohérence biologique
    """
    try:
        # Extraction sécurisée
        p70 = safe_float(row.get('p70'), 0)
        p30 = safe_float(row.get('p30'), 0)
        hg = safe_float(row.get('h_garrot'), 0)
        cc = safe_float(row.get('c_canon'), 0)
        l_poitrine = safe_float(row.get('l_poitrine'), 24)
        p_thoracique = safe_float(row.get('p_thoracique'), 80)
        
        if p70 <= 0 or p30 <= 0 or p30 >= p70:
            return 0.0, 0.0, 0.0, "Données insuffisantes"
        
        # 1. GMQ (Gain Moyen Quotidien)
        gmq = ((p70 - p30) / 40) * 1000
        
        # 2. Rendement estimé
        rendement = 52.4 + (0.35 * l_poitrine) + (0.12 * p_thoracique) - (0.08 * hg)
        rendement = max(40.0, min(65.0, rendement))
        
        # 3. Ratio de Kleiber (indicateur d'état corporel)
        # Formule: Poids / Taille^0.75 (valeur idéale chez l'ovin: 2.5-3.5)
        kleiber = p70 / (hg ** 0.75) if hg > 0 else 0
        
        # 4. INDEX PRO NORMALISÉ (0-100)
        # Composantes: 40% Rendement, 30% GMQ, 20% Poids absolu, 10% Kleiber
        score_rendement = (rendement - 40) / 25 * 100  # Normalisation 40-65% -> 0-100
        score_gmq = min(gmq / 4, 100)  # Plafonné à 400g/j
        score_poids = min(p70 / 35 * 100, 100)  # Plafonné à 35kg
        score_kleiber = min(max((kleiber - 2) * 20, 0), 100)  # Optimal autour de 3
        
        index_final = (
            score_rendement * 0.4 + 
            score_gmq * 0.3 + 
            score_poids * 0.2 + 
            score_kleiber * 0.1
        )
        
        # Commentaire de qualité
        commentaire = ""
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
    """
    Sélection Elite professionnelle:
    - Doit dépasser le seuil ABSOLU (minimum professionnel)
    - ET dépasser le seuil RELATIF (percentile 85)
    - ET ne pas avoir d'anomalie détectée
    """
    if df.empty or len(df) < 3:
        df['Statut'] = ""
        df['Rang'] = 0
        return df
    
    # Nettoyage
    df['p70'] = pd.to_numeric(df['p70'], errors='coerce').fillna(0)
    df['c_canon'] = pd.to_numeric(df['c_canon'], errors='coerce').fillna(0)
    
    # Calcul des seuils
    seuil_p70_rel = df['p70'].quantile(SEUILS_PRO['percentile_elite'])
    seuil_canon_rel = df['c_canon'].quantile(SEUILS_PRO['percentile_elite'])
    
    # Application du MAX(absolu, relatif)
    seuil_p70 = max(SEUILS_PRO['p70_absolu'], seuil_p70_rel)
    seuil_canon = max(SEUILS_PRO['canon_absolu'], seuil_canon_rel)
    
    # Classement global
    df['Rang'] = df['Index'].rank(ascending=False, method='min').astype(int)
    
    # Conditions Elite
    critere_p70 = df['p70'] >= seuil_p70
    critere_canon = df['c_canon'] >= seuil_canon
    critere_sain = ~df['Anomalie']  # Pas d'anomalie détectée
    
    df['Statut'] = np.where(
        critere_p70 & critere_canon & critere_sain,
        "ELITE PRO",
        ""
    )
    
    return df

# ==========================================
# GESTION DES DONNÉES
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
            
            # Conversion numérique
            for col in ['p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'p_thoracique', 'l_poitrine', 'l_corps']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # 1. Détection des anomalies
            df = detecter_anomalies(df)
            
            # 2. Calcul des métriques
            results = df.apply(lambda x: pd.Series(calculer_metrics_pro(x)), axis=1)
            df[['GMQ', 'Rendement', 'Index', 'Appreciation']] = results
            
            # 3. Identification Elite (avec seuils absolus)
            df = identifier_elite_pro(df)
            
            return df
            
    except Exception as e:
        st.error(f"Erreur chargement: {e}")
        return pd.DataFrame()

def generer_demo(n=30):
    """Génération de données test réalistes"""
    races = ["Ouled Djellal", "Rembi", "Hamra"]
    count = 0
    
    with get_db_connection() as conn:
        c = conn.cursor()
        for i in range(n):
            try:
                # Génération cohérente avec quelques anomalies volontaires (5%)
                is_anomalie = random.random() < 0.05
                
                p10 = round(random.uniform(4.0, 6.5), 1)
                p30 = round(p10 + random.uniform(9, 13), 1)
                
                if is_anomalie:
                    p70 = round(random.uniform(15, 50), 1)  # Extrême
                    cc = round(random.uniform(5, 15), 1)    # Incohérent
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
# INTERFACE UTILISATEUR
# ==========================================
def main():
    init_db()
    
    # Sidebar
    st.sidebar.title("💎 Expert Selector Pro")
    st.sidebar.markdown("---")
    
    # Contrôles
    if st.sidebar.button("🚀 Générer 30 sujets test", use_container_width=True):
        with st.spinner("Création..."):
            n = generer_demo(30)
            st.sidebar.success(f"✅ {n} animaux créés")
            time.sleep(0.5)
            st.rerun()
    
    if st.sidebar.button("🗑️ Réinitialiser la base", use_container_width=True):
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mesures")
            conn.execute("DELETE FROM beliers")
        st.sidebar.success("Base vidée")
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Seuil Elite: >{SEUILS_PRO['p70_absolu']}kg & >{SEUILS_PRO['canon_absolu']}cm")
    
    menu = st.sidebar.radio("Menu", ["🏠 Dashboard", "🔍 Contrôle Qualité", "📸 Scanner", "✍️ Saisie"])
    
    # Chargement
    df = load_data()
    
    # --- DASHBOARD PRO ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord Professionnel")
        
        if df.empty:
            st.info("👋 Générez des données test pour commencer")
            return
        
        # Alertes globales
        nb_anomalies = df['Anomalie'].sum()
        if nb_anomalies > 0:
            st.warning(f"⚠️ {nb_anomalies} anomalie(s) détectée(s) dans les données. Vérifiez l'onglet 'Contrôle Qualité'.")
        
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        elite_mask = df['Statut'] == 'ELITE PRO'
        
        with c1:
            st.metric("Total Sujets", len(df))
        with c2:
            st.metric("Elite Pro", len(df[elite_mask]), 
                     f"{len(df[elite_mask])/len(df)*100:.1f}%")
        with c3:
            st.metric("Index Moyen", f"{df['Index'].mean():.1f}/100")
        with c4:
            st.metric("Anomalies", int(nb_anomalies), 
                     delta="Vérifier" if nb_anomalies > 0 else "OK", 
                     delta_color="inverse" if nb_anomalies > 0 else "normal")
        
        # Tableau avec coloration conditionnelle
        st.subheader("Classement officiel")
        
        # Formatage
        df_display = df[['Rang', 'Statut', 'id', 'race', 'p70', 'c_canon', 'Index', 'Appreciation', 'Alerte']].copy()
        df_display = df_display.sort_values('Rang')
        
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
        
        # Distribution
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(df, x='p70', y='Index', color='Statut', 
                           title='Sélection: Poids vs Index global',
                           hover_data=['id', 'Alerte'])
            # Ligne seuil absolu
            fig.add_hline(y=70, line_dash="dash", line_color="red", 
                         annotation_text="Seuil Elite")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig2 = px.histogram(df, x='Index', color='Anomalie', 
                              title="Distribution avec détection d'anomalies",
                              color_discrete_map={True: 'red', False: 'blue'})
            st.plotly_chart(fig2, use_container_width=True)
    
    # --- CONTRÔLE QUALITÉ ---
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Données")
        
        if df.empty:
            st.info("Pas de données")
            return
        
        # Filtre anomalies
        df_anomalies = df[df['Anomalie'] == True]
        
        if not df_anomalies.empty:
            st.error(f"⚠️ {len(df_anomalies)} mesures suspectes détectées")
            st.dataframe(df_anomalies[['id', 'p70', 'c_canon', 'h_garrot', 'Alerte']], 
                        use_container_width=True)
            st.info("💡 Ces animaux sont exclus de la sélection Elite jusqu'à correction")
        else:
            st.success("✅ Aucune anomalie détectée. Toutes les données sont cohérentes.")
        
        # Stats descriptives
        st.subheader("Statistiques du troupeau")
        st.dataframe(df[['p70', 'c_canon', 'h_garrot', 'GMQ', 'Index']].describe(), 
                    use_container_width=True)
    
    # --- SCANNER (inchangé) ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        img = st.camera_input("Photo de profil")
        
        if img:
            with st.spinner("Analyse..."):
                progress = st.progress(0)
                for i in range(100):
                    time.sleep(0.01)
                    progress.progress(i+1)
                
                # Génération réaliste
                base = random.uniform(70, 80)
                scan_data = {
                    'h_garrot': round(base, 1),
                    'c_canon': round(8 + random.random()*3, 1),
                    'l_poitrine': round(base*0.34, 1),
                    'p_thoracique': round(base*1.17, 1),
                    'l_corps': round(base*1.14, 1)
                }
                st.session_state['scan'] = scan_data
            
            col1, col2 = st.columns(2)
            with col1:
                st.image(img)
            with col2:
                st.success("Mesures détectées")
                for k, v in scan_data.items():
                    st.metric(k.replace('_', ' '), f"{v} cm")
                if st.button("→ Transférer"):
                    st.session_state['go_saisie'] = True
                    st.rerun()
    
    # --- SAISIE (inchangée) ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("Données scanner importées")
            st.session_state['go_saisie'] = False
        
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            with c1:
                id_animal = st.text_input("ID *", placeholder="REF-2024-001")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Babarine"])
            with c2:
                date_nais = st.date_input("Date naissance", datetime.now()-timedelta(days=100))
            
            st.subheader("Poids (obligatoires)")
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
                     ('l_poitrine', 'Larg.Poitrine'), ('p_thoracique', 'Périm.Thorax'), 
                     ('l_corps', 'Long.Corps')]
            
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    mens[key] = st.number_input(label, 0.0, 200.0, 
                                               float(scan.get(key, 0.0)), key=f"inp_{key}")
            
            if st.form_submit_button("💾 Enregistrer"):
                if not id_animal or p70 <= 0:
                    st.error("ID et Poids J70 obligatoires!")
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            c.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?)",
                                (id_animal, race, date_nais.strftime("%Y-%m-%d"), "Sélection", "2 Dents", datetime.now()))
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
