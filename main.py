import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager
import time

# ==========================================
# CONFIGURATION & BASE DE DONNÉES
# ==========================================
DB_NAME = "expert_ovin_pro.db"

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
            id TEXT PRIMARY KEY, race TEXT, p10 REAL, p30 REAL, p70 REAL,
            h_garrot REAL, l_corps REAL, p_thoracique REAL, c_canon REAL,
            pct_muscle REAL, pct_gras REAL, pct_os REAL, gras_mm REAL,
            smld REAL, ic REAL, indice_s90 REAL, classe_europ TEXT,
            anomalie INTEGER, alerte TEXT)''')

# ==========================================
# MOTEUR DE CALCUL EXPERT (LOGIQUE MÉTIER)
# ==========================================
def calculer_tout_profil(row):
    """Calcule l'ensemble des indicateurs Écho-like et Morphologiques"""
    h, t, c, p70 = row['h_garrot'], row['p_thoracique'], row['c_canon'], row['p70']
    
    # 1. Indice de Conformation (IC)
    ic = (t / h * 100) if h > 0 else 0
    
    # 2. Estimation Écho-like (Modèles prédictifs)
    gras_mm = max(2.0, (p70 * 0.15) + (t * 0.05) - 8.0)
    smld = max(10.0, (ic * 0.8) + (p70 * 0.2)) # Surface Muscle Longissimus Dorsi
    
    # 3. Composition Centésimale
    pct_muscle = round(55 + (ic * 0.1) - (gras_mm * 0.3), 1)
    pct_gras = round((gras_mm * 1.2) + 5, 1)
    pct_os = 12.0 # Valeur standard
    
    # 4. Classement EUROP & S90
    if ic > 130: classe = "E (Excellent)"
    elif ic > 120: classe = "U (Très Supérieur)"
    elif ic > 110: classe = "R (Bon)"
    else: classe = "O (Moyen)"
    
    s90 = (pct_muscle / pct_gras) * 10 if pct_gras > 0 else 0
    
    # 5. Détection Anomalies
    anomalie = 0
    alerte = ""
    if p70 > 0 and (t < 60 or h < 40):
        anomalie = 1
        alerte = "Dimensions incohérentes pour le poids"
        
    return {
        'pct_muscle': pct_muscle, 'pct_gras': pct_gras, 'pct_os': pct_os,
        'gras_mm': round(gras_mm, 1), 'smld': round(smld, 1), 'ic': round(ic, 2),
        'indice_s90': round(s90, 1), 'classe_europ': classe, 
        'anomalie': anomalie, 'alerte': alerte
    }

# ==========================================
# INTERFACE STREAMLIT
# ==========================================
def main():
    st.set_page_config(page_title="Expert Ovin Pro AI", layout="wide", page_icon="🐏")
    init_db()

    # Sidebar
    st.sidebar.title("💎 Expert Ovin Pro")
    menu = st.sidebar.radio("Navigation", [
        "📊 Dashboard", 
        "📸 Scanner IA (1m)", 
        "🥩 Composition (Écho-like)", 
        "⚖️ Comparateur Elite",
        "✍️ Saisie & Mesures",
        "🔍 Contrôle Qualité",
        "📈 Stats & Analyse"
    ])

    with get_db_connection() as conn:
        df = pd.read_sql("SELECT * FROM beliers", conn)

    # --- MODULE SCANNER IA ---
    if menu == "📸 Scanner IA (1m)":
        st.title("📸 Scanner Morphologique IA")
        up = st.file_uploader("Importer une photo (Standard 1m)", type=['jpg', 'png'])
        if up:
            st.image(up, width=400)
            if st.button("🚀 Lancer l'analyse"):
                with st.spinner("Analyse des pixels..."):
                    time.sleep(1)
                    # Simulation détection via étalon 1m
                    res = {'h_garrot': 72.5, 'l_corps': 81.0, 'p_thoracique': 88.5, 'c_canon': 8.2}
                    st.session_state['last_scan'] = res
                    st.success("✅ Mesures extraites !")
                    st.json(res)

    # ==========================================
    # BLOC À INTÉGRER DANS VOTRE MENU COMPOSITION
    # ==========================================
    elif menu == "🥩 Composition":
        st.title("🥩 Diagnostic Tissulaire (Substitut Échographique)")
        
        if df.empty:
            st.info("Veuillez d'abord enregistrer un animal dans la section Saisie.")
        else:
            # 1. Sélection de l'animal
            target = st.selectbox("Sélectionner l'animal à diagnostiquer", df['id'].unique())
            subj = df[df['id'] == target].iloc[0]

            # 2. Moteur de calcul (Substitution Écho)
            # On utilise le périmètre thoracique (PT), la hauteur (HG) et le canon (CC)
            pt = float(subj.get('p_thoracique', 0))
            hg = float(subj.get('h_garrot', 0))
            cc = float(subj.get('c_canon', 0))
            p70 = float(subj.get('p70', 0))

            # Calculs prédictifs
            ic = (pt / hg * 100) if hg > 0 else 0
            gras_mm = max(1.5, (pt * 0.12) + (p70 * 0.05) - (hg * 0.1)) # Simulation épaisseur gras
            pct_muscle = round(52 + (ic * 0.15) - (cc * 0.4), 1)
            pct_gras = round((gras_mm * 1.5) + 4, 1)
            pct_os = round(100 - pct_muscle - pct_gras, 1)
            rendement = round(42 + (ic * 0.1), 1)

            # 3. Affichage visuel Écho-Like
            st.divider()
            col1, col2, col3 = st.columns([1, 1, 1])

            with col1:
                st.subheader("📟 Sonde Virtuelle")
                # Jauge d'épaisseur de gras (comme sur un écran d'écho)
                fig_gras = go.Figure(go.Indicator(
                    mode="gauge+number", value=gras_mm,
                    title={'text': "Épaisseur Gras (mm)"},
                    gauge={'axis': {'range': [0, 20]}, 
                           'bar': {'color': "#E65100"},
                           'steps': [{'range': [0, 5], 'color': "#C8E6C9"},
                                     {'range': [5, 12], 'color': "#FFF9C4"}]}))
                fig_gras.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                st.plotly_chart(fig_gras, use_container_width=True)
                
                st.metric("Rendement Estimé", f"{rendement} %")

            with col2:
                st.subheader("🧱 Tissus (Dissection)")
                # Graphique en secteurs pour la viande
                fig_pie = px.pie(
                    values=[pct_muscle, pct_gras, pct_os],
                    names=['Muscle (Viande)', 'Gras', 'Os'],
                    color_discrete_sequence=['#2E7D32', '#FFA000', '#757575'],
                    hole=0.4
                )
                fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_pie, use_container_width=True)

            with col3:
                st.subheader("📋 Expertise")
                # Calcul du Score de Sélection
                score_elite = round((pct_muscle * 1.2) + (rendement * 0.8) - (cc * 2), 1)
                
                st.markdown(f"""
                <div style="background-color: #f1f8e9; padding: 15px; border-radius: 10px; border-left: 5px solid #2E7D32;">
                    <h2 style="margin:0; color: #1B5E20;">{score_elite}/100</h2>
                    <p style="margin:0; font-weight: bold;">NOTE DE SÉLECTION</p>
                    <hr>
                    <b>Morphologie :</b> {'Compacte' if ic > 115 else 'Longiligne'}<br>
                    <b>Ossature :</b> {'Fine (Idéal)' if cc < 8.5 else 'Lourde'}<br>
                    <b>Potentiel :</b> {'⭐ ÉLITE' if score_elite > 75 else 'Standard'}
                </div>
                """, unsafe_allow_html=True)

            # 4. Comparatif Radar (La structure visuelle que vous aimiez)
            st.divider()
            st.subheader("📈 Profil Biométrique Complet")
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=[pct_muscle, rendement, ic, p70],
                theta=['Muscle %', 'Rendement %', 'Compacité', 'Poids'],
                fill='toself', line_color='#2E7D32'
            ))
            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 130])))
            st.plotly_chart(fig_radar, use_container_width=True)

    # --- MODULE COMPARATEUR ---
    elif menu == "⚖️ Comparateur Elite":
        st.title("⚖️ Comparaison Duale")
        if len(df) >= 2:
            c1, c2 = st.columns(2)
            id1 = c1.selectbox("Animal A", df['id'].tolist(), index=0)
            id2 = c2.selectbox("Animal B", df['id'].tolist(), index=1)
            
            # Radar Chart de comparaison
            categories = ['Muscle %', 'Gras %', 'Indice Conformation', 'Poids J70']
            fig_radar = go.Figure()
            for aid in [id1, id2]:
                row = df[df['id'] == aid].iloc[0]
                fig_radar.add_trace(go.Scatterpolar(
                    r=[row['pct_muscle'], row['pct_gras']*2, row['ic'], row['p70']],
                    theta=categories, fill='toself', name=f"ID: {aid}"
                ))
            st.plotly_chart(fig_radar, use_container_width=True)
        else:
            st.warning("Il faut au moins 2 animaux.")

    # --- MODULE SAISIE ---
    elif menu == "✍️ Saisie & Mesures":
        st.title("✍️ Nouvel Enregistrement")
        scan = st.session_state.get('last_scan', {})
        with st.form("saisie_form"):
            c1, c2 = st.columns(2)
            with c1:
                id_a = st.text_input("Identifiant Animal *")
                race = st.selectbox("Race", ["Ouled Djellal", "Rembi", "Hamra"])
                p30 = st.number_input("Poids J30 (kg)", 0.0)
                p70 = st.number_input("Poids J70 (kg)", 0.0)
            with c2:
                h = st.number_input("H. Garrot (cm)", value=scan.get('h_garrot', 0.0))
                t = st.number_input("P. Thorax (cm)", value=scan.get('p_thoracique', 0.0))
                c = st.number_input("T. Canon (cm)", value=scan.get('c_canon', 0.0))
            
            if st.form_submit_button("💾 Calculer et Sauvegarder"):
                if id_a:
                    res = calculer_tout_profil({'h_garrot': h, 'p_thoracique': t, 'c_canon': c, 'p70': p70})
                    with get_db_connection() as conn:
                        conn.execute('''INSERT OR REPLACE INTO beliers 
                        (id, race, p30, p70, h_garrot, p_thoracique, c_canon, 
                        pct_muscle, pct_gras, pct_os, gras_mm, smld, ic, indice_s90, classe_europ, anomalie, alerte)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (id_a, race, p30, p70, h, t, c, 
                         res['pct_muscle'], res['pct_gras'], res['pct_os'], res['gras_mm'], 
                         res['smld'], res['ic'], res['indice_s90'], res['classe_europ'], res['anomalie'], res['alerte']))
                    st.success(f"Animal {id_a} enregistré avec succès !")
                else: st.error("ID requis.")

    # --- MODULE CONTRÔLE QUALITÉ ---
    elif menu == "🔍 Contrôle Qualité":
        st.title("🔍 Validation des Données")
        anomalies = df[df['anomalie'] == 1]
        if not anomalies.empty:
            st.error(f"⚠️ {len(anomalies)} mesures suspectes détectées")
            st.dataframe(anomalies[['id', 'p70', 'alerte']])
        else:
            st.success("✅ Aucune anomalie détectée sur le troupeau.")

    # --- MODULE STATS ---
    elif menu == "📈 Stats & Analyse":
        st.title("📈 Analyse Scientifique")
        if len(df) > 2:
            tab1, tab2 = st.tabs(["Corrélations", "Prédictions"])
            with tab1:
                corr = df[['p70', 'gras_mm', 'pct_muscle', 'ic']].corr()
                st.plotly_chart(px.imshow(corr, text_auto=True), use_container_width=True)
            with tab2:
                p_test = st.slider("Simuler Poids (kg)", 20, 60, 35)
                st.write(f"Estimation Gras : {round(2.5 + (p_test * 0.15), 1)} mm")
        else:
            st.info("Données insuffisantes pour les statistiques.")

    elif menu == "⚙️ Admin":
        if st.button("Réinitialiser la base"):
            with get_db_connection() as conn: conn.execute("DELETE FROM beliers")
            st.rerun()

if __name__ == "__main__":
    main()
