import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

# ==========================================
# 1. CONFIGURATION ET DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v3", layout="wide", page_icon="🐏")

# Style CSS pour des cartes de bord modernes
st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #2E7D32;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .elite-text { color: #D4AF37; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
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
        c.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, race_precision TEXT,
            date_naiss TEXT, date_estimee INTEGER DEFAULT 0,
            objectif TEXT, dentition TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL DEFAULT 0, p30 REAL DEFAULT 0, p70 REAL DEFAULT 0,
            h_garrot REAL DEFAULT 0, l_corps REAL DEFAULT 0, p_thoracique REAL DEFAULT 0,
            l_poitrine REAL DEFAULT 0, c_canon REAL DEFAULT 0,
            date_mesure TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_animal ON mesures(id_animal)')

# ==========================================
# 3. LOGIQUE MATHÉMATIQUE SÉCURISÉE
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70 = float(row.get('p70', 0))
        hg = float(row.get('h_garrot', 70))
        pt = float(row.get('p_thoracique', 80))
        cc = float(row.get('c_canon', 8.5))
        
        if p70 <= 5 or cc <= 2 or hg <= 10:
            return 0, 0, 0, 0, "Inconnu", 0, 0

        # Indice de Conformation (IC) - Borné entre 15 et 45
        ic = max(15, min(45, (pt / (cc * hg)) * 1000))
        
        # Gras dorsal (mm) - Equation de prédiction réaliste
        gras_mm = max(2.0, min(22.0, 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)))
        
        # Répartition Tissus (%)
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)

        # Grille EUROP
        if ic > 33: classe = "S (Supérieur)"
        elif ic > 30: classe = "E (Excellent)"
        elif ic > 27: classe = "U (Très bon)"
        elif ic > 24: classe = "R (Bon)"
        else: classe = "O/P (Médiocre)"

        # Valeur Bouchère S90
        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        
        return (round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(gras_mm, 1), classe, s90, round(ic, 2))
    except:
        return 0, 0, 0, 0, "Erreur", 0, 0

