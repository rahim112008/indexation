import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# CONFIGURATION ET PROTECTION
# ==========================================
st.set_page_config(page_title="Expert Selector Pro", layout="wide", page_icon="🐏")
DB_NAME = "expert_ovin_pro.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ==========================================
# LOGIQUE MÉTIER SÉCURISÉE (ANTI-EXPLOSION)
# ==========================================
def safe_div(n, d):
    return n / d if d > 0 else 0

def calculer_composition_carcasse(row):
    """Formules stabilisées pour éviter les pourcentages délirants"""
    try:
        p70 = float(row.get('p70', 0))
        hg = float(row.get('h_garrot', 70))
        pt = float(row.get('p_thoracique', 80))
        cc = float(row.get('c_canon', 8.5))
        lc = float(row.get('l_corps', 80))
        lp = float(row.get('l_poitrine', 24))

        if p70 <= 5 or cc <= 2 or hg <= 10:
            return 0, 0, 0, 0, 0, "Inconnu", 0, 0

        # 1. Indice de Conformation (Stabilisé)
        ic_brut = safe_div(pt, (cc * hg)) * 1000
        ic = max(15, min(45, ic_brut)) # On borne entre 15 et 45

        # 2. Épaisseur de gras (en mm) - Modèle linéaire robuste
        gras_mm = 2.0 + (p70 * 0.15) + (ic * 0.1) - (hg * 0.05)
        gras_mm = max(2.0, min(22.0, gras_mm))

        # 3. Pourcentages (Coefficients ajustés pour réalisme zootechnique)
        pct_gras = max(10.0, min(40.0, 5.0 + (gras_mm * 1.5)))
        pct_muscle = max(45.0, min(72.0, 75.0 - (pct_gras * 0.6) + (ic * 0.2)))
        pct_os = 100.0 - pct_muscle - pct_gras

        # 4. Classement EUROP
        if ic > 33: classe = "S (Supérieur)"
        elif ic > 30: classe = "E (Excellent)"
        elif ic > 27: classe = "U (Très bon)"
        elif ic > 24: classe = "R (Bon)"
        else: classe = "O/P (Médiocre)"

        # 5. Indice S90 (Score de valeur bouchère)
        s90 = (pct_muscle * 1.2) - (pct_gras * 0.5)
        
        return (round(pct_muscle, 1), round(pct_gras, 1), round(pct_os, 1), 
                round(gras_mm, 1), round(ic * 0.8, 1), classe, round(s90, 1), round(ic, 2))
    except:
        return 0, 0, 0, 0, 0, "Erreur", 0, 0

# ==========================================
# GESTION DES DONNÉES
# ==========================================
def load_data():
    with get_db_connection() as conn:
        query = "SELECT * FROM beliers b LEFT JOIN (SELECT id_animal, MAX(id) as mid FROM mesures GROUP BY id_animal) l ON b.id = l.id_animal LEFT JOIN mesures m ON l.mid = m.id"
        df = pd.read_sql(query, conn)
        
        if df.empty: return df

        # Nettoyage des colonnes numériques pour éviter NaN
        num_cols = ['p70', 'p30', 'h_garrot', 'p_thoracique', 'c_canon', 'l_poitrine', 'l_corps']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Application des calculs
        res = df.apply(lambda x: pd.Series(calculer_composition_carcasse(x)), axis=1)
        df[['Pct_Muscle', 'Pct_Gras', 'Pct_Os', 'Gras_mm', 'SMLD', 'EUROP', 'S90', 'IC']] = res
        
        # Index de sélection simple
        df['Index'] = (df['p70'] * 0.4) + (df['S90'] * 0.6)
        df['Statut'] = np.where(df['Index'] > df['Index'].quantile(0.85), "⭐ ELITE", "Standard")
        
        return df

# ==========================================
# INTERFACE UTILISATEUR
# ==========================================
def main():
    st.sidebar.title("💎 Expert Selector Pro")
    menu = st.sidebar.radio("Navigation", ["📊 Dashboard", "🥩 Composition", "✍️ Saisie"])
    
    df = load_data()

    if menu == "📊 Dashboard":
        st.title("🏆 Analyse du Troupeau")
        if df.empty:
            st.info("Aucune donnée. Veuillez utiliser l'onglet Saisie.")
        else:
            # Métriques de tête
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sujets", len(df))
            c2.metric("Muscle moyen", f"{df['Pct_Muscle'].mean():.1f}%")
            c3.metric("Gras moyen", f"{df['Gras_mm'].mean():.1f} mm")
            c4.metric("Elite", len(df[df['Statut'] == "⭐ ELITE"]))

            # Tableau de bord propre
            st.subheader("Classement des performances")
            df_disp = df[['id', 'race', 'p70', 'Pct_Muscle', 'Gras_mm', 'EUROP', 'Index', 'Statut']].sort_values('Index', ascending=False)
            st.dataframe(df_disp, use_container_width=True)

    elif menu == "🥩 Composition":
        st.title("🥩 Analyse Individuelle")
        if not df.empty:
            target = st.selectbox("Sélectionner l'animal", df['id'].unique())
            an = df[df['id'] == target].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                # Graphique en camembert de la carcasse
                fig = px.pie(values=[an['Pct_Muscle'], an['Pct_Gras'], an['Pct_Os']], 
                             names=['Muscle', 'Gras', 'Os'], color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig)
            with col2:
                st.subheader(f"Profil : {an['EUROP']}")
                st.write(f"**Indice de Conformation (IC) :** {an['IC']}")
                st.write(f"**Score de Valeur (S90) :** {an['S90']}")
                st.progress(int(an['Pct_Muscle']))
                st.caption(f"Taux de muscle : {an['Pct_Muscle']}%")

    elif menu == "✍️ Saisie":
        st.title("✍️ Nouvelle Mesure")
        # (Gardez votre formulaire de saisie habituel ici)
        st.info("Utilisez ce formulaire pour ajouter un nouvel animal.")

if __name__ == "__main__":
    main()
