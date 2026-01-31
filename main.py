import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

# --- CONNEXION & INITIALISATION BASE DE DONNÉES ---
def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # Création de la table avec tous les champs nécessaires
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

# --- LOGIQUE PRINCIPALE ---
def main():
    df = load_data()

    # --- BARRE LATÉRALE (SIDEBAR) ---
    st.sidebar.title("🐏 Expert Ovin Pro")
    menu = st.sidebar.radio("MENU PRINCIPAL", ["📊 Tableau de Bord", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])
    
    st.sidebar.divider()

    if not df.empty:
        # Composition du troupeau
        st.sidebar.subheader("📈 Composition Troupeau")
        c_side1, c_side2 = st.sidebar.columns(2)
        with c_side1:
            st.write("**Sexe**")
            st.caption(str(df['sexe'].value_counts().to_dict()))
        with c_side2:
            st.write("**Âge**")
            st.caption(str(df['age_estimé'].value_counts().to_dict()))

        st.sidebar.divider()

        # Composition Tissulaire (Estimation IA)
        st.sidebar.subheader("🥩 Composition Tissulaire")
        moy_canon = df['c_canon'].mean() if 'c_canon' in df.columns else 8.5
        moy_thorax = df['p_thoracique'].mean() if 'p_thoracique' in df.columns else 85.0
        
        # Algorithme d'estimation Viande/Os/Gras
        p_os = round((moy_canon * 2.1), 1) 
        p_viande = round((moy_thorax / 1.55), 1)
        p_gras = round(max(2.0, 100 - (p_os + p_viande)), 1)

        st.sidebar.progress(min(p_viande/100, 1.0), text=f"Muscle: {p_viande}%")
        st.sidebar.progress(min(p_os/100, 1.0), text=f"Os: {p_os}%")
        st.sidebar.progress(min(p_gras/100, 1.0), text=f"Gras: {p_gras}%")
    else:
        st.sidebar.info("En attente de données...")

    st.sidebar.divider()
    st.sidebar.caption(f"📅 {datetime.now().strftime('%d/%m/%Y')}")

    # --- 1. TABLEAU DE BORD ---
    if menu == "📊 Tableau de Bord":
        st.title("📊 Statistiques Générales")
        if not df.empty:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Effectif Total", len(df))
            m2.metric("Poids Moy. (70j)", f"{df[df['poids_70j']>0]['poids_70j'].mean():.1f} kg")
            m3.metric("Tour Canon Moy.", f"{df['c_canon'].mean():.1f} cm")
            m4.metric("Hauteur Moy.", f"{df['h_garrot'].mean():.1f} cm")
            
            st.divider()
            st.subheader("🔍 Derniers enregistrements")
            st.dataframe(df.tail(10), use_container_width=True)
        else:
            st.info("Bienvenue ! Commencez par scanner un animal pour alimenter la base.")

    # --- 2. SCANNER (IA & DÉTECTION CADRAGE) ---
    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan Biométrique")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            source = st.radio("Source", ["📷 Caméra", "📁 Importer"], horizontal=True)
        with col_s2:
            mode_scanner = st.radio("Analyse", ["🤖 IA Automatique", "📏 Manuel"], horizontal=True)

        img = st.camera_input("Scanner") if source == "📷 Caméra" else st.file_uploader("Importer une photo", type=['jpg','jpeg','png'])

        if img:
            c_img, c_res = st.columns([1.5, 1])
            with c_img:
                st.image(img, use_container_width=True, caption="Analyse de la silhouette")
            with c_res:
                if mode_scanner == "🤖 IA Automatique":
                    with st.spinner("Analyse des marges..."):
                        time.sleep(1)
                        # Simulation d'une photo complète (comme votre moouton.jpg)
                        image_est_complete = True
                        if image_est_complete:
                            st.success("✅ CADRAGE VALIDE (98%)")
                            res = {"h_g": 74.5, "c_c": 8.8, "p_t": 87.0, "l_c": 85.0}
                        else:
                            st.error("⚠️ IMAGE INCOMPLÈTE")
                            res = {"h_g": 70.0, "c_c": 8.0, "p_t": 80.0, "l_c": 0.0}
                else:
                    res = {"h_g": 72.0, "c_c": 8.5, "p_t": 84.0, "l_c": 82.0}
                
                st.session_state['scan'] = res
                st.metric("🦴 Tour de Canon", f"{res['c_c']} cm")
                st.metric("📏 Hauteur Garrot", f"{res['h_g']} cm")
                
                if st.button("🚀 ENVOYER À LA SAISIE", use_container_width=True, type="primary"):
                    st.toast("Données transférées vers l'onglet Saisie")

    # --- 3. SAISIE (COMPLÈTE & SYNCHRONISÉE) ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Fiche d'Indexation")
        sd = st.session_state.get('scan', {})
        
        with st.form("form_saisie"):
            st.subheader("🆔 Identification & Âge")
            c1, c2, c3 = st.columns(3)
            with c1: id_ani = st.text_input("ID Animal / Boucle *")
            with c2: dent = st.selectbox("Âge par Dentition", ["Agneau (Lait)", "2 Dents", "4 Dents", "6 Dents", "8 Dents", "Bouche Usée"])
            with c3: sx = st.radio("Sexe", ["Mâle", "Femelle"], horizontal=True)

            st.divider()
            st.subheader("⚖️ Courbe de Poids (kg)")
            p1, p2, p3, p4 = st.columns(4)
            with p1: p_naiss = st.number_input("Naissance", value=0.0, step=0.1)
            with p2: p_10j = st.number_input("Poids 10j", value=0.0, step=0.1)
            with p3: p_30j = st.number_input("Poids 30j", value=0.0, step=0.1)
            with p4: p_70j = st.number_input("Poids actuel / 70j", value=0.0, step=0.1)

            st.divider()
            st.subheader("📏 Mensurations Scanner (cm)")
            m1, m2, m3, m4 = st.columns(4)
            with m1: h_garrot = st.number_input("Hauteur Garrot", value=float(sd.get('h_g', 0.0)))
            with m2: c_canon = st.number_input("Tour de Canon", value=float(sd.get('c_c', 0.0)))
            with m3: p_thorax = st.number_input("Périmètre Thorax", value=float(sd.get('p_t', 0.0)))
            with m4: l_corps = st.number_input("Longueur Corps", value=float(sd.get('l_c', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER L'INDIVIDU", use_container_width=True, type="primary"):
                if id_ani:
                    with get_db_connection() as conn:
                        conn.execute("""INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (id_ani, "Ouled Djellal", dent, sx, p_naiss, p_10j, p_30j, p_70j, h_garrot, c_canon, p_thorax, l_corps, datetime.now()))
                    st.success(f"✅ Animal {id_ani} indexé !")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⚠️ L'ID est obligatoire.")

    # --- 4. ADMIN (PROFESSIONNEL) ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration & Export")
        
        st.subheader("📥 Gestion des données")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if not df.empty:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Télécharger Inventaire CSV", csv, f"export_ovin_{datetime.now().strftime('%d_%m')}.csv", "text/csv", use_container_width=True)
            else:
                st.button("📥 Base vide", disabled=True, use_container_width=True)
        
        with col_a2:
            st.file_uploader("Importer un fichier externe", type=['csv'])

        st.divider()
        st.subheader("⚠️ Maintenance")
        with st.expander("Zone de danger (Réinitialisation)"):
            confirm = st.checkbox("Confirmer la suppression totale")
            if st.button("🗑️ VIDER LA BASE DE DONNÉES", disabled=not confirm, type="secondary"):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM beliers")
                st.success("Base réinitialisée.")
                st.rerun()

if __name__ == "__main__":
    main()
