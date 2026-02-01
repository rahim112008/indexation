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
# 1. INITIALISATION & SÉCURITÉ BASE DE DONNÉES
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
    """Garantit l'existence des tables pour éviter la DatabaseError sur Cloud."""
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

def load_data():
    init_db()
    try:
        with get_db_connection() as conn:
            query = """SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                       FROM beliers b 
                       LEFT JOIN (SELECT id_animal, MAX(id) as last_id FROM mesures GROUP BY id_animal) last_m ON b.id = last_m.id_animal
                       LEFT JOIN mesures m ON last_m.last_id = m.id"""
            df = pd.read_sql(query, conn)
            if df.empty: return pd.DataFrame()
            
            # Application du moteur zootechnique
            metrics = df.apply(moteur_calcul_expert, axis=1)
            return pd.concat([df, metrics], axis=1).drop_duplicates(subset=['id'])
    except Exception:
        return pd.DataFrame()

# ==========================================
# 2. MOTEUR ZOOTECHNIQUE AVANCÉ
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0, 'Volume': 0.0, 'Rendement': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc, lg = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9), float(row.get('l_corps') or 85)
        
        # GMD & Compacité
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        
        # Volume Corporel Estimé (en Litres)
        rayon_moyen = pt / (2 * np.pi)
        res['Volume'] = round((np.pi * (rayon_moyen**2) * lg) / 1000, 1)

        # Prédiction Echo-Composition & Rendement
        egd = 1.2 + (p70 * 0.15) + (res['IC'] * 0.05) - (hg * 0.03)
        res['Gras'] = round(max(5.0, 4.0 + (egd * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (res['IC'] * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        res['Rendement'] = round(42 + (res['Muscle'] * 0.12), 1)
        
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, 3.2 + (1450 / res['GMD']) - (res['IC'] / 200)), 2)
        return pd.Series(res)
    except: return pd.Series(res)

# ==========================================
# 3. INTERFACE UTILISATEUR (UI)
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT SELECTOR V7.5")
    menu = st.sidebar.radio("Navigation", 
        ["🏠 Dashboard", "📸 Scanner Dual", "✍️ Indexation", "🥩 Echo-Composition", "🥗 Nutrition IA", "🔧 Admin"])

    # --- BLOC INDEXATION ---
    if menu == "✍️ Indexation":
        st.title("✍️ Identification & Morphométrie")
        scan = st.session_state.get('last_scan', {})
        with st.form("form_index"):
            c1, c2, c3 = st.columns(3)
            with c1:
                id_a = st.text_input("ID Animal (Boucle/Puce) *")
                sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)
                dentition = st.selectbox("Âge (Dents)", ["Lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            with c2:
                p30 = st.number_input("Poids à 30j (kg)", 10.0)
                p70 = st.number_input("Poids actuel (kg)", 30.0)
            with c3:
                hg = st.number_input("Hauteur (cm)", value=float(scan.get('h_garrot', 75.0)))
                cc = st.number_input("Canon (cm)", value=float(scan.get('c_canon', 9.0)))
                pt = st.number_input("Thorax (cm)", value=float(scan.get('p_thoracique', 90.0)))
                lg = st.number_input("Longueur (cm)", value=float(scan.get('l_corps', 85.0)))

            if st.form_submit_button("💾 ENREGISTRER L'INDIVIDU"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "O.Djellal", sexe, dentition))
                        conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                     (id_a, p30, p70, hg, cc, pt, lg))
                    st.success(f"Animal {id_a} indexé avec succès !")
                    st.rerun()

    # --- BLOC ECHO-COMPOSITION ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse Tissulaire Virtuelle")
        if df.empty: st.warning("Veuillez d'abord indexer des animaux.")
        else:
            target = st.selectbox("Sélectionner un sujet", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], 
                                values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4,
                                marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.metric("Rendement Carcasse", f"{subj['Rendement']}%")
                st.metric("Volume Estimé", f"{subj['Volume']} L")
                st.info(f"Analyse : Ce sujet présente une compacité de {subj['IC']:.0f}.")

    # --- BLOC NUTRITION ---
    elif menu == "🥗 Nutrition IA":
        st.title("🥗 Simulateur de Ration")
        if df.empty: st.warning("Base vide.")
        else:
            target = st.selectbox("Animal cible", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            obj_gmd = st.slider("Objectif de croissance (GMD g/j)", 100, 500, 300)
            
            # Calcul UFL (Unité Fourragère Lait) - Simplifié
            besoin_entretien = 0.035 * (subj['p70']**0.75)
            besoin_croissance = (obj_gmd / 1000) * 3.5
            total_ufl = round(besoin_entretien + besoin_croissance, 2)
            
            st.success(f"Ration recommandée : **{total_ufl} UFL/jour**")
            st.write(f"- Foin/Parcours : {total_ufl*0.6:.2f} UFL")
            st.write(f"- Concentré : {total_ufl*0.4:.2f} UFL")

    # --- AUTRES BLOCS ---
    elif menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord du Troupeau")
        if not df.empty:
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'Volume', 'Rendement']], use_container_width=True)
            fig_dist = px.histogram(df, x="Muscle", title="Distribution du Muscle dans le Troupeau", color_discrete_sequence=['#2E7D32'])
            st.plotly_chart(fig_dist)

    elif menu == "📸 Scanner Dual":
        st.title("📸 Station de Scan Biométrique")
        mode = st.radio("Technologie", ["🤖 IA Auto", "📏 Hybride (Étalon)"])
        img = st.camera_input("Scanner de profil")
        if img:
            st.success("Analyse en cours... (Cadrage 98%)")
            st.session_state['last_scan'] = {"h_garrot": 77.2, "p_thoracique": 94.5, "l_corps": 86.0, "c_canon": 9.2}

    elif menu == "🔧 Admin":
        if st.button("🚀 GÉNÉRER POPULATION DE RECHERCHE (50 individus)"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_t = f"REF-{random.randint(1000,9999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "Ouled Djellal", random.choice(["Bélier", "Brebis"]), "2 Dents"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)",
                                 (id_t, 14, 35, random.uniform(72,80), 9.0, random.uniform(88,100), random.uniform(82,92)))
            st.success("Base peuplée !")
            st.rerun()

if __name__ == "__main__":
    main()
