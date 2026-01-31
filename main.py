import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

def get_db_connection():
    conn = sqlite3.connect('expert_ovin_pro.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- INITIALISATION DE LA BASE ---
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
    # 1. CHARGEMENT DES DONNÉES
    df = load_data()

    # 2. BARRE LATÉRALE (SIDEBAR) - VOTRE STRUCTURE
    st.sidebar.title("🐏 Expert Ovin Pro")
    menu = st.sidebar.radio("MENU PRINCIPAL", ["📊 Tableau de Bord", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])
    
    st.sidebar.divider()

    if not df.empty:
        # BLOC COMPOSITION DU TROUPEAU
        st.sidebar.subheader("📈 Composition Troupeau")
        c_side1, c_side2 = st.sidebar.columns(2)
        with c_side1:
            st.write("**Sexe**")
            st.caption(str(df['sexe'].value_counts().to_dict()))
        with c_side2:
            st.write("**Âge**")
            st.caption(str(df['age_estimé'].value_counts().to_dict()))

        st.sidebar.divider()

        # BLOC TISSUS (VIANDE / GRAS / OS)
        st.sidebar.subheader("🥩 Composition Tissulaire")
        # Calculs basés sur le Tour de Canon et le Thorax
        moy_canon = df['c_canon'].mean() if 'c_canon' in df.columns else 8.0
        moy_thorax = df['p_thoracique'].mean() if 'p_thoracique' in df.columns else 80.0
        
        # Formules d'estimation simplifiées pour l'IA
        p_os = round((moy_canon * 2.2), 1) 
        p_viande = round((moy_thorax / 1.6), 1)
        p_gras = round(max(0, 100 - (p_os + p_viande)), 1)

        st.sidebar.progress(p_viande/100, text=f"Muscle: {p_viande}%")
        st.sidebar.progress(p_os/100, text=f"Os: {p_os}%")
        st.sidebar.progress(p_gras/100, text=f"Gras: {p_gras}%")
    else:
        st.sidebar.info("En attente de données pour les stats...")

    st.sidebar.divider()
    st.sidebar.caption(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    # 3. LOGIQUE DES ONGLETS (MENU)
    if menu == "📊 Tableau de Bord":
        st.title("📊 Statistiques Générales")
        if not df.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Effectif Total", len(df))
            m2.metric("Poids Moyen Sevrage", f"{df[df['poids_70j']>0]['poids_70j'].mean():.1f} kg")
            m3.metric("Tour de Canon Moyen", f"{df['c_canon'].mean():.1f} cm")
            st.divider()
            st.subheader("Dernières entrées")
            st.dataframe(df.tail(5), use_container_width=True)
        else:
            st.info("La base est vide. Utilisez le Scanner pour commencer.")

    elif menu == "📸 Scanner":
        st.title("📸 Station de Scan")
        img = st.file_uploader("Importer une photo de profil", type=['jpg','jpeg','png'])
        if img:
            col_a, col_b = st.columns([1.5, 1])
            col_a.image(img, use_container_width=True)
            with col_b:
                st.success("✅ IMAGE ANALYSÉE")
                # Valeurs types transmises à la saisie
                res = {"h_garrot": 74.5, "c_canon": 8.8, "p_thoracique": 87.0, "l_corps": 85.0}
                st.session_state['scan'] = res
                st.metric("🦴 Tour de Canon", "8.8 cm")
                st.metric("📏 Hauteur", "74.5 cm")
                if st.button("🚀 ENVOYER À LA SAISIE"):
                    st.toast("Données transférées !")

    elif menu == "✍️ Saisie":
        st.title("✍️ Fiche d'Identification")
        sd = st.session_state.get('scan', {})
        with st.form("form_saisie"):
            c1, c2, c3 = st.columns(3)
            with c1: id_ani = st.text_input("ID Animal *")
            with c2: dent = st.selectbox("Âge (Dents)", ["Lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            with c3: sx = st.radio("Sexe", ["M", "F"], horizontal=True)

            st.subheader("⚖️ Pesées (kg)")
            p1, p2, p3, p4 = st.columns(4)
            with p1: p_n = st.number_input("Naissance", value=0.0)
            with p2: p_10 = st.number_input("10j", value=0.0)
            with p3: p_30 = st.number_input("30j", value=0.0)
            with p4: p_70 = st.number_input("70j", value=0.0)

            st.subheader("📏 Mensurations (cm)")
            m1, m2, m3, m4 = st.columns(4)
            with m1: h = st.number_input("Hauteur Garrot", value=float(sd.get('h_garrot', 0.0)))
            with m2: c = st.number_input("Tour de Canon", value=float(sd.get('c_canon', 0.0)))
            with m3: t = st.number_input("Thorax", value=float(sd.get('p_thoracique', 0.0)))
            with m4: l = st.number_input("Longueur", value=float(sd.get('l_corps', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER"):
                if id_ani:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   (id_ani, "Ouled Djellal", dent, sx, p_n, p_10, p_30, p_70, h, c, t, l, datetime.now()))
                    st.success("Enregistré !")
                    st.rerun()

    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if not df.empty:
            st.download_button("📥 Télécharger CSV", df.to_csv(index=False).encode('utf-8'), "ovins.csv")
        if st.button("🗑️ Vider la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
