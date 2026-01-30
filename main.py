import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from contextlib import contextmanager
import time

# ==========================================
# 1. CONFIGURATION & DESIGN AVANCÉ (CSS)
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v3", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    /* Cadres du Dashboard */
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        border-top: 6px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        margin-bottom: 15px;
    }
    .metric-card h2 { color: #2E7D32; font-size: 28px; margin: 5px 0; }
    .metric-card p { color: #555555; font-weight: 600; text-transform: uppercase; font-size: 13px; }
    
    /* Styles pour le mode sombre de Streamlit */
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .metric-card p { color: #BBB; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

# ==========================================
# 2. MOTEUR DE BASE DE DONNÉES
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
            id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

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

        # IC Borné (15 à 45)
        ic = max(15, min(45, (pt / (cc * hg)) * 1000))
        # Gras dorsal (2 à 22 mm)
        gras_mm = max(2.0, min(22.0, 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)))
        # Répartition Tissus
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = round(100.0 - pct_muscle - pct_gras, 1)

        if ic > 33: cl = "S"
        elif ic > 30: cl = "E"
        elif ic > 27: cl = "U"
        elif ic > 24: cl = "R"
        else: cl = "O/P"

        s90 = round((pct_muscle * 1.2) - (pct_gras * 0.5), 1)
        return round(pct_muscle, 1), round(pct_gras, 1), pct_os, round(gras_mm, 1), cl, s90, round(ic, 1)
    except:
        return 0, 0, 0, 0, "Erreur", 0, 0

@st.cache_data(ttl=2)
def load_data():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("""SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.p_thoracique, m.c_canon 
                               FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                               LEFT JOIN mesures m ON l.mid = m.id""", conn)
            if df.empty: return df
            for c in ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'c_canon']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
            df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'EUROP', 'S90', 'IC']] = res
            df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
            
            seuil = df['Index'].quantile(0.85) if len(df) >= 3 else 999
            df['Statut'] = np.where(df['Index'] >= seuil, "⭐ ELITE PRO", "Standard")
            return df
    except:
        return pd.DataFrame()

