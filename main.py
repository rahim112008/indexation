import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

# --- INITIALISATION DE LA BASE DE DONNÉES ---
def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
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

def load_data():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM beliers", conn)

# --- APPLICATION PRINCIPALE ---
def main():
    df = load_data()
    
    # Initialisation du scan dans la session si absent
    if 'scan' not in st.session_state:
        st.session_state['scan'] = {}

    # --- BARRE LATÉRALE (SIDEBAR DASHBOARD) ---
    st.sidebar.title("🐏 Expert Ovin Pro")
    menu = st.sidebar.radio("MENU PRINCIPAL", ["📊 Tableau de Bord", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])
    
    st.sidebar.divider()

    if not df.empty:
        st.sidebar.subheader("📈 Composition Troupeau")
        col_s1, col_s2 = st.sidebar.columns(2)
        with col_s1:
            st.write("**Sexe**")
            st.caption(str(df['sexe'].value_counts().to_dict()))
        with col_s2:
            st.write("**Âge**")
            st.caption(str(df['age_estimé'].value_counts().to_dict()))

        st.sidebar.divider()

        # Bloc Composition Tissulaire (Estimation Biométrique)
        st.sidebar.subheader("🥩 Composition Tissulaire")
        m_canon = df['c_canon'].mean() if 'c_canon' in df.columns else 8.5
        m_thorax = df['p_thoracique'].mean() if 'p_thoracique' in df.columns else 85.0
        
        p_os = round(m_canon * 2.1, 1)
        p_viande = round(m_thorax / 1.55, 1)
        p_gras = round(max(2.0, 100 - (p_os + p_viande)), 1)

        st.sidebar.progress(min(p_viande/100, 1.0), text=f"Muscle: {p_viande}%")
        st.sidebar.progress(min(p_os/100, 1.0), text=f"Os: {p_os}%")
        st.sidebar.progress(min(p_gras/100, 1.0), text=f"Gras: {p_gras}%")
    
    st.sidebar.divider()
    st.sidebar.caption(f"📅 {datetime.now().strftime('%d/%m/%Y')}")

    # --- 1. TABLEAU DE BORD (DASHBOARD) ---
    if menu == "📊 Tableau de Bord":
        st.title("📊 Statistiques Générales")
        if not df.empty:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Individus", len(df))
            m2.metric("Poids Moy. (70j)", f"{df[df['poids_70j']>0]['poids_70j'].mean():.1f} kg")
            m3.metric("Moy. Canon", f"{df['c_canon'].mean():.1f} cm")
            m4.metric("Moy. Hauteur", f"{df['h_garrot'].mean():.1f} cm")
            
            st.divider()
            st.subheader("🔍 Historique des Indexations")
            st.dataframe(df.sort_values(by='date_enregistrement', ascending=False), use_container_width=True)
        else:
            st.info("👋 Bienvenue ! Votre base de données est vide. Utilisez le Scanner pour commencer.")

    # --- 2. SCANNER (IA & ÉTALON 1M) ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        
        c_src, c_mod = st.columns(2)
        with c_src:
            source = st.radio("Source", ["📷 Caméra en direct", "📁 Importer photo"], horizontal=True)
        with c_mod:
            mode = st.radio("Méthode d'analyse", ["🤖 Automatique (IA)", "📏 Manuel (Étalon 1m)"], horizontal=True)

        img = st.camera_input("Scan") if source == "📷 Caméra en direct" else st.file_uploader("Image", type=['jpg','png','jpeg'])

        if img:
            col_left, col_right = st.columns([1.5, 1])
            with col_left:
                st.image(img, use_container_width=True, caption="Analyse morphologique")
            
            with col_right:
                if mode == "🤖 Automatique (IA)":
                    with st.spinner("Analyse du cadrage..."):
                        time.sleep(1.5)
                        # Simulation détection IA
                        st.success("✅ CADRAGE VALIDE (98%)")
                        res = {"h": 74.2, "c": 8.8, "t": 86.5, "l": 84.0}
                else:
                    st.subheader("📏 Calibration Étalon")
                    st.info("Utilisez un bâton de 1 mètre comme référence.")
                    etalon = st.number_input("Référence Étalon (cm)", value=100.0)
                    h_m = st.number_input("Mesure Hauteur (cm)", value=72.0)
                    c_m = st.number_input("Mesure Canon (cm)", value=8.5)
                    t_m = st.number_input("Mesure Thorax (cm)", value=84.0)
                    l_m = st.number_input("Mesure Longueur (cm)", value=82.0)
                    res = {"h": h_m, "c": c_m, "t": t_m, "l": l_m}

                st.session_state['scan'] = res
                st.divider()
                st.metric("🦴 Tour de Canon", f"{res['c']} cm")
                st.metric("📏 Hauteur Garrot", f"{res['h']} cm")
                
                if st.button("🚀 ENVOYER À LA SAISIE", use_container_width=True, type="primary"):
                    st.toast("Données transférées !")

    # --- 3. SAISIE (AVEC POIDS & DENTITION) ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Fiche d'Indexation Complète")
        sd = st.session_state.get('scan', {})
        
        with st.form("form_saisie"):
            st.subheader("🆔 Identification & Âge")
            f1, f2, f3 = st.columns(3)
            with f1: id_ani = st.text_input("N° Boucle / ID *")
            with f2: dent = st.selectbox("État Dentaire (Âge)", ["Agneau (Lait)", "2 Dents", "4 Dents", "6 Dents", "8 Dents", "Bouche Usée"])
            with f3: sexe = st.radio("Sexe", ["Mâle", "Femelle"], horizontal=True)

            st.divider()
            st.subheader("⚖️ Suivi de Croissance (Poids kg)")
            p1, p2, p3, p4 = st.columns(4)
            with p1: p_n = st.number_input("Naissance", value=0.0)
            with p2: p_10 = st.number_input("Poids 10j", value=0.0)
            with p3: p_30 = st.number_input("Poids 30j", value=0.0)
            with p4: p_70 = st.number_input("Poids 70j (Sevrage)", value=0.0)

            st.divider()
            st.subheader("📏 Mensurations Scanner (cm)")
            m1, m2, m3, m4 = st.columns(4)
            with m1: h_g = st.number_input("Hauteur Garrot", value=float(sd.get('h', 0.0)))
            with m2: c_c = st.number_input("Tour de Canon", value=float(sd.get('c', 0.0)))
            with m3: p_t = st.number_input("Périmètre Thorax", value=float(sd.get('t', 0.0)))
            with m4: l_c = st.number_input("Longueur Corps", value=float(sd.get('l', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER L'ANIMAL", use_container_width=True, type="primary"):
                if id_ani:
                    with get_db_connection() as conn:
                        conn.execute("""INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (id_ani, "Ouled Djellal", dent, sexe, p_n, p_10, p_30, p_70, h_g, c_c, p_t, l_c, datetime.now()))
                    st.success(f"✅ Animal {id_ani} enregistré avec succès !")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⚠️ L'ID est obligatoire.")

    # --- 4. ADMIN (PROFESSIONNEL) ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        
        st.subheader("📥 Export des Données")
        if not df.empty:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Télécharger l'inventaire complet (CSV)",
                data=csv,
                file_name=f"export_ovins_{datetime.now().strftime('%d_%m_%Y')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.button("📥 Base vide", disabled=True, use_container_width=True)

        st.divider()
        st.subheader("⚠️ Zone de Danger")
        with st.expander("Réinitialisation de la base de données"):
            st.warning("Action irréversible : tous les animaux seront effacés.")
            confirm = st.checkbox("Je confirme vouloir vider la base.")
            if st.button("🗑️ SUPPRIMER TOUTES LES DONNÉES", disabled=not confirm, type="primary"):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM beliers")
                st.success("Base de données réinitialisée.")
                st.rerun()

if __name__ == "__main__":
    main()
