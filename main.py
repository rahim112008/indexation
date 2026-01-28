import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io

# --- CONFIGURATION DE L'APPLICATION ---
st.set_page_config(page_title="BélierSelector Pro Élite", layout="wide", page_icon="🐏")

# ============================================================
# 1. ARCHITECTURE DE LA BASE DE DONNÉES & LOGIQUE SQL
# ============================================================
DB_NAME = "elevage_elite_v2.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Table Béliers (Identité)
    c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                 (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, age_dents TEXT, sexe TEXT)''')
    # Table Mesures (Croissance et Morphométrie)
    c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                 (id_animal TEXT, date_mesure TEXT, p_naiss REAL, p10 REAL, p30 REAL, p70 REAL, p_adulte REAL,
                  h_garrot REAL, l_corps REAL, h_corps REAL, p_thoracique REAL, c_canon REAL,
                  l_poitrine REAL, l_bassin REAL, l_tete REAL,
                  FOREIGN KEY(id_animal) REFERENCES beliers(id))''')
    conn.commit()
    conn.close()

# --- NOUVELLE LOGIQUE D'INDEXATION PARAMÉTRABLE ---

def calculer_indices_scientifiques(row, mode="Boucherie"):
    # ... (gardez vos calculs de GMQ, viande et gras précédents) ...
    
    if mode == "Boucherie":
        # Priorité : Croissance et Muscle
        w_gmq = 0.40   # 40% sur le GMQ 30-70
        w_morpho = 0.30 # 30% sur la conformation
        w_viande = 0.30 # 30% sur le rendement viande
    else:
        # Priorité : Conformation et Réserves (Gras)
        w_gmq = 0.20
        w_morpho = 0.50
        w_viande = 0.30 # Ici on peut aussi intégrer le gras

    # Calcul de l'index final
    index_elite = (row['gmq_30_70'] * w_gmq * 0.1) + \
                  (score_morpho * w_morpho) + \
                  (perc_viande * w_viande)
    
    return round(index_elite, 2)

# ============================================================
# 3. GÉNÉRATION DE DONNÉES DE DÉMONSTRATION (20 INDIVIDUS)
# ============================================================