# ==========================================
# 4. INTERFACE UTILISATEUR (MENU COMPLET)
# ==========================================
def main():
    init_db()
    df = load_data()

    # --- BARRE LATÉRALE (RECHERCHE + MENU) ---
    st.sidebar.title("💎 Expert Selector")
    
    # Barre de recherche dynamique
    search_query = st.sidebar.text_input("🔍 Rechercher par ID", "").strip()
    
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navigation", [
        "🏠 Dashboard", "🥩 Composition", "🔍 Contrôle Qualité", 
        "📈 Stats & Analyse", "📸 Scanner", "✍️ Saisie", "🔧 Admin"
    ])

    # Filtrage en temps réel
    if search_query and not df.empty:
        df_display = df[df['id'].str.contains(search_query, case=False, na=False)]
    else:
        df_display = df

    # --- LOGIQUE DES ONGLETS ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if df.empty:
            st.info("Aucune donnée. Utilisez l'onglet 'Saisie' pour commencer.")
        else:
            # Cadres de statistiques (Visibles et contrastés)
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            with c2: st.markdown(f"<div class='metric-card'><p>Élites</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            with c3: st.markdown(f"<div class='metric-card'><p>Muscle Moy.</p><h2>{df['Pct_Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            with c4: st.markdown(f"<div class='metric-card'><p>Gras Moy.</p><h2>{df['Gras_mm'].mean():.1f} mm</h2></div>", unsafe_allow_html=True)

            st.subheader("📋 Classement Individuel")
            
            # Application du code couleur au tableau
            def color_statut(val):
                color = '#C8E6C9' if val == "⭐ ELITE PRO" else 'none'
                return f'background-color: {color}'

            st.dataframe(
                df_display[['id', 'race', 'p70', 'Pct_Muscle', 'Gras_mm', 'EUROP', 'Index', 'Statut']]
                .sort_values('Index', ascending=False)
                .style.applymap(color_statut, subset=['Statut']),
                use_container_width=True
            )

    elif menu == "🥩 Composition":
        st.title("🥩 Analyse de la Carcasse")
        if not df_display.empty:
            target = st.selectbox("Choisir un animal", df_display['id'].unique())
            row = df_display[df_display['id'] == target].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(names=['Muscle', 'Gras', 'Os'], 
                             values=[row['Pct_Muscle'], row['Pct_Gras'], row['Pct_Os']],
                             color_discrete_sequence=['#2E7D32', '#FFA000', '#BDBDBD'],
                             hole=0.4, title=f"Répartition tissus : {target}")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.metric("Classe EUROP", row['EUROP'])
                st.metric("Indice de Valeur (S90)", row['S90'])
                st.metric("Indice de Conformation (IC)", row['IC'])
        else:
            st.warning("Veuillez sélectionner ou enregistrer un animal.")

    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Fiche Animal")
        
        # Récupération des données du scanner si elles existent
        scan = st.session_state.get('scan', {})
        if st.session_state.get('go_saisie'):
            st.success("✨ Données du scanner importées avec succès !")
            st.session_state['go_saisie'] = False

        # Fonction interne pour l'estimation de l'âge (si pas définie ailleurs)
        def estimer_date(dent):
            mois = {"2 Dents": 15, "4 Dents": 21, "6 Dents": 27, "Pleine bouche": 36}
            nb_mois = mois.get(dent, 12)
            return datetime.now() - timedelta(days=nb_mois*30)

        with st.form("form_saisie", clear_on_submit=True):
            col_id1, col_id2 = st.columns(2)
            
            with col_id1:
                id_animal = st.text_input("ID de l'animal *", placeholder="Ex: OD-2024-001")
                race_options = ["Ouled Djellal", "Rembi", "Hamra", "Babarine", "Croisé", "Non identifiée"]
                race = st.selectbox("Race principale *", race_options)
                
                race_precision = st.text_input("Précision (si croisé)", placeholder="Ex: OD x Rembi") if race in ["Non identifiée", "Croisé"] else ""
            
            with col_id2:
                methode_age = st.radio("Détermination de l'âge", ["Date exacte", "Estimation par dentition"])
                date_naiss = datetime.now()
                date_estimee_flag = 0
                
                if methode_age == "Date exacte":
                    date_naiss = st.date_input("Date de naissance", datetime.now() - timedelta(days=100))
                    dentition = st.selectbox("État dentition", ["Agneau", "2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
                else:
                    dentition = st.selectbox("Observer la dentition *", ["2 Dents", "4 Dents", "6 Dents", "Pleine bouche"])
                    date_naiss = estimer_date(dentition)
                    date_estimee_flag = 1
                    st.caption(f"📅 Âge estimé : ~{date_naiss.strftime('%m/%Y')}")
                
                objectif = st.selectbox("Objectif final", ["Sélection (Elite)", "Engraissement", "Reproduction"])
            
            st.divider()
            st.subheader("⚖️ Poids (kg)")
            c1, c2, c3 = st.columns(3)
            with c1: p10 = st.number_input("Poids J10", 0.0, 30.0, 0.0)
            with c2: p30 = st.number_input("Poids J30", 0.0, 50.0, 0.0)
            with c3:
                label_p70 = "Poids ACTUEL *" if date_estimee_flag else "Poids J70 *"
                p70 = st.number_input(label_p70, 0.0, 150.0, 0.0)
            
            st.subheader("📏 Mensurations Morphologiques (cm)")
            st.info("💡 Ces mesures sont cruciales pour l'estimation du rendement en viande.")
            cols = st.columns(5)
            fields = [('h_garrot', 'Hauteur'), ('c_canon', 'Canon'), ('l_poitrine', 'Larg.Poitrine'), 
                     ('p_thoracique', 'Pér.Thorax'), ('l_corps', 'Long.Corps')]
            
            mens = {}
            for i, (key, label) in enumerate(fields):
                with cols[i]:
                    # On priorise la valeur du scan, sinon 0.0
                    default_val = float(scan.get(key, 0.0))
                    mens[key] = st.number_input(label, 0.0, 150.0, default_val)
            
            if st.form_submit_button("💾 ENREGISTRER L'ANIMAL", type="primary"):
                # VALIDATION STRICTE
                if not id_animal:
                    st.error("❌ L'identifiant est obligatoire.")
                elif p70 <= 5:
                    st.error("❌ Le poids actuel semble incorrect.")
                elif mens['c_canon'] <= 2 or mens['h_garrot'] <= 10:
                    st.error("❌ Les mensurations (Canon/Hauteur) sont obligatoires pour les calculs de viande.")
                else:
                    try:
                        with get_db_connection() as conn:
                            # 1. Table des béliers
                            conn.execute("""
                                INSERT OR REPLACE INTO beliers 
                                (id, race, race_precision, date_naiss, date_estimee, objectif, dentition)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (id_animal, race, race_precision, date_naiss.strftime("%Y-%m-%d"), 
                                  date_estimee_flag, objectif, dentition))
                            
                            # 2. Table des mesures
                            conn.execute("""
                                INSERT INTO mesures 
                                (id_animal, p10, p30, p70, h_garrot, l_corps, p_thoracique, l_poitrine, c_canon)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (id_animal, p10, p30, p70, mens['h_garrot'], 
                                  mens['l_corps'], mens['p_thoracique'], mens['l_poitrine'], mens['c_canon']))
                        
                        st.success(f"✅ Sujet {id_animal} enregistré avec succès !")
                        st.balloons()
                        # Nettoyage
                        if 'scan' in st.session_state: del st.session_state['scan']
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur base de données : {e}")

    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🗑️ Supprimer TOUTES les données"):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.warning("Base de données vidée."); st.rerun()
        
        st.download_button("📥 Exporter la base (CSV)", df.to_csv(index=False), "base_ovins.csv", "text/csv")

    else:
        st.title(f"Section {menu}")
        st.info("Cette section est prête à recevoir vos données spécifiques.")

if __name__ == "__main__":
    main()