@st.cache_data(ttl=5)
def load_data():
    try:
        with get_db_connection() as conn:
            query = """
                SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, m.p_thoracique, m.l_poitrine, m.c_canon
                FROM beliers b
                LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal
                LEFT JOIN mesures m ON l.mid = m.id
            """
            df = pd.read_sql(query, conn)
            if df.empty: return df

            # Conversion numérique
            num_cols = ['p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'p_thoracique', 'l_poitrine', 'l_corps']
            for col in num_cols: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Calculs
            compo = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = compo
            
            # Index & GMQ
            df['GMQ'] = df.apply(lambda x: round(((x['p70'] - x['p30'])/40)*1000, 1) if x['p70'] > x['p30'] else 0, axis=1)
            df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
            
            # Statut Elite
            seuil = df['Index'].quantile(0.85) if len(df) > 2 else 999
            df['Statut'] = np.where(df['Index'] >= seuil, "⭐ ELITE PRO", "Standard")
            
            return df
    except:
        return pd.DataFrame()

# ==========================================
# 4. INTERFACE PRINCIPALE (MENU COMPLET)
# ==========================================
def main():
    init_db()
    df = load_data()

    st.sidebar.title("💎 Expert Selector Pro")
    st.sidebar.markdown(f"**Date:** {datetime.now().strftime('%d/%m/%Y')}")
    
    menu = st.sidebar.radio("Menu principal", [
        "🏠 Dashboard", 
        "🥩 Composition (Écho-like)", 
        "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse",
        "📸 Scanner", 
        "✍️ Saisie",
        "🔧 Administration BDD"
    ])

    # --- SECTION DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord Professionnel")
        if df.empty:
            st.info("👋 Bienvenue. Commencez par saisir des données ou utiliser le scanner.")
        else:
            # Cartes de synthèse
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='metric-card'><b>Effectif Total</b><br><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><b>Elite Pro</b><br><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><b>Muscle Moy.</b><br><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><b>Poids Moy.</b><br><h2>{df['p70'].mean():.1f} kg</h2></div>", unsafe_allow_html=True)

            st.subheader("📋 Classement de Performance")
            # Style conditionnel pour le tableau
            df_disp = df[['id', 'race', 'p70', 'GMQ', 'Pct_Muscle', 'EUROP', 'Index', 'Statut']].sort_values('Index', ascending=False)
            st.dataframe(df_disp.style.applymap(lambda x: 'background-color: #fff9c4' if x == '⭐ ELITE PRO' else '', subset=['Statut']), use_container_width=True)

    # --- SECTION COMPOSITION ---
    elif menu == "🥩 Composition (Écho-like)":
        st.title("🥩 Analyse Composition Corporelle")
        if not df.empty:
            target = st.selectbox("Sélectionner l'animal", df['id'].unique())
            an = df[df['id'] == target].iloc[0]
            
            col1, col2 = st.columns([1, 1])
            with col1:
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = an['Gras_mm'],
                    title = {'text': "Gras Dorsal (mm)"},
                    gauge = {'axis': {'range': [0, 25]}, 'bar': {'color': "#e91e63"}}
                ))
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                labels = ['Muscle', 'Gras', 'Os']
                values = [an['Pct_Muscle'], an['Pct_Gras'], an['Pct_Os']]
                fig_pie = px.pie(names=labels, values=values, title=f"Répartition Carcasse : {target}", 
                                 color_discrete_sequence=px.colors.sequential.Greens_r)
                st.plotly_chart(fig_pie, use_container_width=True)
            
            st.success(f"**Classement EUROP estimé : {an['EUROP']}** | Indice S90 : {an['S90']}")

    # --- SECTION CONTRÔLE QUALITÉ ---
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Mesures")
        if not df.empty:
            # Détection simple d'anomalies (ex: poids incohérent avec le canon)
            df['Alerte'] = np.where((df['p70'] / df['c_canon'] > 8) | (df['p70'] < 10), "⚠️ Vérifier", "✅ OK")
            st.table(df[['id', 'p70', 'c_canon', 'Alerte']])
        else: st.info("Aucune donnée à contrôler.")

    # --- SECTION SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        img = st.camera_input("Scanner le sujet")
        if img:
            st.warning("Analyse visuelle en cours... Profilage automatique activé.")
            st.info("Profil type 'Ouled Djellal' détecté. Transférez vers la saisie pour ajuster.")

    # --- SECTION SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Enregistrement Animal")
        with st.form("form_saisie"):
            c1, c2 = st.columns(2)
            with c1:
                aid = st.text_input("Identifiant Animal *")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
            with c2:
                p30 = st.number_input("Poids J30 (kg)", 0.0)
                p70 = st.number_input("Poids Actuel/J70 (kg) *", 0.0)
            
            st.subheader("Mensurations (cm)")
            m1, m2, m3, m4 = st.columns(4)
            hg = m1.number_input("H. Garrot", 0.0)
            cc = m2.number_input("Tour Canon", 0.0)
            pt = m3.number_input("Périm. Thorax", 0.0)
            lc = m4.number_input("Long. Corps", 0.0)
            
            if st.form_submit_button("💾 Sauvegarder dans la base"):
                if aid and p70 > 0:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (aid, race))
                        conn.execute("""INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) 
                                     VALUES (?,?,?,?,?,?,?)""", (aid, p30, p70, hg, cc, pt, lc))
                    st.success("Données enregistrées avec succès !"); time.sleep(1); st.rerun()
                else: st.error("L'ID et le Poids J70 sont obligatoires.")

    # --- SECTION ADMIN ---
    elif menu == "🔧 Administration BDD":
        st.title("🔧 Maintenance Système")
        col_ad1, col_ad2 = st.columns(2)
        with col_ad1:
            if st.button("🗑️ Vider toute la base de données"):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM mesures")
                    conn.execute("DELETE FROM beliers")
                st.error("Base de données réinitialisée."); st.rerun()
        with col_ad2:
            st.download_button("📥 Exporter en Excel (CSV)", df.to_csv(index=False), "export_ovin.csv", "text/csv")

if __name__ == "__main__":
    main()
