import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import random

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v3", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .report-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e0e0e0; }
    .ai-box { background-color: #e3f2fd; padding: 15px; border-radius: 10px; border-left: 5px solid #1976d2; }
    .metric-val { color: #2E7D32; font-weight: bold; font-size: 20px; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_recherche.db"

# ==========================================
# 2. MOTEUR DE CALCUL & PRÉDICTION
# ==========================================
def moteur_zootechnique(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        if p70 <= 0: return pd.Series(res)
        
        # Calculs de base
        if p70 > p30 > 0: res['GMD'] = round(((p70 - p30) / 40) * 1000)
        res['IC'] = round((pt / (cc * hg)) * 1000, 2)
        if res['GMD'] > 0:
            res['ICA'] = round(max(2.5, min(8.0, 3.2 + (1450 / res['GMD']) - (res['IC'] / 200))), 2)

        # Echo-Composition
        egd = 1.2 + (p70 * 0.15) + (res['IC'] * 0.05) - (hg * 0.03)
        res['Gras'] = round(max(5.0, 4.0 + (egd * 1.8)), 1)
        res['Muscle'] = round(min(75.0, 81.0 - (res['Gras'] * 0.6) + (res['IC'] * 0.1)), 1)
        res['Os'] = round(100 - res['Muscle'] - res['Gras'], 1)
        return pd.Series(res)
    except: return pd.Series(res)

def load_data():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        metrics = df.apply(moteur_zootechnique, axis=1)
        df = pd.concat([df, metrics], axis=1)
    return df

# ==========================================
# 3. BLOC : ECHO-COMPOSITION & COMPARATEUR
# ==========================================
def view_echo_composition(df):
    st.title("🥩 Echo-Like & Comparateur Individuel")
    
    if df.empty:
        st.warning("Veuillez d'abord indexer des animaux.")
        return

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1: id1 = st.selectbox("Sélectionner l'animal A", df['id'].unique(), key="a")
    with col_sel2: id2 = st.selectbox("Sélectionner l'animal B (Comparaison)", df['id'].unique(), key="b")

    c1, c2 = st.columns(2)
    for i, target_id in enumerate([id1, id2]):
        subj = df[df['id'] == target_id].iloc[0]
        with [c1, c2][i]:
            st.subheader(f"Sujet : {target_id}")
            fig = go.Figure(data=[go.Pie(labels=['Viande (Muscle)', 'Gras', 'Os'], 
                                        values=[subj['Muscle'], subj['Gras'], subj['Os']],
                                        hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(f"""
            **Diagnostic :** - Rendement Viande : <span class='metric-val'>{subj['Muscle']}%</span>  
            - Indice de Gras : <span class='metric-val'>{subj['Gras']}%</span>  
            - Compacité (IC) : <span class='metric-val'>{subj['IC']}</span>
            """, unsafe_allow_html=True)

# ==========================================
# 4. BLOC : SIMULATEUR NUTRITIONNEL IA
# ==========================================
def view_nutrition_ia(df):
    st.title("🥗 Assistant Nutritionniste IA")
    
    target_id = st.selectbox("Choisir l'animal à optimiser", df['id'].unique())
    subj = df[df['id'] == target_id].iloc[0]
    
    st.divider()
    col_sim, col_res = st.columns([1, 1])
    
    with col_sim:
        st.subheader("⚙️ Simulation de Ration")
        st.write("Ajustez les curseurs pour voir l'impact sur la composition carcasse.")
        
        energie = st.slider("Niveau Énergie (UFL)", 0.6, 1.2, 0.9, 0.05)
        proteine = st.slider("Protéines (PDI g/j)", 80, 150, 110, 5)
        duree = st.number_input("Durée de la nouvelle ration (jours)", 15, 60, 30)

        # Logique de prédiction simplifiée (Modèle de simulation)
        delta_gmd = (energie - 0.9) * 200 + (proteine - 110) * 0.5
        nouveau_gmd = max(100, subj['GMD'] + delta_gmd)
        nouveau_gras = subj['Gras'] + (energie - 0.9) * 10
        nouveau_muscle = subj['Muscle'] + (proteine - 110) * 0.08
        
    with col_res:
        st.subheader("📈 Prédiction à J+" + str(duree))
        st.info(f"Avec cette ration, le GMD passerait de **{subj['GMD']}g/j** à **{nouveau_gmd:.0f}g/j**.")
        
        # Graphique comparatif
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Actuel', x=['Muscle', 'Gras'], y=[subj['Muscle'], subj['Gras']], marker_color='#81c784'))
        fig.add_trace(go.Bar(name='Prédit', x=['Muscle', 'Gras'], y=[nouveau_muscle, nouveau_gras], marker_color='#2e7d32'))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='ai-box'><b>💡 Conseil de l'IA :</b> L'animal montre une excellente réponse aux protéines. Pour augmenter le rendement carcasse sans excès de gras, maintenez l'énergie à 0.95 UFL et augmentez le tourteau de soja de 10%.</div>", unsafe_allow_html=True)

# ==========================================
# 5. NAVIGATION PRINCIPALE
# ==========================================
def main():
    df = load_data()
    
    st.sidebar.title("💎 Expert Ovin Pro")
    menu = st.sidebar.radio("Navigation", 
        ["🏠 Dashboard", "🥩 Echo-Composition", "🥗 Nutrition IA", "📊 Statistiques", "✍️ Indexation", "🔧 Admin"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Performance Troupeau")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("GMD Moyen", f"{df['GMD'].mean():.0f} g/j")
            c2.metric("Muscle Moyen", f"{df['Muscle'].mean():.1f}%")
            c3.metric("Efficience (ICA)", f"{df['ICA'].mean():.2f}")
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'Gras', 'ICA']], use_container_width=True)

    elif menu == "🥩 Echo-Composition": view_echo_composition(df)
    elif menu == "🥗 Nutrition IA": view_nutrition_ia(df)
    elif menu == "📊 Statistiques":
        st.title("📊 Analyse de Corrélation")
        fig = px.scatter(df, x="GMD", y="Muscle", color="Gras", size="p70", hover_name="id", trendline="ols")
        st.plotly_chart(fig, use_container_width=True)
    
    elif menu == "✍️ Indexation":
        # Formulaire simplifié pour l'exemple
        with st.form("index"):
            id_a = st.text_input("ID Animal")
            p30, p70 = st.number_input("Poids 30j"), st.number_input("Poids 70j")
            hg, cc, pt = st.number_input("H. Garrot"), st.number_input("T. Canon"), st.number_input("P. Thorax")
            if st.form_submit_button("Enregistrer"):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_a, "O.Djellal"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_a, p30, p70, hg, cc, pt))
                st.rerun()

if __name__ == "__main__":
    main()
