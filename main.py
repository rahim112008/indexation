import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

# --- CONNEXION BASE DE DONNÉES ---
def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # Table principale avec les nouveaux champs de poids et mensurations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beliers (
                id TEXT PRIMARY KEY,
                race TEXT,
                age_estimé TEXT,
                sexe TEXT,
                poids_naissance REAL,
                poids_10j REAL,
                poids_30j REAL,
                poids_70j REAL,
                h_garrot REAL,
                c_canon REAL,
                p_thoracique REAL,
                l_corps REAL,
                date_enregistrement DATETIME
            )
        """)
        conn.commit()

init_db()

# --- CHARGEMENT DES DONNÉES ---
def load_data():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM beliers", conn)

# --- INTERFACE PRINCIPALE ---
def main():
    st.sidebar.title("🐏 Expert Ovin Pro")
    menu = st.sidebar.radio("Navigation", ["📊 Tableau de Bord", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])
    
    df = load_data()

    # --- 1. TABLEAU DE BORD ---
    if menu == "📊 Tableau de Bord":
        st.title("📊 Statistiques du Troupeau")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Individus", len(df))
            if 'poids_70j' in df.columns:
                c2.metric("Poids Moyen (Sevrage)", f"{df['poids_70j'].mean():.1f} kg")
            
            st.subheader("Derniers enregistrements")
            st.dataframe(df.tail(10), use_container_width=True)
        else:
            st.info("Bienvenue ! Commencez par scanner ou saisir un animal.")

    # --- 2. SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            source = st.radio("Source", ["📷 Caméra", "📁 Photo"], horizontal=True)
        with col_cfg2:
            mode_scanner = st.radio("Méthode", ["🤖 Automatique", "📏 Manuel"], horizontal=True)

        img = st.camera_input("Scanner") if source == "📷 Caméra" else st.file_uploader("Importer", type=['jpg','png','jpeg'])

        if img:
            col_img, col_res = st.columns([1.5, 1])
            with col_img:
                st.image(img, use_container_width=True)
            with col_res:
                if mode_scanner == "🤖 Automatique":
                    with st.spinner("Analyse IA..."):
                        time.sleep(1)
                        # Simulation d'un cadrage réussi
                        res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                        st.success("✅ CADRAGE VALIDE (98%)")
                else:
                    res = {"h_garrot": 72.0, "c_canon": 8.5, "p_thoracique": 84.0, "l_corps": 82.0}
                
                st.session_state['scan'] = res
                st.metric("📏 Hauteur", f"{res['h_garrot']} cm")
                st.metric("🦴 Tour de Canon", f"{res['c_canon']} cm")
                if st.button("🚀 ENVOYER À LA SAISIE", use_container_width=True):
                    st.success("Données prêtes !")

    # --- 3. SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Fiche d'Identification")
        sd = st.session_state.get('scan', {})
        
        with st.form("form_saisie"):
            c1, c2, c3 = st.columns(3)
            with c1: id_animal = st.text_input("ID Animal *")
            with c2: dentition = st.selectbox("Âge (Dents)", ["Lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            with c3: sexe = st.radio("Sexe", ["M", "F"], horizontal=True)

            st.subheader("⚖️ Poids (kg)")
            p1, p2, p3, p4 = st.columns(4)
            with p1: p_n = st.number_input("Naissance", value=0.0)
            with p2: p_10 = st.number_input("10j", value=0.0)
            with p3: p_30 = st.number_input("30j", value=0.0)
            with p4: p_70 = st.number_input("70j", value=0.0)

            st.subheader("📏 Mensurations (cm)")
            m1, m2, m3, m4 = st.columns(4)
            with m1: h_g = st.number_input("Hauteur Garrot", value=float(sd.get('h_garrot', 0.0)))
            with m2: c_c = st.number_input("Tour de Canon", value=float(sd.get('c_canon', 0.0)))
            with m3: p_t = st.number_input("Thorax", value=float(sd.get('p_thoracique', 0.0)))
            with m4: l_c = st.number_input("Longueur", value=float(sd.get('l_corps', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER"):
                if id_animal:
                    with get_db_connection() as conn:
                        conn.execute("""INSERT OR REPLACE INTO beliers 
                            (id, race, age_estimé, sexe, poids_naissance, poids_10j, poids_30j, poids_70j, h_garrot, c_canon, p_thoracique, l_corps, date_enregistrement)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (id_animal, "Ouled Djellal", dentition, sexe, p_n, p_10, p_30, p_70, h_g, c_c, p_t, l_c, datetime.now()))
                    st.success(f"Animal {id_animal} enregistré !")
                else: st.error("L'ID est obligatoire.")

    # --- 4. ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        st.subheader("📥 Export / Import")
        if not df.empty:
            st.download_button("📥 Télécharger CSV", df.to_csv(index=False).encode('utf-8'), "inventaire.csv", "text/csv")
        
        st.divider()
        with st.expander("Zone de danger"):
            if st.button("🗑️ RÉINITIALISER LA BASE"):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM beliers")
                st.rerun()

if __name__ == "__main__":
    main()
