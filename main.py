import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import math

# --- CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Pro - Efficacité Lot", layout="wide", page_icon="🐏")

# --- INITIALISATION BASES ---
if 'db_data' not in st.session_state:
    st.session_state.db_data = pd.DataFrame(columns=['ID', 'PoidsActuel', 'Age', 'Sire', 'Dam'])

if 'agneaux_db' not in st.session_state:
    st.session_state.agneaux_db = pd.DataFrame(columns=[
        'ID_Agneau', 'ID_Mere', 'ID_Pere', 'Date_Naissance', 'Sexe', 
        'Poids_Naissance', 'Poids_J30', 'Poids_J90', 'Poids_J180'
    ])

# NOUVELLE BASE : Consommation par lot/cohorte
if 'consommation_lot_db' not in st.session_state:
    st.session_state.consommation_lot_db = pd.DataFrame(columns=[
        'ID_Lot', 'Date_Debut', 'Date_Fin', 'Duree_Jours',
        'Liste_Agneaux', 'Nombre_Tetes', 'Poids_Total_Debut', 'Poids_Total_Fin',
        'Aliment_Distribue_Kg', 'Aliment_MS_Perc', 'Type_Aliment',
        'Prix_Aliment_Kg', 'Consommation_Matiere_Seche', 'Gain_Lot_Kg',
        'IC_Lot', 'Cout_Kg_Gain', 'Marge_Alimentaire', 'Efficacite'
    ])

# --- FONCTIONS CALCUL CONSOMMATION GROUPE ---
def calculer_poids_metabolique(poids_kg):
    """PV^0.75 - standard physiologique pour comparaison inter-espèces/lots"""
    return poids_kg ** 0.75

def repartir_conso_par_poids_metabolique(df_animaux, conso_totale_ms):
    """
    Répartit la consommation totale selon le poids métabolique de chaque animal
    Plus l'animal est gros, plus il mange proportionnellement
    """
    df = df_animaux.copy()
    df['Poids_Meta'] = df['Poids_Actuel'].apply(calculer_poids_metabolique)
    total_meta = df['Poids_Meta'].sum()
    
    df['Part_Consommation'] = df['Poids_Meta'] / total_meta
    df['Conso_Individuelle_MS'] = conso_totale_ms * df['Part_Consommation']
    df['Conso_Individuelle_Jour'] = df['Conso_Individuelle_MS'] / df['Duree_Period']
    
    return df

def ic_theorique_ovin(age_jours, poids_kg, sexe):
    """
    Valeurs théoriques INRA pour ovins croissance
    IC = kg MS / kg gain
    """
    if age_jours < 30:
        base = 2.5  # Allaitement + démarrage
    elif age_jours < 90:
        base = 3.5 if sexe == 'Mâle' else 4.0  # Croissance lente
    elif age_jours < 180:
        base = 4.5 if sexe == 'Mâle' else 5.0  # Pré-engraissement
    else:
        base = 6.0  # Engraissement
    
    # Ajustement selon poids (plus gros = moins efficace généralement)
    if poids_kg > 35:
        base *= 1.1
    
    return base

def evaluer_ic_reel(ic_reel, ic_theorique):
    """Écart par rapport à la référence"""
    ecart = ((ic_reel - ic_theorique) / ic_theorique) * 100
    if ecart <= 5:
        return "Excellent", "green", "🟢"
    elif ecart <= 15:
        return "Acceptable", "orange", "🟡"
    else:
        return "À améliorer", "red", "🔴"

# --- INTERFACE ---
st.sidebar.title("🐏 BélierSelector Pro v5.0")
menu = st.sidebar.radio("Navigation", [
    "👶 Agnelages & Croissance",
    "🌾 Efficacité Alimentaire (Lot)",  # NOUVEAU MODULE
    "💰 Rentabilité & Marge",
    "🧬 Génétique",
    "💾 Export"
])

