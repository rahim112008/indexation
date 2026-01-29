import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import io
from datetime import datetime
from contextlib import contextmanager

# --- CONFIGURATION ---
st.set_page_config(page_title="Expert Selector", layout="wide", page_icon="💎")

# Changement de nom pour corriger l'erreur de colonne manquante vue sur votre capture
DB_NAME = "expert_ovin_v5.db"

# --- BASE DE DONNÉES ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS beliers 
                    (id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mesures 
                    (id_animal TEXT, p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, 
                     c_canon REAL, l_poitrine REAL, p_thoracique REAL, l_corps REAL, date_mesure TEXT)''')
init_db()

# --- CHARGEMENT ---
def load_data():
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.c_canon, m.l_poitrine, m.p_thoracique, m.l_corps 
                   FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal"""
        return pd.read_sql(query, conn)

# --- INTERFACE ---
st.sidebar.title("💎 Expert Selector")
st.sidebar.write("Sélection Zootechnique IA")
if st.sidebar.button("🚀 Générer 50 sujets démo"):
    # Logique de démo ici
    st.rerun()

menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie Manuelle", "📥 Import/Export"])

df = load_data()

if menu == "🏠 Dashboard":
    st.title("🏆 Tableau de Bord du Troupeau")
    st.dataframe(df, use_container_width=True)

elif menu == "✍️ Saisie Manuelle":
    st.title("✍️ Saisie des données")
    
    # --- BLOC 1 : IDENTIFICATION ---
    st.subheader("Identification")
    id_animal = st.text_input("ID Animal (Boucle)")
    
    # --- BLOC 2 : POIDS (Design Capture 110) ---
    st.subheader("Poids de croissance")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1: p10 = st.number_input("Poids J10 (kg)", 0.0)
    with col_p2: p30 = st.number_input("Poids J30 (kg)", 0.0)
    with col_p3: p70 = st.number_input("Poids J70 (kg) *", 0.0)

    # --- BLOC 3 : MENSURATIONS (Design Capture 110) ---
    st.subheader("Mensurations (cm) - Scannées ou manuelles")
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1: hg = st.number_input("Hauteur Garrot", 0.0)
    with col_m2: can = st.number_input("Canon", 0.0)
    with col_m3: lp = st.number_input("Larg. Poitrine", 0.0)
    with col_m4: pt = st.number_input("Périm. Thorax", 0.0)
    with col_m5: lc = st.number_input("Long. Corps", 0.0)

    if st.button("💾 Enregistrer", type="primary"):
        if id_animal:
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_animal, "Rembi"))
                conn.execute("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, l_corps, date_mesure) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (id_animal, p10, p30, p70, hg, can, lp, pt, lc, datetime.now().strftime("%Y-%m-%d")))
            st.success("Données enregistrées !")
            st.rerun()
        else:
            st.error("Veuillez entrer un ID Animal.")

elif menu == "📥 Import/Export":
    st.title("📥 Échange de Données")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📤 Exporter")
        # Modèle Excel pour les autres
        mod_df = pd.DataFrame(columns=['id', 'race', 'p10', 'p30', 'p70', 'h_garrot', 'c_canon', 'l_poitrine', 'p_thoracique', 'l_corps'])
        buf = io.BytesIO()
        mod_df.to_excel(buf, index=False)
        st.download_button("📄 Télécharger le Modèle Vide", buf.getvalue(), "modele_eleveur.xlsx")
        
    with c2:
        st.subheader("📥 Importer")
        file = st.file_uploader("Fichier Excel d'un confrère", type=['xlsx'])
        if file:
            imp_df = pd.read_excel(file)
            if st.button("Confirmer l'importation"):
                with get_db_connection() as conn:
                    for _, r in imp_df.iterrows():
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (str(r['id']), str(r.get('race', 'Inconnue'))))
                        conn.execute("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon) VALUES (?,?,?,?,?,?)", 
                                     (str(r['id']), r.get('p10',0), r.get('p30',0), r.get('p70',0), r.get('h_garrot',0), r.get('c_canon',0)))
                st.success("Importation terminée !"); st.rerun()
