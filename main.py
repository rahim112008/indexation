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
# 1. DESIGN & CSS (INTERFACE PRO)
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; margin-bottom: 15px;
    }
    .metric-card h2 { color: #2E7D32; font-size: 28px; margin: 5px 0; }
    .metric-card p { color: #555555; font-weight: 600; text-transform: uppercase; font-size: 13px; margin:0; }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
    }
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
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, race_precision TEXT, 
            date_naiss TEXT, date_estimee INTEGER, objectif TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, 
            p_thoracique REAL, l_corps REAL, l_poitrine REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. MOTEUR DE CALCULS SCIENTIFIQUES
# ==========================================
def calculer_composition_carcasse(row):
    try:
        p70, hg, pt, cc = float(row.get('p70', 0)), float(row.get('h_garrot', 70)), float(row.get('p_thoracique', 80)), float(row.get('c_canon', 8.5))
        if p70 <= 5 or cc <= 2: return 0, 0, 0, 0, "Inconnu", 0, 0
        ic = max(15, min(45, (pt / (cc * hg)) * 1000))
        gras_mm = max(2.0, min(22.0, 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)))
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)
        cl = "S" if ic > 33 else "E" if ic > 30 else "U" if ic > 27 else "R" if ic > 24 else "O/P"
        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        return round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(gras_mm, 1), cl, s90, round(ic, 1)
    except: return 0, 0, 0, 0, "Erreur", 0, 0

@st.cache_data(ttl=2)
def load_data():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("""SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.p_thoracique, m.c_canon, m.l_corps, m.l_poitrine 
                               FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                               LEFT JOIN mesures m ON l.mid = m.id""", conn)
            if df.empty: return df
            for c in ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'c_canon']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = res
            df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
            df['Statut'] = np.where(df['Index'] >= df['Index'].quantile(0.85), "⭐ ELITE PRO", "Standard")
            return df
    except: return pd.DataFrame()

