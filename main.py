import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.graph_objects as go
from contextlib import contextmanager
import time
import random

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff; padding: 15px; border-radius: 12px;
        border: 1px solid #e0e0e0; border-top: 5px solid #2E7D32;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;
    }
    .metric-card h2 { color: #2E7D32; margin: 5px 0; font-size: 24px; }
    .analysis-box { 
        background-color: #f9fdf9; padding: 15px; border-radius: 10px; 
        border: 1px solid #c8e6c9; margin-bottom: 10px;
    }
    @media (prefers-color-scheme: dark) {
        .metric-card { background-color: #1E1E1E; border: 1px solid #333; }
        .analysis-box { background-color: #121212; border: 1px solid #2E7D32; }
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_pro.db"

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
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT, objectif TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL, l_corps REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id) ON DELETE CASCADE)''')

# ==========================================
# 3. LOGIQUE "ECHO-LIKE" & CALCULS
# ==========================================
def calculer_echo_metrics(row):
    try:
        p70 = float(row.get('p70') or 0)
        hg = float(row.get('h_garrot') or 75)
        pt = float(row.get('p_thoracique') or 90)
        cc = float(row.get('c_canon') or 9)
        
        if p70 < 5: return [0]*7 # Sécurité

        # Algorithme prédictif interne
        ic = (pt / (cc * hg)) * 1000
        gras_mm = 1.2 + (p70 * 0.14) + (ic * 0.07) - (hg * 0.04)
        pct_gras = max(8.0, 5.0 + (gras_mm * 1.6))
        pct_muscle = max(40.0, 78.0 - (pct_gras * 0.58) + (ic * 0.18))
        pct_os = 100 - pct_muscle - pct_gras
        rendement = pct_muscle + (pct_gras * 0.2) # Estimation carcasse
        
        return [round(pct_muscle, 1), round(pct_gras, 1), round(pct_os, 1), 
                round(ic, 1), round(gras_mm, 1), round(rendement, 1), "R"]
    except: return [0]*7

def load_data():
    with get_db_connection() as conn:
        df = pd.read_sql("""SELECT b.*, m.p70, m.h_garrot, m.c_canon, m.p_thoracique, m.l_corps 
                           FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal 
                           LEFT JOIN mesures m ON l.mid = m.id""", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        res = df.apply(lambda x: pd.Series(calculer_echo_metrics(x)), axis=1)
        df[['Muscle', 'Gras', 'Os', 'IC', 'Gras_mm', 'Rendement', 'Classe']] = res
        # Calcul Statut Elite (Top 15%)
        df['Score'] = (df['Muscle'] * 0.7) + (df['p70'] * 0.3)
        limit = df['Score'].quantile(0.85) if len(df) > 5 else 999
        df['Statut'] = np.where(df['Score'] >= limit, "⭐ ELITE PRO", "Standard")
    return df

# ==========================================
# 4. COMPOSANTS GRAPHIQUES
# ==========================================
def draw_echo_charts(subj, title=""):
    st.markdown(f"### {title} (ID: {subj['id']})")
    c1, c2 = st.columns(2)
    
    with c1:
        fig_pie = go.Figure(data=[go.Pie(labels=['Viande (Muscle)', 'Gras', 'Os'], 
                                       values=[subj['Muscle'], subj['Gras'], subj['Os']],
                                       hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
        fig_pie.update_layout(height=250, margin=dict(l=0, r=0, b=0, t=0), showlegend=True)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with c2:
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = subj['Gras_mm'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Gras Sous-cutané (mm)", 'font': {'size': 14}},
            gauge = {'axis': {'range': [0, 20]}, 'bar': {'color': "#2E7D32"}}))
        fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, b=20, t=40))
        st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown(f"""
    <div class='analysis-box'>
        <b>Rendement Viande :</b> {subj['Muscle']}% | <b>Indice Conformation :</b> {subj['IC']}<br>
        <b>Poids :</b> {subj['p70']} kg | <b>Sexe :</b> {subj['sexe']}
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 5. INTERFACE PRINCIPALE
# ==========================================
def main():
    init_db()
    df = load_data()

    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Echo-Composition", "📸 Scanner", "✍️ Saisie", "🔧 Admin"])

    # --- DASHBOARD ---
    if menu == "🏠 Dashboard":
        st.title("🏆 Tableau de Bord du Troupeau")
        if df.empty: st.info("Base vide. Allez dans Admin pour générer des données.")
        else:
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.markdown(f"<div class='metric-card'><p>Sujets</p><h2>{len(df)}</h2></div>", unsafe_allow_html=True)
            col_m2.markdown(f"<div class='metric-card'><p>Elite</p><h2>{len(df[df['Statut'] != 'Standard'])}</h2></div>", unsafe_allow_html=True)
            col_m3.markdown(f"<div class='metric-card'><p>Muscle Moyen</p><h2>{df['Muscle'].mean():.1f}%</h2></div>", unsafe_allow_html=True)
            col_m4.markdown(f"<div class='metric-card'><p>Poids Moyen</p><h2>{df['p70'].mean():.1f} kg</h2></div>", unsafe_allow_html=True)
            
            st.subheader("📋 Liste des individus")
            st.dataframe(df[['id', 'sexe', 'race', 'p70', 'Muscle', 'Statut']], use_container_width=True)

    # --- ECHO-COMPOSITION & COMPARATEUR ---
    elif menu == "🥩 Echo-Composition":
        st.title("🥩 Analyse Échographique Prédictive")
        if not df.empty:
            tab1, tab2 = st.tabs(["Analyse Individuelle", "🆚 Comparaison Côte à Côte"])
            
            with tab1:
                target = st.selectbox("Choisir un animal", df['id'].unique(), key="single")
                subj = df[df['id'] == target].iloc[0]
                draw_echo_charts(subj, "Détails de l'animal")

            with tab2:
                col_left, col_right = st.columns(2)
                with col_left:
                    t1 = st.selectbox("Animal A", df['id'].unique(), index=0)
                    draw_echo_charts(df[df['id'] == t1].iloc[0], "Sujet A")
                with col_right:
                    t2 = st.selectbox("Animal B", df['id'].unique(), index=min(1, len(df)-1))
                    draw_echo_charts(df[df['id'] == t2].iloc[0], "Sujet B")
        else: st.warning("Données absentes.")

  elif menu == "✍️ Saisie":
        st.title("✍️ Indexation et Identification")
        
        # Récupération des données du scanner
        sd = st.session_state.get('scan', {})
        
        with st.form("form_saisie"):
            # --- SECTION 1 : IDENTITÉ & ÂGE ---
            st.subheader("🆔 État Civil de l'Animal")
            c1, c2, c3 = st.columns(3)
            with c1:
                id_animal = st.text_input("N° Boucle / ID *")
            with c2:
                # Estimation par la dentition pour les adultes ou inconnus
                statut_dentaire = st.selectbox("État Dentaire (Âge estimé)", 
                    ["Agneau (Dents de lait)", "2 Dents (12-18 mois)", "4 Dents (2 ans)", 
                     "6 Dents (2.5 - 3 ans)", "8 Dents / Adulte (4 ans+)", "Bouche usée / Vieillard"])
            with c3:
                sexe = st.radio("Sexe", ["Bélier", "Brebis", "Agneau/elle"], horizontal=True)

            st.divider()

            # --- SECTION 2 : HISTORIQUE DE POIDS (Optionnel) ---
            st.subheader("⚖️ Historique de Pesée")
            st.caption("Laissez à 0.0 si l'historique est inconnu (nouvel individu)")
            cp1, cp2, cp3, cp4 = st.columns(4)
            with cp1:
                p_naiss = st.number_input("Poids Naissance", min_value=0.0, value=0.0, step=0.1)
            with cp2:
                p_10j = st.number_input("Poids à 10j", min_value=0.0, value=0.0, step=0.1)
            with cp3:
                p_30j = st.number_input("Poids à 30j", min_value=0.0, value=0.0, step=0.1)
            with cp4:
                p_70j = st.number_input("Poids actuel / 70j", min_value=0.0, value=0.0, step=0.1)

            st.divider()

            # --- SECTION 3 : BIOMÉTRIE (SCANNER) ---
            st.subheader("📏 Morphologie (Mesures Scanner)")
            cm1, cm2, cm3, cm4 = st.columns(4)
            with cm1:
                hauteur = st.number_input("Hauteur Garrot", value=float(sd.get('h_garrot', 0.0)), step=0.1)
            with cm2:
                # Notre fameux Tour de Canon
                canon = st.number_input("Tour de Canon", value=float(sd.get('c_canon', 0.0)), step=0.1)
            with cm3:
                thorax = st.number_input("Périmètre Thorax", value=float(sd.get('p_thoracique', 0.0)), step=0.1)
            with cm4:
                # Gestion du texte "Coupé" ou "Incertain" venant du scanner
                val_long = sd.get('l_corps', 0.0)
                longueur = st.number_input("Longueur Corps", value=float(val_long) if isinstance(val_long, (int, float)) else 0.0, step=0.1)

            submit = st.form_submit_button("💾 INDEXER L'INDIVIDU", type="primary", use_container_width=True)
            
            if submit:
                if id_animal:
                    st.success(f"✅ L'animal {id_animal} ({statut_dentaire}) a été ajouté à la base de données.")
                else:
                    st.warning("⚠️ L'ID est obligatoire pour l'indexation.")
    # --- ADMIN ---
    elif menu == "🔧 Admin":
        st.title("🔧 Administration")
        if st.button("🚀 GÉNÉRER 50 INDIVIDUS (MÉLANGE TEST)", use_container_width=True):
            with get_db_connection() as conn:
                for i in range(50):
                    id_a = f"DZ-2026-{random.randint(1000, 9999)}"
                    sx = random.choice(["Bélier", "Brebis", "Agneau", "Agnelle"])
                    hg, cc, pt, p70 = (random.uniform(70,85), random.uniform(8.5,10.5), random.uniform(85,115), random.uniform(60,105)) if "Agne" not in sx else (random.uniform(50,65), random.uniform(6.5,8), random.uniform(60,80), random.uniform(25,45))
                    conn.execute("INSERT OR REPLACE INTO beliers VALUES (?,?,?,?,?)", (id_a, "Ouled Djellal", sx, "Adulte", "Sélection"))
                    conn.execute("INSERT INTO mesures (id_animal, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?)", (id_a, p70, hg, cc, pt))
            st.success("50 individus ajoutés avec succès !")
            st.rerun()
        
        if st.button("🗑️ RESET TOTAL", type="primary", use_container_width=True):
            with get_db_connection() as conn:
                conn.execute("DELETE FROM mesures"); conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