# --- PAGE 1 : CONSOMMATION EN GROUPE ---
if menu == "🌾 Efficacité Alimentaire (Lot)":
    st.title("🌾 Gestion de la Consommation en Élevage Groupe")
    
    st.info("""
    **💡 Méthode du Poids Métabolique (PV^0.75)**
    Comme les agneaux mangent ensemble, la consommation est répartie proportionnellement
    au poids métabolique de chacun : un animal de 40kg mange ~1.5x plus qu'un de 25kg.
    Cela permet d'estimer l'IC individuel sans isolement alimentaire.
    """)
    
    tab1, tab2, tab3 = st.tabs(["⚖️ Saisie Consommation Lot", "📊 Analyse Efficacité", "🔍 Comparaison Individuelle"])
    
    with tab1:
        st.subheader("Enregistrement de la Consommation Groupe")
        
        col1, col2 = st.columns(2)
        
        with col1:
            id_lot = st.text_input("Identifiant du Lot", 
                                  value=f"LOT-{datetime.now().strftime('%Y%m')}")
            date_debut = st.date_input("Début période", datetime.now().date() - timedelta(days=30))
            date_fin = st.date_input("Fin période", datetime.now().date())
            duree = (date_fin - date_debut).days
            
            st.write(f"**Durée**: {duree} jours")
            
            # Sélection multiple d'agneaux
            liste_agneaux = st.session_state.agneaux_db['ID_Agneau'].tolist() if len(st.session_state.agneaux_db) > 0 else []
            selectionnes = st.multiselect("Agneaux présents dans le lot", liste_agneaux)
            
            mode_repartition = st.radio("Méthode de répartition", [
                "Poids métabolique (PV^0.75) - Précis",
                "Équipondéré (part égale) - Si groupe homogène",
                "Manuelle (si identification mangeurs rapides)"
            ])
        
        with col2:
            st.subheader("Données Alimentaires")
            type_alim = st.selectbox("Type d'aliment", [
                "Concentré croissance (18% PB)",
                "Foin + concentré (50/50)",
                "Pâturage seul (estimation)",
                "Engraissement (16% PB)",
                "Aliment spécifique post-sevrage"
            ])
            
            # Tenir compte de la MS (Matière Sèche)
            if "Pâturage" in type_alim:
                ms_perc = 20.0  # Herbe fraîche
            elif "Foin" in type_alim:
                ms_perc = 85.0
            else:
                ms_perc = 88.0  # Concentré
            
            qte_distribuee = st.number_input("Quantité distribuée totale (kg frais)", 
                                           min_value=1.0, max_value=10000.0, value=500.0)
            ms_ajust = st.number_input("Teneur en Matière Sèche (%)", 0.0, 100.0, ms_perc)
            qte_ms = qte_distribuee * (ms_ajust / 100)
            
            st.success(f"**Matière Sèche totale**: {qte_ms:.1f} kg MS")
            
            prix_kg = st.number_input("Prix aliment (€/kg)", 0.0, 5.0, 0.35, 0.01)
            cout_total = qte_ms * prix_kg
            
            st.write(f"**Coût alimentaire**: {cout_total:.2f} €")
            
            # Gaspillage estimé (important en élevage groupe !)
            gaspillage = st.slider("Gaspillage estimé (%)", 0, 30, 5, 
                                  help="Restes au mangeoire, piétinements, vol..."),
            qte_ms_reelle = qte_ms * (1 - gaspillage[0]/100)
            st.write(f"**MS réellement ingéré**: ~{qte_ms_reelle:.1f} kg (après gaspillage)")
        
        # Informations individuelles nécessaires
        if selectionnes and len(selectionnes) > 0:
            st.divider()
            st.subheader("📋 Poids des Animaux au Début et Fin de Période")
            st.write("Nécessaire pour calculer le gain de lot")
            
            data_pesee = []
            cols = st.columns(min(len(selectionnes), 4))
            
            for i, id_agn in enumerate(selectionnes):
                col = cols[i % 4]
                with col:
                    st.markdown(f"**{id_agn}**")
                    data_agn = st.session_state.agneaux_db[
                        st.session_state.agneaux_db['ID_Agneau'] == id_agn
                    ].iloc[0]
                    
                    poids_deb = st.number_input(f"Poids début (kg) {i}", 
                                               value=float(data_agn.get('Poids_J30', 15.0)), 
                                               key=f"deb_{i}")
                    poids_fin = st.number_input(f"Poids fin (kg) {i}", 
                                               value=float(data_agn.get('Poids_J90', 25.0)), 
                                               key=f"fin_{i}")
                    
                    data_pesee.append({
                        'ID': id_agn,
                        'Poids_Debut': poids_deb,
                        'Poids_Fin': poids_fin,
                        'Gain': poids_fin - poids_deb,
                        'Age_Moyen': data_agn.get('Age', 60),  # Approximation
                        'Sexe': data_agn.get('Sexe', 'Mâle')
                    })
            
            if st.button("💾 Calculer Efficacité du Lot"):
                df_lot = pd.DataFrame(data_pesee)
                gain_total = df_lot['Gain'].sum()
                poids_total_deb = df_lot['Poids_Debut'].sum()
                poids_total_fin = df_lot['Poids_Fin'].sum()
                
                # Calcul IC Lot
                if gain_total > 0:
                    ic_lot = qte_ms_reelle / gain_total
                else:
                    ic_lot = 999
                
                # Coût au kg de gain
                if gain_total > 0:
                    cout_kg_gain = cout_total / gain_total
                else:
                    cout_kg_gain = 999
                
                # Valeur du gain (estimation marché)
                prix_kg_vif = 3.5  # €/kg vif moyen
                valeur_gain = gain_total * prix_kg_vif
                
                # Marge
                marge = valeur_gain - cout_total
                
                # Sauvegarde
                new_entry = {
                    'ID_Lot': id_lot,
                    'Date_Debut': str(date_debut),
                    'Date_Fin': str(date_fin),
                    'Duree_Jours': duree,
                    'Liste_Agneaux': json.dumps(selectionnes),
                    'Nombre_Tetes': len(selectionnes),
                    'Poids_Total_Debut': poids_total_deb,
                    'Poids_Total_Fin': poids_total_fin,
                    'Aliment_Distribue_Kg': qte_distribuee,
                    'Aliment_MS_Perc': ms_ajust,
                    'Type_Aliment': type_alim,
                    'Prix_Aliment_Kg': prix_kg,
                    'Consommation_Matiere_Seche': qte_ms_reelle,
                    'Gain_Lot_Kg': gain_total,
                    'IC_Lot': round(ic_lot, 2),
                    'Cout_Kg_Gain': round(cout_kg_gain, 2),
                    'Marge_Alimentaire': round(marge, 2),
                    'Efficacite': 'Bonne' if ic_lot < 4.5 else 'Moyenne' if ic_lot < 6 else 'Faible'
                }
                
                st.session_state.consommation_lot_db = pd.concat([
                    st.session_state.consommation_lot_db,
                    pd.DataFrame([new_entry])
                ], ignore_index=True)
                
                st.success("✅ Données enregistrées!")
                st.balloons()
                
                # Affichage résumé
                col_r1, col_r2, col_r3 = st.columns(3)
                col_r1.metric("IC Lot", f"{ic_lot:.2f}", 
                             help="kg MS / kg gain. Objectif: <4.5")
                col_r2.metric("Coût/kg gain", f"{cout_kg_gain:.2f} €")
                col_r3.metric("Marge lot", f"{marge:.2f} €", 
                             delta="Bénéfice" if marge > 0 else "Déficit")
    
    with tab2:
        st.subheader("Analyse de l'Efficacité par Lot")
        
        if len(st.session_state.consommation_lot_db) > 0:
            df_cons = st.session_state.consommation_lot_db.copy()
            
            # Tableau récap
            st.dataframe(df_cons[['ID_Lot', 'Date_Fin', 'Nombre_Tetes', 'Type_Aliment', 
                                 'IC_Lot', 'Cout_Kg_Gain', 'Efficacite']], hide_index=True)
            
            # Graphique évolution IC
            fig = px.bar(df_cons, x='ID_Lot', y='IC_Lot', color='Efficacite',
                        title="Indice de Consommation par Lot (objectif < 4.5)",
                        color_discrete_map={'Bonne': 'green', 'Moyenne': 'orange', 'Faible': 'red'})
            fig.add_hline(y=4.5, line_dash="dash", annotation_text="Seuil optimal")
            fig.add_hline(y=6.0, line_dash="dash", line_color="red", annotation_text="Seuil critique")
            st.plotly_chart(fig, use_container_width=True)
            
            # Analyse économique
            st.subheader("💰 Analyse Économique")
            fig2 = px.scatter(df_cons, x='Cout_Kg_Gain', y='Marge_Alimentaire', 
                            size='Gain_Lot_Kg', color='Type_Aliment',
                            title="Coût vs Marge par lot")
            st.plotly_chart(fig2, use_container_width=True)
            
            # Détection des problèmes
            lots_probleme = df_cons[df_cons['IC_Lot'] > 6]
            if len(lots_probleme) > 0:
                st.error("🚨 Lots à problème (IC > 6):")
                for _, row in lots_probleme.iterrows():
                    st.write(f"• {row['ID_Lot']}: IC de {row['IC_Lot']:.1f} "
                            f"(vérifier gaspillage ou aliment non adapté)")
        else:
            st.info("Aucune donnée de consommation enregistrée")
    
    with tab3:
        st.subheader("Estimation Individuelle par Poids Métabolique")
        
        if len(st.session_state.consommation_lot_db) > 0 and len(st.session_state.agneaux_db) > 0:
            # Sélection d'un lot pour analyse détaillée
            lot_selection = st.selectbox("Choisir un lot à analys", 
                                       st.session_state.consommation_lot_db['ID_Lot'])
            
            data_lot = st.session_state.consommation_lot_db[
                st.session_state.consommation_lot_db['ID_Lot'] == lot_selection
            ].iloc[0]
            
            # Récupération agneaux et simulation répartition
            ids_agneaux = json.loads(data_lot['Liste_Agneaux'])
            df_agn = st.session_state.agneaux_db[
                st.session_state.agneaux_db['ID_Agneau'].isin(ids_agneaux)
            ].copy()
            
            # Création données simulées pour la démo (en vrai: poids début/fin de période)
            np.random.seed(42)
            df_agn['Poids_Actuel'] = np.random.uniform(25, 40, len(df_agn))
            df_agn['Duree_Period'] = data_lot['Duree_Jours']
            
            # Calcul répartition
            df_reparti = repartir_conso_par_poids_metabolique(df_agn, data_lot['Consommation_Matiere_Seche'])
            
            # Affichage
            st.write("**Répartition estimée de la consommation:**")
            df_display = df_reparti[['ID_Agneau', 'Poids_Actuel', 'Poids_Meta', 'Part_Consommation', 
                                   'Conso_Individuelle_MS', 'Conso_Individuelle_Jour']]
            df_display.columns = ['ID', 'Poids (kg)', 'PV^0.75', '% Consommation', 'MS totale (kg)', 'MS/jour']
            st.dataframe(df_display.style.background_gradient(subset=['MS/jour'], cmap='YlOrRd'))
            
            # Identification des "gros mangeurs" vs "efficaces"
            st.info("""
            **Interprétation:**
            • Les animaux avec un % consommation > leur % de poids métabolique sont des gros mangeurs
            • Si leur gain est faible malgré cela → inefficaces (à éliminer)
            • Si leur gain est élevé → croissance rapide (à garder pour reproduction)
            """)