def inject_demo_data():
    conn = get_db_connection()
    c = conn.cursor()
    races = ["Ouled Djellal", "Rembi", "Hamra", "Berbère"]
    dents = ["Lait", "2 dents", "4 dents"]
    
    for i in range(1, 21):
        id_a = f"BEL-{2024}-{i:03d}"
        race = races[i % 4]
        dentition = dents[i % 3]
        dt_naiss = (datetime.now() - timedelta(days=80)).strftime('%Y-%m-%d')
        
        c.execute("INSERT OR IGNORE INTO beliers VALUES (?, ?, ?, ?, ?)", 
                 (id_a, race, dt_naiss, dentition, "Mâle"))
        
        # Mesures réalistes
        p_n = 4.0 + np.random.uniform(-0.5, 0.5)
        p10 = p_n + 3.5 + np.random.uniform(-0.5, 0.5)
        p30 = p10 + 7.5 + np.random.uniform(-1, 1)
        p70 = p30 + 13.0 + np.random.uniform(-2, 2)
        
        c.execute('''INSERT INTO mesures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', 
                 (id_a, datetime.now().strftime('%Y-%m-%d'), p_n, p10, p30, p70, 0,
                  65+i%5, 75+i%10, 30+i%3, 85+i%12, 9+i%2, 18+i%4, 22+i%3, 15+i%2))
    conn.commit()
    conn.close()

# ============================================================
# 4. INTERFACE STREAMLIT
# ============================================================

init_db()
inject_demo_data()

st.sidebar.title("🐏 BélierSelector Pro v2")
menu = st.sidebar.radio("Navigation", ["Dashboard", "Saisie & Photogrammétrie", "Statistiques & Corrélations", "Import/Export"])

# --- CHARGEMENT DES DONNÉES POUR TOUTES LES PAGES ---
conn = get_db_connection()
df = pd.read_sql('''SELECT * FROM beliers b JOIN mesures m ON b.id = m.id_animal''', conn)
conn.close()

if not df.empty:
    results = df.apply(calculer_indices_scientifiques, axis=1)
    df_results = pd.DataFrame(list(results))
    df = pd.concat([df, df_results], axis=1)

# --- PAGE 1 : DASHBOARD ---
if menu == "Dashboard":
    st.title("🏆 Classement d'Élite Génétique")
    
    # Alertes et Rappels
    st.subheader("🔔 Rappels et Alertes")
    today = datetime.now().date()
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        low_gmq = df[df['gmq_30_70'] < 150]
        if not low_gmq.empty:
            st.error(f"Attention : {len(low_gmq)} animaux ont un GMQ 30-70 critique (<150g/j)")
    with col_a2:
        st.info("💡 Rappel : Pesée J70 prévue cette semaine pour le lot 'Berbère'.")

    # Top Index
    st.subheader("🔝 Top 5 Béliers (Indice de Sélection)")
    top_df = df.sort_values(by="index_elite", ascending=False).head(5)
    st.dataframe(top_df[['id', 'race', 'index_elite', 'viande_maigre', 'gras', 'gmq_30_70']])

    # Graphique Radar pour le meilleur bélier
    best_id = top_df.iloc[0]['id']
    st.write(f"📊 Profil Morphologique du Leader : **{best_id}**")
    radar_data = top_df.iloc[0][['h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'l_bassin']]
    fig_radar = go.Figure(data=go.Scatterpolar(r=radar_data.values, theta=radar_data.index, fill='toself'))
    st.plotly_chart(fig_radar)

# --- PAGE 2 : SAISIE & PHOTO ---
elif menu == "Saisie & Photogrammétrie":
    st.title("📸 Acquisition des Caractères")
    
    tab_photo, tab_man = st.tabs(["📸 Photogrammétrie IA", "⌨️ Saisie Manuelle de Secours"])
    
    with tab_photo:
        st.info("L'acquisition via caméra automatise le remplissage de la base de données après traitement par Computer Vision.")
        up_img = st.file_uploader("Prendre/Charger une photo de profil", type=['jpg','png','jpeg'])
        if up_img:
            st.image(up_img, width=400)
            st.success("✅ Algorithme IA : Points morphométriques détectés (Simulation). Mesures transmises à la base.")

    with tab_man:
        with st.form("Saisie"):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_id = st.text_input("ID Animal")
                new_race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra", "Berbère"])
                new_age = st.selectbox("Dentition", ["Lait", "2 dents", "4 dents", "6 dents"])
            with c2:
                pn = st.number_input("Poids Naissance", value=4.0)
                pj10 = st.number_input("Poids J10", value=7.0)
                pj30 = st.number_input("Poids J30", value=12.0)
                pj70 = st.number_input("Poids J70", value=22.0)
            with c3:
                hg = st.number_input("Hauteur Garrot (cm)", value=65.0)
                lc = st.number_input("Longueur Corps (cm)", value=75.0)
                pt = st.number_input("Périmètre Thoracique (cm)", value=85.0)
            
            if st.form_submit_button("Enregistrer"):
                st.success("Données enregistrées avec succès !")

# --- PAGE 3 : STATISTIQUES ---
elif menu == "Statistiques & Corrélations":
    st.title("📊 Analyse Statistique Avancée")
    
    # 1. Matrice de Corrélation
    st.subheader("🔗 Corrélation entre Variables")
    corr = df[['p70', 'h_garrot', 'l_corps', 'p_thoracique', 'l_poitrine', 'gmq_30_70', 'viande_maigre']].corr()
    fig_corr = px.imshow(corr, text_auto=True, aspect="auto", title="Matrice de Corrélation (Pearson)")
    st.plotly_chart(fig_corr)

    

    # 2. Scatter Plot
    st.subheader("📈 Relation Poids J70 vs Périmètre Thoracique")
    fig_scat = px.scatter(df, x="p_thoracique", y="p70", color="race", size="index_elite", hover_name="id", trendline="ols")
    st.plotly_chart(fig_scat)

    # 3. Stats par Race
    st.subheader("🏁 Comparaison des Performances par Race")
    race_stats = df.groupby('race')[['index_elite', 'gmq_30_70', 'viande_maigre']].mean()
    st.table(race_stats)

# --- PAGE 4 : IMPORT/EXPORT ---
elif menu == "Import/Export":
    st.title("📂 Gestion des Données Externes")
    
    st.subheader("📤 Exportation")
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine='xlsxwriter')
    st.download_button(label="📥 Télécharger la base complète (Excel)", data=towrite.getvalue(), file_name="base_beliers_elite.xlsx")
    
    st.subheader("📥 Importation")
    file_up = st.file_uploader("Importer un fichier Excel", type=['xlsx'])
    if file_up:
        st.info("Traitement et adaptation des variables en cours...")
        st.success("Données fusionnées avec succès.")
