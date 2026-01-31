import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import io
import random

# ==========================================
# 1. CONFIGURATION & DESIGN
# ==========================================
st.set_page_config(page_title="Expert Selector Pro v3.5", layout="wide", page_icon="🐏")

st.markdown("""
    <style>
    .report-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border: 1px solid #e0e0e0; }
    .ai-advice { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2e7d32; }
    .vs-badge { font-size: 24px; font-weight: bold; color: #d32f2f; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = "expert_ovin_recherche.db"

# ==========================================
# 2. GESTION DATA & CALCULS
# ==========================================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS beliers (
            id TEXT PRIMARY KEY, race TEXT, sexe TEXT, dentition TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS mesures (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_animal TEXT NOT NULL,
            p30 REAL, p70 REAL, h_garrot REAL, c_canon REAL, p_thoracique REAL,
            FOREIGN KEY (id_animal) REFERENCES beliers(id))''')

def moteur_calcul_expert(row):
    res = {'Muscle': 0.0, 'Gras': 0.0, 'Os': 0.0, 'GMD': 0, 'ICA': 0.0, 'IC': 0.0}
    try:
        p70, p30 = float(row.get('p70') or 0), float(row.get('p30') or 0)
        hg, pt, cc = float(row.get('h_garrot') or 75), float(row.get('p_thoracique') or 90), float(row.get('c_canon') or 9)
        if p70 <= 0: return pd.Series(res)
        
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
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT b.*, m.p30, m.p70, m.h_garrot, m.c_canon, m.p_thoracique FROM beliers b LEFT JOIN mesures m ON b.id = m.id_animal", conn)
    if not df.empty:
        df = df.drop_duplicates(subset=['id'])
        metrics = df.apply(moteur_calcul_expert, axis=1)
        df = pd.concat([df, metrics], axis=1)
    return df

# ==========================================
# 3. BLOC : ECHO-COMPOSITION & COMPARATEUR
# ==========================================
def view_echo_composition(df):
    st.title("🥩 Echo-Like & Comparateur de Carcasse")
    if df.empty:
        st.info("Ajoutez des animaux pour comparer.")
        return

    col_a, col_vs, col_b = st.columns([4, 1, 4])
    
    with col_a:
        id_a = st.selectbox("Animal A", df['id'].unique(), key="sel_a")
        subj_a = df[df['id'] == id_a].iloc[0]
        fig_a = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj_a['Muscle'], subj_a['Gras'], subj_a['Os']], hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
        st.plotly_chart(fig_a, use_container_width=True)
        st.metric("Muscle A", f"{subj_a['Muscle']}%")

    with col_vs:
        st.markdown("<br><br><br><div class='vs-badge'>VS</div>", unsafe_allow_html=True)

    with col_b:
        id_b = st.selectbox("Animal B", df['id'].unique(), key="sel_b")
        subj_b = df[df['id'] == id_b].iloc[0]
        fig_b = go.Figure(data=[go.Pie(labels=['Muscle', 'Gras', 'Os'], values=[subj_b['Muscle'], subj_b['Gras'], subj_b['Os']], hole=.4, marker_colors=['#2E7D32', '#FBC02D', '#D32F2F'])])
        st.plotly_chart(fig_b, use_container_width=True)
        st.metric("Muscle B", f"{subj_b['Muscle']}%")

    st.divider()
    st.subheader("📊 Comparaison Biométrique")
    comp_df = pd.DataFrame({
        "Critère": ["GMD (g/j)", "ICA (Efficience)", "Compacité (IC)", "Gras (%)"],
        id_a: [subj_a['GMD'], subj_a['ICA'], subj_a['IC'], subj_a['Gras']],
        id_b: [subj_b['GMD'], subj_b['ICA'], subj_b['IC'], subj_b['Gras']]
    })
    st.table(comp_df)

# ==========================================
# 4. BLOC : NUTRITIONNISTE IA
# ==========================================
def view_nutrition_ia(df):
    st.title("🥗 Nutritionniste IA & Simulateur de Ration")
    if df.empty: return

    target = st.selectbox("Individu à optimiser", df['id'].unique(), key="nut_target")
    subj = df[df['id'] == target].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⚙️ Paramètres de la Ration")
        energie = st.slider("Apport Énergie (UFL)", 0.6, 1.3, 0.9, 0.05)
        proteine = st.slider("Apport Protéines (PDI g/j)", 80, 160, 110, 5)
        
        # Simulation mathématique (IA simplifiée)
        delta_muscle = (proteine - 110) * 0.05 + (energie - 0.9) * 2
        delta_gras = (energie - 0.9) * 15
        
        new_muscle = max(40, min(75, subj['Muscle'] + delta_muscle))
        new_gras = max(5, min(35, subj['Gras'] + delta_gras))

    with col2:
        st.subheader("🔮 Projection de l'IA")
        fig_sim = go.Figure()
        fig_sim.add_trace(go.Bar(name='Actuel', x=['Muscle', 'Gras'], y=[subj['Muscle'], subj['Gras']], marker_color='#A5D6A7'))
        fig_sim.add_trace(go.Bar(name='Prédit (Nouvelle Ration)', x=['Muscle', 'Gras'], y=[new_muscle, new_gras], marker_color='#2E7D32'))
        st.plotly_chart(fig_sim, use_container_width=True)

    st.markdown(f"""
    <div class='ai-advice'>
    <b>💡 Conseil du Nutritionniste IA :</b><br>
    Pour le sujet {target}, l'augmentation des protéines à {proteine}g/j favorisera le dépôt de muscle squelettique. 
    Attention, avec {energie} UFL, vous risquez une augmentation du gras dorsal de {delta_gras:.1f}%.
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 5. NAVIGATION & MAIN
# ==========================================
def main():
    df = load_data()
    st.sidebar.title("💎 EXPERT OVIN PRO")
    menu = st.sidebar.radio("Navigation", ["🏠 Dashboard", "🥩 Echo-Composition", "🥗 Nutritionniste IA", "📊 Statistiques", "✍️ Indexation", "💾 Data Mgmt"])

    if menu == "🏠 Dashboard":
        st.title("🏆 Performance du Troupeau")
        if not df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("GMD Moyen", f"{df['GMD'].mean():.0f} g/j")
            c2.metric("Muscle Moyen", f"{df['Muscle'].mean():.1f}%")
            c3.metric("ICA Global", f"{df['ICA'].mean():.2f}")
            st.dataframe(df[['id', 'sexe', 'GMD', 'Muscle', 'ICA']], use_container_width=True)

    elif menu == "🥩 Echo-Composition": view_echo_composition(df)
    elif menu == "🥗 Nutritionniste IA": view_nutrition_ia(df)
    elif menu == "📊 Statistiques":
        st.title("📊 Analyse de Corrélation Recherche")
        if not df.empty:
            fig = px.scatter(df, x="ICA", y="Muscle", color="Gras", size="p70", trendline="ols", title="Corrélation Efficience vs Musculature")
            st.plotly_chart(fig, use_container_width=True)

    elif menu == "✍️ Indexation":
        st.title("✍️ Saisie Biométrique")
        with st.form("index"):
            id_a = st.text_input("ID Animal")
            p30, p70 = st.number_input("Poids 30j"), st.number_input("Poids 70j")
            hg, cc, pt = st.number_input("H. Garrot"), st.number_input("T. Canon"), st.number_input("P. Thorax")
            if st.form_submit_button("💾 Sauvegarder"):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT OR REPLACE INTO beliers (id, race) VALUES (?,?)", (id_a, "O.Djellal"))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (id_a, p30, p70, hg, cc, pt))
                st.rerun()

    elif menu == "💾 Data Mgmt":
        st.title("💾 Gestion CSV")
        if not df.empty:
            st.download_button("📥 Exporter la Base complète (CSV)", df.to_csv(index=False).encode('utf-8'), "donnees_ovin.csv", "text/csv")
        file = st.file_uploader("📤 Importer un fichier CSV", type="csv")
        if file and st.button("Lancer Import"):
            idf = pd.read_csv(file)
            with sqlite3.connect(DB_NAME) as conn:
                for _, r in idf.iterrows():
                    conn.execute("INSERT OR REPLACE INTO beliers (id, sexe) VALUES (?,?)", (r['id'], r['sexe']))
                    conn.execute("INSERT INTO mesures (id_animal, p30, p70, h_garrot, c_canon, p_thoracique) VALUES (?,?,?,?,?,?)", (r['id'], r['p30'], r['p70'], r['h_garrot'], r['c_canon'], r['p_thoracique']))
            st.rerun()

if __name__ == "__main__":
    main()
