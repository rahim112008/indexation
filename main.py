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
# INITIALISATION & BD
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")
DB_NAME = "expert_ovin_pro.db"

@contextmanager
def get_db_connection():
    # Ajout du journal_mode pour éviter les blocages de lecture/écriture simultanés
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL") 
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur DB : {e}")
        raise e
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, race_precision TEXT,
            date_naiss TEXT, date_estimee INTEGER DEFAULT 0,
            objectif TEXT, dentition TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Vérification des colonnes pour les mises à jour de structure
        cursor = conn.execute("PRAGMA table_info(beliers)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'race_precision' not in columns:
            conn.execute("ALTER TABLE beliers ADD COLUMN race_precision TEXT")
        if 'date_estimee' not in columns:
            conn.execute("ALTER TABLE beliers ADD COLUMN date_estimee INTEGER DEFAULT 0")

        c.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL DEFAULT 0, p30 REAL DEFAULT 0, p70 REAL DEFAULT 0,
            h_garrot REAL DEFAULT 0, l_corps REAL DEFAULT 0, p_thoracique REAL DEFAULT 0,
            l_poitrine REAL DEFAULT 0, c_canon REAL DEFAULT 0,
            date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_animal ON mesures(id_animal)')

# ==========================================
# UTILITAIRES & LOGIQUE AVANCÉE
# ==========================================
def safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val): return default
        return float(val)
    except: return default

def calculer_composition_carcasse(row):
    """Calcule la morphologie écho-like avec protections robustes"""
    try:
        p70 = safe_float(row.get('p70'), 0)
        hg = safe_float(row.get('h_garrot'), 70)
        pt = safe_float(row.get('p_thoracique'), 80)
        cc = safe_float(row.get('c_canon'), 8.5)
        lc = safe_float(row.get('l_corps'), 80)
        lp = safe_float(row.get('l_poitrine'), 24)
        
        if p70 <= 0 or cc <= 0 or pt <= 0 or hg <= 0:
            return 0, 0, 0, 0, 0, "Inconnu", 0, 0
        
        # Indice Conformation (Morphométrie)
        IC = (pt / (cc * hg)) * 1000
        surface_laterale = max(1, lc * lp)
        indice_eng = p70 / surface_laterale
        
        gras_mm = max(2.0, min(25.0, 2.5 + (indice_eng * 8.5) + (p70 * 0.05) - (IC * 0.02)))
        smld_cm2 = max(10, min(30, (pt * lc * 0.12) - (gras_mm * 1.5)))
        
        # Estimation distribution carcasse
        pct_muscle = max(40, min(75, 55 + (IC * 0.2) - (gras_mm * 0.5)))
        pct_gras = max(10, min(45, (gras_mm * 1.8) + (p70 * 0.1)))
        pct_os = 100 - pct_muscle - pct_gras
        
        # Grille EUROP Simplifiée
        if IC > 32 and gras_mm < 10: classe = "S (Supérieur)"
        elif IC > 29: classe = "E (Excellent)"
        elif IC > 26: classe = "U (Très bon)"
        elif IC > 23: classe = "R (Bon)"
        else: classe = "O (Ordinaire)"
        
        indice_s90 = round(pct_muscle * (1 - (pct_gras/200)), 1)
        return round(pct_muscle, 1), round(pct_gras, 1), round(pct_os, 1), round(gras_mm, 1), round(smld_cm2, 1), classe, indice_s90, round(IC, 2)
    except:
        return 0, 0, 0, 0, 0, "Erreur", 0, 0

def calculer_metrics_pro(row):
    try:
        p70, p30 = safe_float(row.get('p70')), safe_float(row.get('p30'))
        hg = safe_float(row.get('h_garrot'), 1)
        
        if p70 <= 0 or p30 <= 0 or p30 >= p70:
            return 0.0, 0.0, 0.0, "Données insuffisantes"
        
        gmq = ((p70 - p30) / 40) * 1000
        rendement = 52.4 + (0.35 * safe_float(row.get('l_poitrine'))) + (0.12 * safe_float(row.get('p_thoracique'))) - (0.08 * hg)
        rendement = max(40.0, min(65.0, rendement))
        
        # Index global pro
        index_final = (gmq * 0.1) + (rendement * 0.5) + (p70 * 0.2) + (safe_float(row.get('c_canon')) * 2.0)
        
        app = "Excellence" if index_final > 80 else "Standard"
        return round(gmq, 1), round(rendement, 1), round(index_final, 1), app
    except:
        return 0.0, 0.0, 0.0, "Erreur"

