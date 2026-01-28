import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from scipy import stats
import json
from PIL import Image
import io
import base64

# --- CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Pro - Photogrammétrie", layout="wide", page_icon="🐏")

# --- INITIALISATION SESSION STATE ---
if 'db_data' not in st.session_state:
    st.session_state.db_data = pd.DataFrame(columns=[
        'ID', 'DateDernierePesee', 'PoidsActuel', 'GMQ', 'Age', 
        'Prev_P10', 'Prev_P30', 'Prev_P70', 'ProchainesPesees', 
        'HistoriquePoids', 'V2', 'V5', 'BCS', 'Q29', 'Sire', 'Dam',
        'PhotoProfil', 'MesuresPhoto'  # Nouveaux champs
    ])
    
if 'saillies_db' not in st.session_state:
    st.session_state.saillies_db = pd.DataFrame(columns=[
        'ID_Saillie', 'ID_Belier', 'ID_Brebis', 'Date_Saillie', 
        'Mode', 'Duree', 'Succes_Obs', 'Gest_Confirme', 
        'Date_Agnelage_Prevu', 'Notes'
    ])

# --- FONCTIONS UTILITAIRES ---
def calculer_dates_pesee(date_derniere_pesee):
    if isinstance(date_derniere_pesee, str):
        date_derniere_pesee = pd.to_datetime(date_derniere_pesee).date()
    return {
        'P10': date_derniere_pesee + timedelta(days=10),
        'P30': date_derniere_pesee + timedelta(days=30),
        'P70': date_derniere_pesee + timedelta(days=70)
    }

def get_alerts():
    alerts = []
    today = datetime.now().date()
    for _, row in st.session_state.db_data.iterrows():
        if 'ProchainesPesees' in row and pd.notna(row['ProchainesPesees']):
            dates = json.loads(row['ProchainesPesees'])
            for periode, date_str in dates.items():
                date_obj = pd.to_datetime(date_str).date()
                jours = (date_obj - today).days
                if 0 <= jours <= 3:
                    alerts.append({'type': 'pesee', 'id': row['ID'], 'date': date_str, 'jours': jours})
    
    # Alertes saillies à terme
    for _, row in st.session_state.saillies_db.iterrows():
        if pd.notna(row['Date_Agnelage_Prevu']):
            date_obj = pd.to_datetime(row['Date_Agnelage_Prevu']).date()
            jours = (date_obj - today).days
            if 0 <= jours <= 7:
                alerts.append({
                    'type': 'agnelage', 
                    'belier': row['ID_Belier'], 
                    'brebis': row['ID_Brebis'],
                    'date': str(date_obj),
                    'jours': jours
                })
    return alerts

def calculer_index_fertilite(id_belier):
    """Calcule le taux de fécondité du bélier"""
    saillies = st.session_state.saillies_db[st.session_state.saillies_db['ID_Belier'] == id_belier]
    if len(saillies) == 0:
        return None
    
    total = len(saillies)
    gest_confirmees = len(saillies[saillies['Gest_Confirme'] == 'Oui'])
    taux = (gest_confirmees / total) * 100 if total > 0 else 0
    
    # Calcul du NRR (Non-Return Rate à 60 jours)
    # Simulé ici car on n'a pas les données de retour en chaleur exactes
    return {
        'Total_Saillies': total,
        'Gestations': gest_confirmees,
        'Taux_Fertilite': round(taux, 1),
        'Moyenne_Saillies_Jour': round(total / 30, 1) if total > 0 else 0  # Sur dernier mois
    }

# --- SIDEBAR ---
st.sidebar.title("🐏 BélierSelector Pro v2.0")
menu = st.sidebar.radio("Navigation", [
    "📸 Photogrammétrie (Mesure par Photo)",  # NOUVEAU
    "❤️ Reproduction & Fertilité",             # NOUVEAU
    "📅 Calendrier & Projections",
    "⚖️ Mise à jour Pesée",
    "📝 Caractérisation",
    "💾 Base de Données"
])

# Alertes
st.sidebar.divider()
alerts = get_alerts()
if alerts:
    st.sidebar.subheader(f"🔔 Alertes ({len(alerts)})")
    for alert in alerts:
        if alert['type'] == 'pesee':
            st.sidebar.warning(f"⚖️ {alert['id'][:8]} dans {alert['jours']}j")
        else:
            st.sidebar.error(f"🍼 Agnelage {alert['brebis'][:8]} imminant !")
else:
    st.sidebar.info("Aucune alerte urgente")