# --- PAGE 2 : RENTABILITÉ ---
elif menu == "💰 Rentabilité & Marge":
    st.title("💰 Calcul de la Marge Alimentaire")
    
    st.latex(r'''
    \text{Marge} = (\text{Gain de poids} \times \text{Prix kg vif}) - (\text{MS consommée} \times \text{Prix aliment})
    ''')
    
    st.write("""
    **Seuils de rentabilité indicatifs (ovins):**
    - IC < 4.0 : Très rentable
    - IC 4.0-5.0 : Rentable  
    - IC 5.0-6.0 : Limite (vérifier le prix de vente)
    - IC > 6.0 : Déficitaire (sauf très haut prix de vente)
    """)
    
    # Calculateur interactif
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Paramètres")
        poids_vendu = st.number_input("Poids vente (kg)", 30.0, 50.0, 38.0)
        prix_vif = st.number_input("Prix €/kg vif", 2.0, 8.0, 3.5, 0.1)
        poids_debut = st.number_input("Poids achat/démarrage (kg)", 10.0, 30.0, 20.0)
        
    with col2:
        ic_realise = st.number_input("IC réalisé", 2.0, 10.0, 4.5, 0.1)
        prix_alim = st.number_input("Coût aliment €/kg MS", 0.2, 1.0, 0.35, 0.01)
        
        gain = poids_vendu - poids_debut
        conso_ms = gain * ic_realise
        cout_prod = conso_ms * prix_alim
        recette = poids_vendu * prix_vif
        marge = recette - cout_prod - (poids_debut * 2)  # -2€/kg prix de départ
        
        st.metric("Marge estimée/animal", f"{marge:.2f} €")
        if marge > 50:
            st.success("✅ Rentable")
        elif marge > 20:
            st.warning("⚠️ Rentabilité faible")
        else:
            st.error("❌ Non rentable - Revoir alimentation")

