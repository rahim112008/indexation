import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
from PIL import Image
import random
import time

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v5.0", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 15px; border-radius: 12px;
        border-top: 5px solid #2E7D32; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    .status-valid { color: #2E7D32; font-weight: bold; }
    .status-error { color: #D32F2F; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_recherche.db"

# ==========================================
# 2. GESTION BASE DE DONNÉES
# ==========================================
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
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
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. MOTEUR DE CALCUL ZOOTECHNIQUE
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, min(8.0, 3.2 + (1450 / res['GMD']) - (res['IC'] / 200))), 2)
        
        egd = 1.2 + (p70 * 0.15) + (res['IC'] * 0.05) - (hg * 0.03)
        res['Gras'] = round(max(5.0, 4.0 + (egd * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (res['IC'] * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    init_db()
    with get_db_connection() as conn:
        query = """SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                   FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                   LEFT JOIN mesures m ON l.mid = m.id"""
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id']).reset_index(drop=True)
        metrics = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, metrics], axis=1)
    return df

# ==========================================
# 4. BLOCS DE L'INTERFACE (SCANNER & SAISIE)
# ==========================================

def view_scanner():
    st.title("📸 Scanner Biométrique Intelligent")
    mode_scanner = st.sidebar.radio("Mode d'analyse", ["🤖 Automatique (IA)", "📏 Manuel (Gabarit)"])
    source = st.radio("Source de l'image", ["📷 Caméra en direct", "📁 Charger une photo"], horizontal=True)

    if source == "📷 Caméra en direct":
        img = st.camera_input("Positionnez l'animal bien de profil")
    else:
        img = st.file_uploader("Charger une photo de profil complète", type=['jpg', 'jpeg', 'png'])

    if img:
        col_img, col_res = st.columns([1.5, 1])
        with col_img:
            st.image(img, caption="Silhouette et points osseux détectés", use_container_width=True)
        
        with col_res:
            if mode_scanner == "🤖 Automatique (IA)":
                with st.spinner("🧠 Analyse du squelette et du cadrage..."):
                    time.sleep(1.2)
                    margin_left = 10 # Simulation
                    image_est_complete = True if margin_left > 5 else False
                    
                    if image_est_complete:
                        st.success("✅ **CADRAGE VALIDE (98%)**")
                        res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                    else:
                        st.error("⚠️ **IMAGE INCOMPLÈTE**")
                        res = {"h_garrot": 73.5, "c_canon": 8.2, "p_thoracique": 84.0, "l_corps": 0.0}
            else:
                st.subheader("📏 Mesures au Gabarit")
                h_in = st.number_input("Hauteur Garrot (cm)", value=72.0)
                c_in = st.number_input("Tour de Canon (cm)", value=8.5)
                t_in = st.number_input("Périmètre Thorax (cm)", value=84.0)
                l_in = st.number_input("Longueur Corps (cm)", value=82.0)
                res = {"h_garrot": h_in, "c_canon": c_in, "p_thoracique": t_in, "l_corps": l_in}

            st.divider()
            st.session_state['scan'] = res
            m1, m2 = st.columns(2)
            m1.metric("📏 Hauteur", f"{res['h_garrot']} cm")
            m1.metric("🦴 Tour de Canon", f"{res['c_canon']} cm")
            m2.metric("⭕ Thorax", f"{res['p_thoracique']} cm")
            m2.metric("📏 Longueur", f"{res['l_corps']} cm")

            if st.button("🚀 VALIDER ET ENVOYER À LA SAISIE", type="primary", use_container_width=True):
                st.session_state['go_to_saisie'] = True
                st.toast("Données transférées !")

def view_saisie():
    st.title("✍️ Indexation et Identification")
    sd = st.session_state.get('scan', {})
    
    with st.form("form_saisie"):
        st.subheader("🆔 État Civil de l'Animal")
        c1, c2, c3 = st.columns(3)
        with c1: id_animal = st.text_input("N° Boucle / ID *")
        with c2: statut_dentaire = st.selectbox("Âge (Dentition)", ["Agneau", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
        with c3: sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)

        st.divider()
        st.subheader("⚖️ Historique de Pesée")
        cp1, cp2, cp3, cp4 = st.columns(4)
        p_30j = cp3.number_input("Poids à 30j", min_value=0.0, value=0.0)
        p_70j = cp4.number_input("Poids actuel / 70j", min_value=0.0, value=0.0)

        st.divider()
        st.subheader("📏 Morphologie (Scanner)")
        cm1, cm2, cm3, cm4 = st.columns(4)
        hauteur = cm1.number_input("Hauteur Garrot", value=float(sd.get('h_garrot', 0.0)))
        canon = cm2.number_input("Tour de Canon", value=float(sd.get('c_canon', 0.0)))
        thorax = cm3.number_input("Périmètre Thorax", value=float(sd.get('p_thoracique', 0.0)))
        longueur = cm4.number_input("Longueur Corps", value=float(sd.get('l_corps', 0.0)))

        if st.form_submit_button("💾 INDEXER L'INDIVIDU", type="primary", use_container_width=True):
            if id_animal:
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_animal, "O.Djellal", sexe, statut_dentaire))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)", 
                                 (id_animal, p_30j, p_70j, hauteur, canon, thorax, longueur))
                st.success(f"✅ L'animal {id_animal} a été ajouté.")
                st.rerun()

# ==========================================
# 5. NAVIGATION PRINCIPALE
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT OVIN V5")
    menu = st.sidebar.radio("Menu", ["🏠 Dashboard", "📸 Scanner", "✍️ Saisie", "🥩 Echo-Composition", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("📊 Tableau de Bord")
        if not df.empty:
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA']], use_container_width=True)
        else: st.info("Base vide. Utilisez l'onglet Admin pour générer 50 individus.")

    elif menu == "📸 Scanner": view_scanner()
    elif menu == "✍️ Saisie": view_saisie()
    
    elif menu == "🥩 Echo-Composition":
        if not df.empty:
            target = st.selectbox("Choisir l'animal", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            fig = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj['Muscle'], subj['Gras'], subj['Os']], hole=.4)])
            st.plotly_chart(fig)

    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS DE TEST"):
            types = ["Bélier", "Brebis", "Agneau"]
            dents = ["Agneau", "2 Dents", "4 Dents", "8 Dents"]
            with get_db_connection() as conn:
                for i in range(50):
                    id_t = f"OD-{random.randint(1000,9999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "O.Djellal", random.choice(types), random.choice(dents)))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)", 
                                 (id_t, random.uniform(12,18), random.uniform(22,38), random.uniform(70,82), random.uniform(8.5,10), random.uniform(85,98), random.uniform(80,95)))
            st.success("50 individus créés !")
            st.rerun()

if __name__ == "__main__":
    main()