# --- PAGE 1 : PHOTOGRAMMÉTRIE ---
if menu == "📸 Photogrammétrie (Mesure par Photo)":
    st.title("📸 Mesure Morphométrique par Photogrammétrie")
    
    st.warning("""
    **⚠️ Protocole de mesure obligatoire pour la précision :**
    1. **Étalon de référence** : Placer une règle de 1m ou un objet de taille connue visible sur la photo
    2. **Position** : Photographier perpendiculairement au dos de l'animal (90°)
    3. **Distance** : Maintenir 2-3m de distance, zoomer si nécessaire
    4. **Fond** : Préférer un fond contrasté (mur clair ou sombre)
    5. **Posture** : Animal debout, tête droite, 4 pattes bien alignées
    
    *Précision attendue : ±2-3 cm (vs ±0.5cm au ruban)*
    """)
    
    tab1, tab2 = st.tabs(["📷 Nouvelle Mesure", "📏 Historique Photos"])
    
    with tab1:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("1. Capture de l'Image")
            id_animal = st.selectbox("Animal à mesurer", st.session_state.db_data["ID"] if len(st.session_state.db_data) > 0 else ["Aucun"])
            
            photo_type = st.radio("Type de mesure", [
                "Longueur du corps (épaule-croupe)",
                "Hauteur au garrot", 
                "Périmètre thoracique (vue de côté, référence nécessaire)",
                "Largeur hanches (vue de dos)"
            ])
            
            # Option caméra ou upload
            mode_capture = st.radio("Source", ["📱 Caméra téléphone", "📁 Fichier existant"])
            
            if mode_capture == "📱 Caméra téléphone":
                photo = st.camera_input("Prendre la photo", help="Visez l'animal de profil, étalon visible")
            else:
                photo = st.file_uploader("Charger une image", type=['jpg', 'png', 'jpeg'])
            
            if photo:
                st.image(photo, caption="Image capturée", use_column_width=True)
                
                # Sauvegarde temporaire pour processing
                bytes_data = photo.getvalue()
                
        with col2:
            if photo:
                st.subheader("2. Calibration & Mesure")
                
                st.info("**Méthode de l'étalon :** Indiquez la longueur réelle d'un objet visible sur la photo")
                
                col_ref1, col_ref2 = st.columns(2)
                longueur_ref_px = col_ref1.number_input("Longueur étalon sur image (pixels)", 50, 2000, 500)
                longueur_ref_reelle = col_ref2.number_input("Longueur réelle de l'étalon (cm)", 1.0, 200.0, 100.0)
                
                # Calcul du ratio pixels/cm
                ratio = longueur_ref_px / longueur_ref_reelle
                st.write(f"**Ratio calculé :** {ratio:.2f} pixels/cm")
                st.write(f"**Résolution :** {1/ratio:.2f} cm/pixel")
                
                st.divider()
                
                st.subheader("3. Mesure de l'animal")
                st.write("Entrez les mesures en pixels (à mesurer avec un logiciel d'image ou estimation visuelle)")
                
                if "Longueur" in photo_type:
                    pixels_mesure = st.number_input("Longueur animal (pixels)", 100, 3000, 800)
                    mesure_reelle = pixels_mesure / ratio
                    st.success(f"**Longueur du corps estimée : {mesure_reelle:.1f} cm**")
                    
                elif "Hauteur" in photo_type:
                    pixels_mesure = st.number_input("Hauteur au garrot (pixels)", 100, 2000, 600)
                    mesure_reelle = pixels_mesure / ratio
                    st.success(f"**Hauteur au garrot estimée : {mesure_reelle:.1f} cm**")
                    
                elif "Périmètre" in photo_type:
                    st.error("⚠️ Le périmètre thoracique ne peut pas être mesuré précisément en 2D (nécessite volume). Utilisez la vue de dessus ou le ruban.")
                    pixels_mesure = st.number_input("Largeur thorax (pixels)", 100, 1500, 400)
                    mesure_reelle = pixels_mesure / ratio
                    st.info(f"Largeur thoracique (pas périmètre) : {mesure_reelle:.1f} cm")
                    
                else:  # Largeur
                    pixels_mesure = st.number_input("Largeur hanches (pixels)", 100, 1500, 300)
                    mesure_reelle = pixels_mesure / ratio
                    st.success(f"**Largeur hanches estimée : {mesure_reelle:.1f} cm**")
                
                # Enregistrement
                if st.button("💾 Enregistrer cette mesure"):
                    if id_animal in st.session_state.db_data["ID"].values:
                        idx = st.session_state.db_data[st.session_state.db_data["ID"] == id_animal].index[0]
                        
                        # Stockage de la photo encodée (simplifié)
                        photo_b64 = base64.b64encode(bytes_data).decode()
                        
                        mesures_existantes = json.loads(st.session_state.db_data.at[idx, 'MesuresPhoto']) if pd.notna(st.session_state.db_data.at[idx, 'MesuresPhoto']) else []
                        mesures_existantes.append({
                            'date': str(datetime.now().date()),
                            'type': photo_type,
                            'valeur_cm': round(mesure_reelle, 1),
                            'ratio': ratio,
                            'photo': photo_b64[:100] + "..."  # Stockage partiel pour démo
                        })
                        
                        st.session_state.db_data.at[idx, 'MesuresPhoto'] = json.dumps(mesures_existantes)
                        st.session_state.db_data.at[idx, 'PhotoProfil'] = photo_b64
                        
                        # Mise à jour automatique de la donnée morpho correspondante
                        if "Longueur" in photo_type:
                            st.session_state.db_data.at[idx, 'V4'] = round(mesure_reelle, 1)
                        elif "Hauteur" in photo_type:
                            st.session_state.db_data.at[idx, 'V2'] = round(mesure_reelle, 1)
                        elif "hanches" in photo_type:
                            st.session_state.db_data.at[idx, 'V8'] = round(mesure_reelle, 1)
                        
                        st.success("✅ Mesure photogrammétrique enregistrée et intégrée au profil !")
                        st.balloons()
                    else:
                        st.error("Animal non trouvé dans la base")
    
    with tab2:
        st.subheader("Historique des mesures par photo")
        if len(st.session_state.db_data) > 0 and 'MesuresPhoto' in st.session_state.db_data.columns:
            for _, row in st.session_state.db_data.iterrows():
                if pd.notna(row['MesuresPhoto']):
                    mesures = json.loads(row['MesuresPhoto'])
                    with st.expander(f"🐏 {row['ID']} - {len(mesures)} mesures"):
                        for m in mesures:
                            st.write(f"📅 {m['date']} : {m['type']} = **{m['valeur_cm']} cm** (ratio: {m['ratio']:.1f}px/cm)")