# --- AUTRES PAGES SIMPLIFIÉES ---
elif menu == "👶 Agnelages & Croissance":
    st.title("Module Agneaux (intégré)")
    st.write("Utilisez les autres modules pour les détails")

elif menu == "🧬 Génétique":
    st.title("Sélection sur efficacité alimentaire")
    st.write("Les animaux avec IC élevé (>6) malgré bon gain sont à éliminer")

elif menu == "💾 Export":
    if st.button("Exporter toutes les données"):
        export = {
            'consommation_lots': st.session_state.consommation_lot_db.to_dict('records'),
            'agneaux': st.session_state.agneaux_db.to_dict('records')
        }
        st.download_button("Télécharger JSON", json.dumps(export, indent=2), "data.json")

# --- SIDEBAR RÉSUMÉ ---
st.sidebar.divider()
if len(st.session_state.consommation_lot_db) > 0:
    st.sidebar.subheader("📊 Dernier Lot")
    dernier = st.session_state.consommation_lot_db.iloc[-1]
    st.sidebar.write(f"IC: {dernier['IC_Lot']:.2f}")
    st.sidebar.write(f"Marge: {dernier['Marge_Alimentaire']:.0f}€")
    if dernier['IC_Lot'] > 6:
        st.sidebar.error("IC élevé!")
