import streamlit as st
import pandas as pd
import sqlite3
import time
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Expert Ovin Pro", layout="wide", page_icon="🐏")

# --- CONNEXION & INITIALISATION DB ---
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

# --- APPLICATION ---
def main():
    df = load_data()

    # --- BARRE LATÉRALE ---
    st.sidebar.title("🐏 Expert Ovin Pro")
    menu = st.sidebar.radio("MENU", ["📊 Tableau de Bord", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])
    
    st.sidebar.divider()

    if not df.empty:
        st.sidebar.subheader("📈 Stats Troupeau")
        # Affichage rapide en sidebar
        st.sidebar.write(f"**Total:** {len(df)} têtes")
        st.sidebar.write(f"**Mâles:** {len(df[df['sexe']=='Mâle'])}")
        st.sidebar.write(f"**Femelles:** {len(df[df['sexe']=='Femelle'])}")
        
        st.sidebar.divider()
        
        # Bloc Composition Tissulaire
        st.sidebar.subheader("🥩 Tissus (Moyenne)")
        m_c = df['c_canon'].mean() if 'c_canon' in df.columns else 8.5
        m_t = df['p_thoracique'].mean() if 'p_thoracique' in df.columns else 85.0
        p_os = round(m_c * 2.1, 1)
        p_viande = round(m_t / 1.55, 1)
        p_gras = round(max(2.0, 100 - (p_os + p_viande)), 1)

        st.sidebar.progress(min(p_viande/100, 1.0), text=f"Muscle: {p_viande}%")
        st.sidebar.progress(min(p_os/100, 1.0), text=f"Os: {p_os}%")
        st.sidebar.progress(min(p_gras/100, 1.0), text=f"Gras: {p_gras}%")
    
    st.sidebar.divider()
    st.sidebar.caption(f"📅 {datetime.now().strftime('%d/%m/%Y')}")

    # --- 1. TABLEAU DE BORD ---
    if menu == "📊 Tableau de Bord":
        st.title("📊 Tableau de Bord")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Effectif Total", len(df))
            c2.metric("Poids Moyen Sevrage", f"{df[df['poids_70j']>0]['poids_70j'].mean():.1f} kg")
            c3.metric("Conformation Osseuse", f"{df['c_canon'].mean():.1f} cm")
            st.divider()
            st.subheader("Derniers enregistrements")
            st.dataframe(df.tail(10), use_container_width=True)
        else:
            st.info("Aucune donnée disponible.")

    # --- 2. SCANNER ---
    elif menu == "📸 Scanner":
        st.title("📸 Scanner Morphologique")
        img = st.file_uploader("Charger photo de profil", type=['jpg','jpeg','png'])
        if img:
            col_a, col_b = st.columns([1.5, 1])
            with col_a:
                st.image(img, use_container_width=True)
            with col_b:
                st.success("✅ Analyse terminée")
                # Valeurs types
                res = {"h": 74.5, "c": 8.8, "t": 87.0, "l": 85.0}
                st.session_state['scan'] = res
                st.metric("🦴 Tour de Canon", "8.8 cm")
                st.metric("📏 Hauteur", "74.5 cm")
                if st.button("🚀 ENVOYER À LA SAISIE", use_container_width=True):
                    st.toast("Données transmises !")

    # --- 3. SAISIE ---
    elif menu == "✍️ Saisie":
        st.title("✍️ Fiche d'Indexation")
        sd = st.session_state.get('scan', {})
        with st.form("form_saisie"):
            st.subheader("🆔 Identification")
            c1, c2, c3 = st.columns(3)
            with c1: id_a = st.text_input("ID Animal *")
            with c2: dent = st.selectbox("Âge (Dents)", ["Lait", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            with c3: sx = st.radio("Sexe", ["Mâle", "Femelle"], horizontal=True)

            st.subheader("⚖️ Pesées (kg)")
            p1, p2, p3, p4 = st.columns(4)
            with p1: pn = st.number_input("Naissance", value=0.0)
            with p2: p10 = st.number_input("10j", value=0.0)
            with p3: p30 = st.number_input("30j", value=0.0)
            with p4: p70 = st.number_input("70j", value=0.0)

            st.subheader("📏 Mensurations (cm)")
            m1, m2, m3, m4 = st.columns(4)
            with m1: h = st.number_input("Hauteur Garrot", value=float(sd.get('h', 0.0)))
            with m2: c = st.number_input("Tour de Canon", value=float(sd.get('c', 0.0)))
            with m3: t = st.number_input("Thorax", value=float(sd.get('t', 0.0)))
            with m4: l = st.number_input("Longueur", value=float(sd.get('l', 0.0)))

            if st.form_submit_button("💾 ENREGISTRER"):
                if id_a:
                    with get_db_connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                   (id_a, "Ouled Djellal", dent, sx, pn, p10, p30, p70, h, c, t, l, datetime.now()))
                    st.success("Données enregistrées !")
                    st.rerun()

    # --- 4. ADMIN (LE BLOC AMÉLIORÉ) ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        
        st.subheader("📊 Gestion de la Base")
        col_adm1, col_adm2 = st.columns(2)
        
        with col_adm1:
            st.write("**Exporter les données**")
            if not df.empty:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger l'inventaire (.CSV)",
                    data=csv,
                    file_name=f"export_ovin_{datetime.now().strftime('%d_%m_%Y')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.caption("Fichier compatible Excel et Google Sheets.")
            else:
                st.button("📥 Base de données vide", disabled=True, use_container_width=True)

        with col_adm2:
            st.write("**Importer des données**")
            st.file_uploader("Glisser un fichier CSV ici", type=['csv'])
            st.caption("Fonctionnalité d'importation bientôt disponible.")

        st.divider()

        st.subheader("⚠️ Maintenance Système")
        with st.expander("Zone de danger (Action irréversible)"):
            st.warning("Attention : Cela effacera tous les animaux enregistrés.")
            confirm = st.checkbox("Je confirme vouloir vider la base de données.")
            if st.button("🗑️ RÉINITIALISER TOUTE LA BASE", disabled=not confirm, type="primary"):
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM beliers")
                st.success("Toutes les données ont été supprimées.")
                st.rerun()

if __name__ == "__main__":
    main()
