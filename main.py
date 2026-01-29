import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import io
from datetime import datetime
from contextlib import contextmanager

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Expert Selector Ultra", layout="wide", page_icon="🐏")

# Nom de base de données stable
DB_NAME = "expert_ovin_v7_preinstalled.db"

# --- 2. GESTION BASE DE DONNÉES ---
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def preinstaller_individus():
    """Injecte des individus de test si la base est vide"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM beliers")
        if cursor.fetchone()[0] == 0:  # Si la base est vide
            # Liste d'individus modèles (Race, Poids, Canon)
            test_data = [
                ("ELITE-001", "Ouled Djellal", 38.5, 11.5, 76.0, 26.0, 90.0),
                ("ELITE-002", "Rembi", 36.2, 11.0, 74.5, 25.5, 88.0),
                ("ELITE-003", "Hamra", 32.0, 10.2, 72.0, 24.0, 85.0),
                ("TOP-004", "Ouled Djellal", 40.1, 12.0, 78.0, 27.0, 92.0),
                ("STD-005", "Rembi", 34.0, 10.5, 73.0, 25.0, 87.0)
            ]
            for aid, race, p70, can, hg, lp, pt in test_data:
                conn.execute("INSERT INTO beliers (id, race, date_naiss) VALUES (?,?,'2024-01-10')", (aid, race))
                conn.execute("""INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, date_mesure) 
                             VALUES (?, 5.0, 15.0, ?, ?, ?, ?, ?, ?)""", 
                             (aid, p70, hg, can, lp, pt, datetime.now().strftime("%Y-%m-%d")))

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, date_naiss TEXT, 
            objectif TEXT, dentition TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT,
            p10 REAL, p30 REAL, p70 REAL, h_garrot REAL, l_corps REAL, 
            p_thoracique REAL, l_poitrine REAL, c_canon REAL, 
            date_mesure TEXT,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
    preinstaller_individus() # Appel de la pré-installation

# --- 3. LOGIQUE MÉTIER ---
def calculer_metrics(row):
    try:
        p70 = float(row.get('p70', 0) or 0)
        p30 = float(row.get('p30', 0) or 0)
        if p70 <= 0 or p30 <= 0: return 0.0, 0.0, 0.0
        gmq = ((p70 - p30) / 40) * 1000
        rendement = 52.4 + (0.35 * float(row.get('l_poitrine', 24))) - (0.08 * float(row.get('h_garrot', 70)))
        index = (gmq * 0.15) + (rendement * 0.45) + (p70 * 0.2) + (float(row.get('c_canon', 9)) * 2.5)
        return round(gmq, 1), round(rendement, 1), round(index, 2)
    except: return 0.0, 0.0, 0.0

# --- 4. CHARGEMENT ---
def load_data():
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p10, m.p30, m.p70, m.h_garrot, m.l_corps, 
                   m.p_thoracique, m.l_poitrine, m.c_canon FROM beliers b 
                   LEFT JOIN mesures m ON b.id = m.id_animal"""
        df = pd.read_sql(query, conn)
        if not df.empty:
            df[['GMQ', 'Rendement', 'Index']] = df.apply(lambda x: pd.Series(calculer_metrics(x)), axis=1)
        return df

# --- 5. INTERFACE (DESIGN 110) ---
def main():
    init_db()
    st.sidebar.title("💎 Expert Selector")
    
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "📈 Analyse", "✍️ Saisie Manuelle", "📥 Import/Export"])
    df = load_data()

    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord")
        if not df.empty:
            st.dataframe(df.sort_values('Index', ascending=False), use_container_width=True)
        else:
            st.info("La base est vide.")

    elif menu == "✍️ Saisie Manuelle":
        st.title("✍️ Fiche d'Identification")
        scan = st.session_state.get('scan_data', {})
        
        with st.form("form_saisie"):
            st.subheader("Identification")
            c_id1, c_id2 = st.columns(2)
            with c_id1: animal_id = st.text_input("ID Animal *")
            with c_id2: race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])

            st.subheader("Poids de croissance")
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1: p10 = st.number_input("Poids J10 (kg)", 0.0)
            with col_p2: p30 = st.number_input("Poids J30 (kg)", 0.0)
            with col_p3: p70 = st.number_input("Poids J70 (kg) *", 0.0)

            st.subheader("Mensurations (cm)")
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            with col_m1: hg = st.number_input("Hauteur Garrot", value=float(scan.get('h_garrot', 0.0)))
            with col_m2: can = st.number_input("Canon (Tour)", value=float(scan.get('c_canon', 0.0)))
            with col_m3: lp = st.number_input("Larg. Poitrine", value=float(scan.get('l_poitrine', 0.0)))
            with col_m4: pt = st.number_input("Périm. Thorax", value=float(scan.get('p_thoracique', 0.0)))
            with col_m5: lc = st.number_input("Long. Corps", value=float(scan.get('l_corps', 0.0)))

            if st.form_submit_button("💾 Enregistrer", type="primary"):
                if animal_id and p70 > 0:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (animal_id, race))
                        conn.execute("INSERT INTO mesures (id_animal, p10, p30, p70, h_garrot, c_canon, l_poitrine, p_thoracique, l_corps, date_mesure) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                     (animal_id, p10, p30, p70, hg, can, lp, pt, lc, datetime.now().strftime("%Y-%m-%d")))
                    st.success(f"Animal {animal_id} enregistré !"); st.rerun()

    elif menu == "📥 Import/Export":
        st.title("📥 Échange de Données")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Export")
            if not df.empty:
                buf = io.BytesIO()
                df.to_excel(buf, index=False)
                st.download_button("📥 Télécharger mon Troupeau", buf.getvalue(), "troupeau.xlsx")
        with c2:
            st.subheader("Import")
            file = st.file_uploader("Fichier Excel", type=['xlsx'])
            if file and st.button("Confirmer l'import"):
                imp_df = pd.read_excel(file)
                with get_db_connection() as conn:
                    for _, r in imp_df.iterrows():
                        conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (str(r['id']), str(r.get('race', 'ND'))))
                        conn.execute("INSERT INTO mesures (id_animal, p70, c_canon) VALUES (?,?,?)", (str(r['id']), r.get('p70',0), r.get('c_canon',0)))
                st.success("Importé !"); st.rerun()

if __name__ == "__main__":
    main()