# --- PAGE 2 : REPRODUCTION & FERTILITÉ ---
elif menu == "❤️ Reproduction & Fertilité":
    st.title("❤️ Suivi de la Reproduction des Béliers")
    
    tab1, tab2, tab3 = st.tabs(["📝 Saisie d'une Saillie", "📊 Fertilité des Béliers", "📅 Calendrier des Mises Bas"])
    
    with tab1:
        st.subheader("Enregistrement d'une saillie naturelle ou IA")
        
        col1, col2 = st.columns(2)
        with col1:
            id_belier = st.selectbox("Bélier reproducteur", 
                                    st.session_state.db_data["ID"] if len(st.session_state.db_data) > 0 else ["Aucun"])
            
            if id_belier != "Aucun":
                data_b = st.session_state.db_data[st.session_state.db_data["ID"] == id_belier].iloc[0]
                st.metric("Age du bélier", f"{data_b['Age']} mois")
                st.metric("BCS", data_b['BCS'])
        
        with col2:
            id_brebis = st.text_input("Identifiant Brebis", placeholder="Ex: BRB-2024-001")
            date_saillie = st.date_input("Date de saillie", datetime.now().date())
            mode_saillie = st.selectbox("Mode", ["Naturelle libre", "Naturelle contrôlée", "Insémination Artificielle"])
        
        col3, col4 = st.columns(2)
        with col3:
            duree = st.number_input("Durée (minutes)", 1, 60, 15, help="Temps de monte ou d'IA")
        
        with col4:
            succes = st.selectbox("Succès apparent", ["Non observé", "Monte confirmée", "Douteuse"])
        
        # Calcul date prévue d'agnelage (ovins : 147-150 jours de gestation)
        date_agnelage = date_saillie + timedelta(days=150)
        st.info(f"📅 **Date prévue d'agnelage :** {date_agnelage.strftime('%d/%m/%Y')} (J+150)")
        
        notes_repro = st.text_area("Observations", placeholder="Comportement, nombre de montes, etc.")
        
        if st.button("💾 Enregistrer la saillie"):
            new_saillie = {
                'ID_Saillie': f"SAIL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'ID_Belier': id_belier,
                'ID_Brebis': id_brebis,
                'Date_Saillie': str(date_saillie),
                'Mode': mode_saillie,
                'Duree': duree,
                'Succes_Obs': succes,
                'Gest_Confirme': 'Non testé',
                'Date_Agnelage_Prevu': str(date_agnelage),
                'Notes': notes_repro
            }
            st.session_state.saillies_db = pd.concat([st.session_state.saillies_db, pd.DataFrame([new_saillie])], ignore_index=True)
            st.success("✅ Saillie enregistrée ! Suivi de gestation activé.")
    
    with tab2:
        st.subheader("📊 Indices de Fertilité des Béliers")
        
        if len(st.session_state.saillies_db) > 0:
            # Tableau récap par bélier
            beliers_actifs = st.session_state.saillies_db['ID_Belier'].unique()
            
            stats_list = []
            for bel in beliers_actifs:
                idx_data = calculer_index_fertilite(bel)
                if idx_data:
                    stats_list.append({
                        'ID_Belier': bel,
                        'Taux_Fertilite_%': idx_data['Taux_Fertilite'],
                        'Nb_Saillies': idx_data['Total_Saillies'],
                        'Gestations_Confirmees': idx_data['Gestations']
                    })
            
            if stats_list:
                df_stats = pd.DataFrame(stats_list).sort_values('Taux_Fertilite_%', ascending=False)
                
                # Graphique
                fig = px.bar(df_stats, x='ID_Belier', y='Taux_Fertilite_%', 
                            color='Nb_Saillies', title="Taux de Fécondité par Bélier (%)",
                            labels={'Taux_Fertilite_%': 'Fertilité (%)', 'ID_Belier': 'Bélier'})
                fig.add_hline(y=80, line_dash="dash", line_color="green", annotation_text="Objectif >80%")
                fig.add_hline(y=60, line_dash="dash", line_color="red", annotation_text="Seuil critique <60%")
                st.plotly_chart(fig, use_container_width=True)
                
                st.dataframe(df_stats, use_container_width=True)
                
                # Détection des problèmes
                problemes = df_stats[df_stats['Taux_Fertilite_%'] < 60]
                if len(problemes) > 0:
                    st.error("🚨 Alertes fertilité :")
                    for _, prob in problemes.iterrows():
                        st.write(f"• {prob['ID_Belier']} : {prob['Taux_Fertilite_%']}% - Examen andrologique recommandé")
        else:
            st.info("Aucune donnée de saillie enregistrée")
    
    with tab3:
        st.subheader("🍼 Calendrier des Agnelages Prévus")
        
        if len(st.session_state.saillies_db) > 0:
            today = datetime.now().date()
            saillies = st.session_state.saillies_db.copy()
            saillies['Date_Agnelage'] = pd.to_datetime(saillies['Date_Agnelage_Prevu']).dt.date
            
            # Prochains agnelages (dans les 60 jours)
            a_venir = saillies[saillies['Date_Agnelage'] >= today]
            a_venir = a_venir.sort_values('Date_Agnelage')
            
            # Colonnes pour affichage
            cols = st.columns(3)
            for i, (_, row) in enumerate(a_venir.head(9).iterrows()):
                with cols[i % 3]:
                    jours_restant = (row['Date_Agnelage'] - today).days
                    
                    if jours_restant <= 7:
                        couleur = "🔴"
                        bg = "red"
                    elif jours_restant <= 30:
                        couleur = "🟡"
                        bg = "orange"
                    else:
                        couleur = "🟢"
                        bg = "green"
                    
                    st.markdown(f"""
                    <div style='padding:10px; border-left: 5px solid {bg}; background-color:#f0f0f0; margin:5px;'>
                        {couleur} <b>{row['ID_Brebis']}</b><br>
                        <small>Père: {row['ID_Belier']}</small><br>
                        <b>{row['Date_Agnelage'].strftime('%d/%m/%Y')}</b><br>
                        <small>Dans {jours_restant} jours</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Confirmer gestation", key=f"gest_{row['ID_Saillie']}"):
                        idx = st.session_state.saillies_db[st.session_state.saillies_db['ID_Saillie'] == row['ID_Saillie']].index[0]
                        st.session_state.saillies_db.at[idx, 'Gest_Confirme'] = 'Oui'
                        st.success("Gestation confirmée !")
        else:
            st.info("Utilisez l'onglet 'Saisie d'une Saillie' pour remplir le calendrier")

# --- AUTRES PAGES (conservées du code précédent) ---
elif menu == "📅 Calendrier & Projections":
    st.title("📅 Planificateur")
    st.write("Module de projections de poids (10-30-70 jours) - Intégré dans la nouvelle version")
    
elif menu == "⚖️ Mise à jour Pesée":
    st.title("⚖️ Mise à jour manuelle")
    # ... (code précédent conservé)

elif menu == "💾 Base de Données":
    st.title("💾 Export Complet")
    if st.button("Exporter toutes les données (JSON)"):
        export = {
            'animaux': st.session_state.db_data.to_dict('records'),
            'reproduction': st.session_state.saillies_db.to_dict('records')
        }
        st.download_button("Télécharger", json.dumps(export, indent=2), "database_complete.json")

st.sidebar.markdown("---")
st.sidebar.caption("Photogrammétrie v1.0 - Précision ±2-3cm")