# ==========================================
# INTERFACE (DASHBOARD & LOGIQUE)
# ==========================================
def load_data():
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, m.p_thoracique, m.l_poitrine, m.c_canon 
                   FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal
                   LEFT JOIN mesures m ON l.mid = m.id"""
        df = pd.read_sql(query, conn)
        if df.empty: return df
        
        # Application des calculs en cascade
        compo = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
        df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'SMLD', 'Classe_EUROP', 'Indice_S90', 'IC']] = compo
        
        metrics = df.apply(lambda x: pd.Series(calculer_metrics_pro(x)), axis=1)
        df[['GMQ', 'Rendement', 'Index', 'Appreciation']] = metrics
        
        # Elite calculation
        seuil = df['Index'].quantile(SEUILS_PRO['percentile_elite']) if len(df) > 2 else 999
        df['Statut'] = np.where((df['Index'] >= seuil) & (df['p70'] >= SEUILS_PRO['p70_absolu']), "ELITE PRO", "")
        return df

def main():
    init_db()
    df = load_data()
    
    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Menu", ["🏠 Dashboard", "🥩 Composition", "📈 Analyse", "📸 Scanner", "✍️ Saisie"])
    
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Troupeau", len(df))
            c2.metric("Elite", len(df[df['Statut'] == "ELITE PRO"]))
            c3.metric("Muscle Moy.", f"{df['Pct_Muscle'].mean():.1f}%")
            c4.metric("Gras Moy.", f"{df['Gras_mm'].mean():.1f}mm")
            
            # Tableau stylisé
            st.subheader("Performance Individuelle")
            df_view = df[['id', 'race', 'p70', 'Pct_Muscle', 'Gras_mm', 'Classe_EUROP', 'Index', 'Statut']].sort_values('Index', ascending=False)
            st.dataframe(df_view.style.highlight_max(axis=0, subset=['Index']), use_container_width=True)
        else:
            st.info("Base vide. Veuillez saisir des données.")

    elif menu == "🥩 Composition":
        st.title("🥩 Analyse Carcasse Estimée")
        if not df.empty:
            target = st.selectbox("Choisir un sujet", df['id'].unique())
            an = df[df['id'] == target].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                # Radar Chart de conformation
                categories = ['Muscle %', 'Rendement', 'Indice S90', 'Conformation']
                fig = go.Figure(data=go.Scatterpolar(
                    r=[an['Pct_Muscle'], an['Rendement'], an['Indice_S90'], an['IC']],
                    theta=categories, fill='toself'
                ))
                st.plotly_chart(fig)
            with col2:
                st.metric("Classe EUROP", an['Classe_EUROP'])
                st.metric("Épaisseur Gras", f"{an['Gras_mm']} mm")
                st.progress(int(an['Pct_Muscle']))
                st.write(f"Muscle : {an['Pct_Muscle']}%")

    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        with st.form("saisie_pro"):
            col1, col2 = st.columns(2)
            with col1:
                id_a = st.text_input("ID Animal *")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
            with col2:
                p30 = st.number_input("Poids J30", 0.0)
                p70 = st.number_input("Poids J70 / Actuel *", 0.0)
            
            st.subheader("Biométrie (cm)")
            m1, m2, m3, m4, m5 = st.columns(5)
            hg = m1.number_input("Hauteur", 0.0)
            cc = m2.number_input("Canon", 0.0)
            lp = m3.number_input("Largeur Poit.", 0.0)
            pt = m4.number_input("Périm. Thorax", 0.0)
            lc = m5.number_input("Long. Corps", 0.0)
            
            if st.form_submit_button("💾 Enregistrer"):
                if id_a and p70 > 0:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_a, race))
                        conn.execute("""INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, l_corps) 
                                     VALUES (?,?,?,?,?,?,?,?)""", (id_a, p30, p70, hg, cc, lp, pt, lc))
                    st.success("Enregistré !"); st.rerun()

    # Les sections Scanner et Stats peuvent être reprises de votre code initial sans problème.

if __name__ == "__main__":
    main()
    