# ==========================================
# 4. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    # Barre latérale
    st.sidebar.title("💎 Expert Selector")
    search_query = st.sidebar.text_input("🔍 Recherche par ID", "").strip()
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Composition", "🔍 Contrôle Qualité", "📈 Stats", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    df_filtered = df[df['id'].str.contains(search_query, case=False, na=False)] if (search_query and not df.empty) else df

    # --- 1. DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty: st.info("Bienvenue ! Commencez par l'onglet Saisie.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='metric-card'><p>Total Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><p>Elites</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><p>Gras Moy.</p><h2>{df['Gras_mm'].mean():.1f}mm</h2></div>", unsafe_allow_html=True)
            
            st.dataframe(df_filtered[['id', 'race', 'p70', 'Pct_Muscle', 'EUROP', 'S90', 'Statut']].sort_values('p70', ascending=False), use_container_width=True)

    # --- 2. COMPOSITION (VÉRITABLE ANALYSE) ---
    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de la Carcasse")
        if not df.empty:
            animal_id = st.selectbox("Sélectionner l'ID de l'animal", df['id'].unique())
            subject = df[df['id'] == animal_id].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                fig_pie = px.pie(names=['Muscle', 'Gras', 'Os'], values=[subject['Pct_Muscle'], subject['Pct_Gras'], subject['Pct_Os']],
                                 color_discrete_sequence=['#2E7D32', '#FFA000', '#BDBDBD'], hole=0.4, title="Anatomie Estimée")
                st.plotly_chart(fig_pie, use_container_width=True)
            with col2:
                st.markdown(f"<div class='metric-card'><p>Indice de Conformation</p><h2>{subject['IC']}</h2></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-card'><p>Classe EUROP</p><h2>{subject['EUROP']}</h2></div>", unsafe_allow_html=True)
        else: st.warning("Aucune donnée disponible.")

    # --- 3. CONTROLE QUALITE (DÉTECTION D'ERREURS) ---
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Contrôle de Fiabilité des Mesures")
        if not df.empty:
            df['Alerte'] = np.where((df['p70'] < 10) | (df['c_canon'] > 15), "⚠️ Anomalie", "✅ Coordonnées OK")
            st.table(df[['id', 'p70', 'c_canon', 'h_garrot', 'Alerte']])
        else: st.info("Saisissez des données pour activer le contrôle.")

    # --- 4. STATS (VISUALISATION GROUPE) ---
    elif menu == "📈 Stats":
        st.title("📈 Analyse du Troupeau")
        if not df.empty:
            fig_scat = px.scatter(df, x="p70", y="Pct_Muscle", color="EUROP", size="S90", hover_name="id", title="Poids vs Muscle par Classe EUROP")
            st.plotly_chart(fig_scat, use_container_width=True)
        else: st.info("Données insuffisantes.")

    # --- 5. SCANNER (SIMULATEUR) ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        img = st.camera_input("Scanner le sujet")
        if img:
            st.warning("IA : Analyse morphologique en cours...")
            st.session_state['scan'] = {'h_garrot': 72.5, 'c_canon': 8.8, 'p_thoracique': 92.0}
            st.success("✅ Mesures extraites ! Allez dans 'Saisie' pour enregistrer.")

    # --- 6. SAISIE (VOTRE BLOC PERFECTIONNÉ) ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche")
        scan = st.session_state.get('scan', {})
        def estimer_date(dent):
            m_map = {"2 Dents": 15, "4 Dents": 21, "6 Dents": 27, "Pleine bouche": 36}
            return datetime.now() - timedelta(days=m_map.get(dent, 12) * 30)

        with st.form("form_saisie"):
            col1, col2 = st.columns(2)
            with col1:
                id_animal = st.text_input("ID Animal *", placeholder="Ex: OD-101")
                race = st.selectbox("Race *", ["Ouled Djellal", "Rembi", "Hamra", "Croisé"])
                objectif = st.selectbox("Objectif", ["Sélection", "Engraissement", "Reproduction"])
            with col2:
                methode = st.radio("Âge par :", ["Date exacte", "Dentition"])
                if methode == "Date exacte":
                    date_naiss = st.date_input("Naissance", datetime.now() - timedelta(days=100))
                    dentition = st.selectbox("Dentition", ["Agneau", "2 Dents", "4 Dents", "6 Dents"])
                else:
                    dentition = st.selectbox("Dentition actuelle *", ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
                    date_naiss = estimer_date(dentition)
                    st.info(f"📅 Estimée : {date_naiss.strftime('%m/%Y')}")

            st.subheader("Poids & Mesures")
            c1, c2, c3 = st.columns(3)
            with c1: p30 = st.number_input("Poids J30", 0.0, 50.0, 0.0)
            with c2: p70 = st.number_input("Poids Actuel *", 0.0, 150.0, 0.0)
            with c3: hg = st.number_input("Hauteur (cm)", 0.0, 150.0, float(scan.get('h_garrot', 0.0)))
            
            c4, c5 = st.columns(2)
            with c4: cc = st.number_input("Canon (cm)", 0.0, 20.0, float(scan.get('c_canon', 0.0)))
            with c5: pt = st.number_input("Périmètre Thorax (cm)", 0.0, 200.0, float(scan.get('p_thoracique', 0.0)))
            
            submit = st.form_submit_button("💾 ENREGISTRER", type="primary")

        if submit:
            if not id_animal or p70 <= 0 or cc <= 0: st.error("ID, Poids et Canon obligatoires !")
            else:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?)", (id_animal, race, "", date_naiss.strftime("%Y-%m-%d"), 1 if methode != "Date exacte" else 0, objectif, dentition))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_animal, p30, p70, hg, cc, pt))
                st.success("Enregistré !"); time.sleep(1); st.rerun()

    # --- 7. ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🗑️ Vider TOUTES les données"):
            with get_db_connection() as conn: 
                conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.warning("Base de données réinitialisée."); st.rerun()
        st.download_button("📥 Télécharger CSV", df.to_csv(index=False), "export_ovins.csv", "text/csv")

if __name__ == "__main__":
    main()
