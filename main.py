import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import random
import plotly.express as px
from datetime import datetime, timedelta
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

# Style CSS optimisé
st.markdown("""
    <style>
    .stMetric { background-color: #111111; color: white; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    .alert-card { padding: 10px; background-color: #331a00; border-left: 5px solid #ff9900; color: #ffcc00; margin-bottom: 5px; border-radius: 5px; font-weight: bold; }
    /* Amélioration lisibilité du tableau */
    .stDataFrame { border: 1px solid #333; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ultra_final.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- 2. LOGIQUE MÉTIER EXPERTE ---
def estimer_age_dents(dentition):
    mapping = {
        "Dents de lait": "6-12 mois", "2 Dents": "14-22 mois",
        "4 Dents": "22-28 mois", "6 Dents": "28-36 mois",
        "8 Dents (Pleine)": "+36 mois"
    }
    return mapping.get(dentition, "Inconnu")

def calculer_metrics(row, mode="Viande"):
    # Sécurité : Vérification de la présence des données minimales
    if row['p70'] <= 0 or row['p30'] <= 0:
        return 0.0, 0.0, 0.0
    
    # GMQ 30-70 (Gain Moyen Quotidien en grammes)
    gmq = ((row['p70'] - row['p30']) / 40) * 1000
    
    # Rendement estimé (Formule zootechnique basée sur le thorax et la poitrine)
    # On sature les valeurs pour éviter des aberrations statistiques
    rendement = 52.4 + (0.35 * row['l_poitrine']) + (0.12 * row['p_thoracique']) - (0.08 * row['h_garrot'])
    rendement = max(min(rendement, 65.0), 40.0) # Limites physiologiques normales
    
    if mode == "Viande":
        # Index pondéré : Priorité au Rendement Carcasse (55%) et Poids Final (30%)
        index = (gmq * 0.15) + (rendement * 0.55) + (row['p70'] * 0.3)
    else:
        # Index Rusticité : Priorité au Canon (40%) et Hauteur (30%)
        index = (row['c_canon'] * 4.0) + (row['h_garrot'] * 0.3) + (gmq * 0.03)
        
    return round(gmq, 1), round(rendement, 1), round(index, 2)

# --- 3. INITIALISATION DB ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, objectif TEXT, dentition TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                  l_corps REAL, p_thoracique REAL, l_poitrine REAL, c_canon REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- 4. NAVIGATION & GESTION DES DONNÉES ---
st.sidebar.title("💎 Selector Ultra")

# Injection de données de test (Code optimisé)
if st.sidebar.button("🚀 GÉNÉRER 500 SUJETS (DÉMO)"):
    conn = get_db_connection()
    c = conn.cursor()
    # Utilisation d'un générateur pour la performance
    data_beliers = []
    data_mesures = []
    for i in range(500):
        a_id = f"REF-{3000 + i}"
        race = random.choice(["Ouled Djellal", "Rembi", "Hamra"])
        p10 = round(random.uniform(4.0, 5.5), 1)
        p30 = round(p10 + random.uniform(7, 9), 1)
        p70 = round(p30 + random.uniform(14, 17), 1)
        cc = round(8.5 + (p70 * 0.07) + random.uniform(-0.3, 0.3), 1) # Lien biologique canon/poids
        hg = round(68 + (p70 * 0.25), 1)
        data_beliers.append((a_id, race, "2024-06-01", "Viande", "Dents de lait"))
        data_mesures.append((a_id, p10, p30, p70, hg, 75.0, hg*1.2, 24.0, cc))
    
    c.executemany("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", data_beliers)
    c.executemany("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", data_mesures)
    conn.commit()
    st.sidebar.success("Base prête pour analyse !")
    st.rerun()

if st.sidebar.button("🗑️ VIDER LA BASE"):
    conn = get_db_connection(); conn.execute("DELETE FROM beliers"); conn.execute("DELETE FROM mesures"); conn.commit()
    st.sidebar.warning("Données effacées.")
    st.rerun()

obj_selection = st.sidebar.selectbox("🎯 Objectif de Sélection", ["Viande", "Rusticité"])
menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📈 Analyse Scientifique", "✍️ Saisie Manuelle", "📥 Import/Export"])

# Chargement intelligent des données
conn = get_db_connection()
df = pd.read_sql("SELECT * FROM beliers JOIN mesures ON beliers.id = mesures.id_animal", conn)
conn.close()

if not df.empty:
    # Calcul des metrics avec vecteur pandas pour la rapidité
    metrics = df.apply(lambda x: pd.Series(calculer_metrics(x, obj_selection)), axis=1)
    df[['GMQ', 'Rendement', 'Index']] = metrics

# --- 5. PAGES ---

if menu == "🏠 Dashboard":
    st.title("📊 Registre du Troupeau")
    if not df.empty:
        # Affichage du top classement
        st.subheader(f"Classement Élite ({obj_selection})")
        st.dataframe(df[['id', 'race', 'p70', 'c_canon', 'GMQ', 'Index']].sort_values('Index', ascending=False), use_container_width=True)
    else:
        st.info("Aucune donnée disponible. Commencez par la saisie ou la démo.")

elif menu == "📈 Analyse Scientifique":
    st.title("🔬 Laboratoire d'Analyse Biométrique")
    if not df.empty:
        # 1. Matrice de Corrélation
        cols_ana = ['p10', 'p30', 'p70', 'h_garrot', 'p_thoracique', 'c_canon', 'GMQ']
        st.subheader("🔗 Corrélation entre critères")
        fig_corr = px.imshow(df[cols_ana].corr(), text_auto=".2f", color_continuous_scale='Plasma')
        st.plotly_chart(fig_corr, use_container_width=True)
        
        

        # 2. Analyse des Impacts (Top 5)
        st.divider()
        st.subheader("🏆 Facteurs déterminants pour le Poids Final (J70)")
        corrs = df[cols_ana].corr()['p70'].abs().drop('p70').sort_values(ascending=False)
        rank_df = pd.DataFrame({"Paramètre": corrs.index, "Impact sur le Poids (%)": (corrs.values * 100).round(1)})
        
        c_tab, c_chart = st.columns([1, 2])
        c_tab.table(rank_df)
        c_chart.plotly_chart(px.bar(rank_df, x="Impact sur le Poids (%)", y="Paramètre", orientation='h', color="Impact sur le Poids (%)", color_continuous_scale='Greens'), use_container_width=True)

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie de Précision Terrain")
    
    
    
    with st.form("form_pro"):
        c1, c2 = st.columns(2)
        with c1:
            m_id = st.text_input("ID Boucle de l'animal")
            m_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
            meth_age = st.radio("Saisie de l'âge :", ["Date de naissance", "Dentition"])
            if meth_age == "Date de naissance":
                m_val = st.date_input("Date")
                m_dents = "Calendrier"
            else:
                m_dents = st.selectbox("Dents", ["Dents de lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
                m_val = f"Est. {estimer_age_dents(m_dents)}"
            
            st.divider()
            st.subheader("⚖️ Protocole de Pesée")
            p10 = st.number_input("Poids J10 (kg)", min_value=0.0)
            p30 = st.number_input("Poids J30 (kg)", min_value=0.0)
            p70 = st.number_input("Poids J70 (kg)", min_value=0.0)
            
        with c2:
            st.subheader("📏 Mensurations Morphologiques")
            hg = st.number_input("Hauteur Garrot (cm)", min_value=0.0)
            pt = st.number_input("Périmètre Thoracique (cm)", min_value=0.0)
            lp = st.number_input("Largeur Poitrine (cm)", min_value=0.0)
            lc = st.number_input("Longueur Corps (cm)", min_value=0.0)
            
            st.markdown("---")
            st.markdown("### 🦴 Mesure du Canon")
            
            cc = st.number_input("Circonférence Canon (cm)", help="Mesure précise de la charpente osseuse")

        if st.form_submit_button("💾 ENREGISTRER L'INDIVIDU"):
            if m_id:
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (m_id, m_race, str(m_val), obj_selection, m_dents))
                conn.execute("INSERT OR REPLACE INTO mesures VALUES (?,?,?,?,?,?,?,?,?)", (m_id, p10, p30, p70, hg, lc, pt, lp, cc))
                conn.commit()
                st.success(f"Animal {m_id} enregistré avec succès !")
                st.rerun()
            else:
                st.error("L'ID est obligatoire pour l'enregistrement.")

elif menu == "📥 Import/Export":
    st.title("📥 Gestion de la Base de Données")
    if not df.empty:
        output = io.BytesIO()
        df.to_excel(output, index=False)
        st.download_button("📥 Exporter le Troupeau vers Excel", data=output.getvalue(), file_name=f"selection_troupeau_{datetime.now().strftime('%Y%m%d')}.xlsx")
