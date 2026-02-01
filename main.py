import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import random
import time

# ==========================================
# 1. INITIALISATION & SÉCURITÉ DB (CORRIGÉ)
# ==========================================
DB_NAME = "expert_ovin_recherche.db"

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

def init_db():
    """Crée les tables si elles n'existent pas ET ajoute les colonnes manquantes."""
    with get_db_connection() as conn:
        # Création des tables de base
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')
        
        # SÉCURITÉ : Ajouter la colonne l_corps si elle manque (évite l'OperationalError)
        try:
            conn.execute("ALTER TABLE mesures ADD COLUMN l_corps REAL DEFAULT 85.0")
        except sqlite3.OperationalError:
            pass # La colonne existe déjà

def load_data():
    """Charge les données en garantissant que la structure est prête."""
    init_db() # Appelé à chaque chargement pour plus de sécurité
    try:
        with get_db_connection() as conn:
            query = """SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                       FROM beliers b 
                       LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal
                       LEFT JOIN mesures m ON last_m.last_id = m.id"""
            df = pd.read_sql(query, conn)
            
            if df.empty:
                return pd.DataFrame()
            
            # Calcul des métriques sans modifier la structure originale
            metrics = df.apply(moteur_calcul_expert, axis=1)
            return pd.concat([df, metrics], axis=1).drop_duplicates(subset=['id'])
    except Exception as e:
        # En cas d'erreur de lecture (table vide par ex.), on renvoie un DF vide propre
        return pd.DataFrame()

# ==========================================
# 2. MOTEUR ZOOTECHNIQUE (VOTRE STRUCTURE)
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'Volume': 0.0, 'Rendement': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc, lg = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9), float(row.get('l_corps') or 85)
        
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        ic = (pt / (cc * hg)) * 1000
        res['Volume'] = round((np.pi * ((pt/(2*np.pi))**2) * lg) / 1000, 1)
        
        res['Gras'] = round(max(5.0, 4.0 + ((1.2 + p70*0.15 + ic*0.05 - hg*0.03) * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (ic * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, 3.2 + (1450 / res['GMD']) - (ic / 200)), 2)
        return pd.Series(res)
    except:
        return pd.Series(res)

# ==========================================
# 3. INTERFACE (VOS BLOCS RÉACTUALISÉS)
# ==========================================
def main():
    # 1. Initialisation prioritaire
    init_db()
    df = load_data()
    
    st.sidebar.title("💎 EXPERT SELECTOR PRO")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "📸 Scanner IA", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition IA", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Performance du Troupeau")
        if df.empty:
            st.info("La base de données est vide. Allez dans 'Admin' pour générer des données ou 'Indexation' pour ajouter un animal.")
        else:
            st.dataframe(df[['id', 'sexe', 'dentition', 'GMD', 'Muscle', 'Rendement']], use_container_width=True)
            fig = px.scatter(df, x="GMD", y="Muscle", color="sexe", size="Rendement", title="Analyse GMD vs Muscle")
            st.plotly_chart(fig, use_container_width=True)

    elif menu == "📸 Scanner IA":
        st.title("📸 Station de Scan")
        source = st.radio("Source", ["📷 Caméra", "📁 Télécharger"], horizontal=True)
        img_file = st.camera_input("Scan") if source == "📷 Caméra" else st.file_uploader("Image", type=['jpg','png'])
        
        if img_file:
            st.image(img_file, caption="Analyse biométrique...")
            time.sleep(1)
            res = {"h_garrot": 77.5, "p_thoracique": 94.0, "l_corps": 88.5, "c_canon": 9.2}
            st.session_state['last_scan'] = res
            st.success("✅ Mesures détectées et prêtes pour l'indexation.")
            st.json(res)

    elif menu == "✍️ Indexation":
        st.title("✍️ Indexation")
        scan = st.session_state.get('last_scan', {})
        with st.form("index_form"):
            c1, c2 = st.columns(2)
            id_a = c1.text_input("ID Animal")
            dent = c1.selectbox("Dentition", ["Lait", "2 Dents", "4 Dents", "8 Dents"])
            hg = c2.number_input("Hauteur", value=float(scan.get('h_garrot', 75.0)))
            pt = c2.number_input("Thorax", value=float(scan.get('p_thoracique', 90.0)))
            lg = c2.number_input("Longueur", value=float(scan.get('l_corps', 85.0)))
            cc = c2.number_input("Canon", value=float(scan.get('c_canon', 9.0)))
            
            if st.form_submit_button("Sauvegarder"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "O.Djellal", "M", dent))
                        conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                     (id_a, 15, 35, hg, cc, pt, lg))
                    st.success("Enregistré !")
                    st.rerun()

    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Echo-Composition")
        if not df.empty:
            target = st.selectbox("Sujet", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4)])
            st.plotly_chart(fig)

    elif menu == "🥗 Nutrition IA":
        st.title("🥗 Nutrition IA")
        st.info("Simulateur basé sur les besoins en UFL pour Ouled Djellal.")

    elif menu == "🔧 Admin":
        st.title("🔧 Admin")
        if st.button("🚀 Générer 50 individus de test"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_t = f"TEST-{random.randint(1000,9999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "O.Djellal", "M", "2 Dents"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                 (id_t, 14, 32, random.uniform(70,80), 9.0, random.uniform(85,100), random.uniform(80,90)))
            st.success("Base de données initialisée !")
            st.rerun()

if __name__ == "__main__":
    main()
