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
# 1. CONFIGURATION & BASE DE DONNÉES
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v6.5", layout="wide")

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
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 2. LOGIQUE ZOOTECHNIQUE (ALGORITHMES)
# ==========================================
def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0, 'Volume': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc, lg = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9), float(row.get('l_corps') or 85)
        
        # GMD & Compacité (IC)
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        
        # Volume Corporel (Estimation Ellipsoïde)
        rayon = pt / (2 * np.pi)
        res['Volume'] = round((np.pi * (rayon**2) * lg) / 1000, 1) # en Litres

        # ICA & Echo-Composition
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
        # Score Expert Global (Pondéré)
        df['Score'] = round((df['Muscle']*0.4) + (df['GMD']/10*0.3) + (df['Volume']*0.1) + ((8-df['ICA'])*10), 1)
    return df

# ==========================================
# 3. COMPOSANTS GRAPHIQUES (RADAR & HISTO)
# ==========================================
def plot_radar(target_data, avg_data):
    categories = ['Muscle', 'GMD (Scaled)', 'Compacité', 'Volume', 'ICA (Inv)']
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=[target_data['Muscle'], target_data['GMD']/10, target_data['IC']/10, target_data['Volume']/2, (8-target_data['ICA'])*10],
        theta=categories, fill='toself', name=f"Individu {target_data['id']}", line_color='green'
    ))
    fig.add_trace(go.Scatterpolar(
        r=[avg_data['Muscle'], avg_data['GMD']/10, avg_data['IC']/10, avg_data['Volume']/2, (8-avg_data['ICA'])*10],
        theta=categories, fill='toself', name='Moyenne Troupeau', line_color='gray'
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True)
    return fig

def plot_distribution(df, target_val, column, label):
    fig = px.histogram(df, x=column, nbins=15, title=f"Positionnement : {label}", color_discrete_sequence=['#A5D6A7'])
    fig.add_vline(x=target_val, line_dash="dash", line_color="red", annotation_text="VOTRE ANIMAL")
    fig.update_layout(showlegend=False, height=300)
    return fig

# ==========================================
# 4. INTERFACE UTILISATEUR
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT SELECTOR PRO")
    menu = st.sidebar.radio("Menu", ["🏠 Dashboard", "📸 Scanner Dual", "✍️ Indexation", "📊 Comparaison Avancée", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("📊 Vue d'ensemble du Troupeau")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Effectif", len(df))
            c2.metric("Muscle Moyen", f"{df['Muscle'].mean():.1f} %")
            c3.metric("GMD Moyen", f"{df['GMD'].mean():.0f} g/j")
            st.dataframe(df[['id', 'sexe', 'dentition', 'Muscle', 'GMD', 'Volume', 'Score']], use_container_width=True)

    elif menu == "📸 Scanner Dual":
        st.title("📸 Station de Scan")
        mode = st.radio("Technologie", ["🤖 IA Intégrale (Auto)", "📏 Hybride (Étalon)"], horizontal=True)
        img = st.camera_input("Scanner l'animal de profil")
        if img:
            with st.spinner("Analyse photogrammétrique..."):
                time.sleep(1.5)
                # Logique : Pixel/cm basé sur étalon (simulation)
                res = {"h_garrot": 76.5, "c_canon": 9.1, "p_thoracique": 92.5, "l_corps": 88.0}
                st.session_state['last_scan'] = res
                st.success("✅ Analyse terminée. Prêt pour l'indexation.")
                st.json(res)

    elif menu == "✍️ Indexation":
        st.title("✍️ Saisie & Identification")
        scan = st.session_state.get('last_scan', {})
        with st.form("index"):
            c1, c2 = st.columns(2)
            id_a = c1.text_input("ID Animal *")
            dent = c1.selectbox("Dentition", ["Agneau", "2 Dents", "4 Dents", "6 Dents", "8 Dents"])
            sexe = c1.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"])
            hg = c2.number_input("Hauteur (cm)", value=float(scan.get('h_garrot', 75.0)))
            pt = c2.number_input("Thorax (cm)", value=float(scan.get('p_thoracique', 90.0)))
            lg = c2.number_input("Longueur (cm)", value=float(scan.get('l_corps', 85.0)))
            cc = c2.number_input("Canon (cm)", value=float(scan.get('c_canon', 9.0)))
            if st.form_submit_button("💾 Enregistrer"):
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_a, "O.Djellal", sexe, dent))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)", 
                                 (id_a, 15.0, 32.0, hg, cc, pt, lg))
                st.success("Animal enregistré !")

    elif menu == "📊 Comparaison Avancée":
        st.title("📊 Analyse Individuelle vs Population")
        if not df.empty:
            target = st.selectbox("Choisir un individu", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]
            avg = df.mean(numeric_only=True)

            col_radar, col_dist = st.columns([1, 1])
            with col_radar:
                st.subheader("🕸️ Équilibre Morphologique")
                st.plotly_chart(plot_radar(subj, avg), use_container_width=True)
            
            with col_dist:
                st.subheader("📈 Distribution du Muscle")
                st.plotly_chart(plot_distribution(df, subj['Muscle'], 'Muscle', 'Pourcentage de Muscle'), use_container_width=True)
                st.subheader("⚖️ Distribution du Volume")
                st.plotly_chart(plot_distribution(df, subj['Volume'], 'Volume', 'Volume Corporel (L)'), use_container_width=True)

    elif menu == "🔧 Admin":
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS (Ouled Djellal)"):
            with get_db_connection() as conn:
                for i in range(50):
                    id_t = f"OD-{random.randint(1000,9999)}"
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?)", (id_t, "O.Djellal", random.choice(["Bélier", "Brebis"]), "2 Dents"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique, l_corps) VALUES (?,?,?,?,?,?,?)", 
                                 (id_t, random.uniform(12,16), random.uniform(28,45), random.uniform(70,82), random.uniform(8.5,10.2), random.uniform(88,105), random.uniform(82,95)))
            st.rerun()

if __name__ == "__main__":
    main()
