import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from scipy import stats
import json
import math
from PIL import Image
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="BélierSelector Pro - Démo Complète", layout="wide", page_icon="🐏")

# ============================================================
# FONCTIONS UTILITAIRES SÉCURISÉES
# ============================================================

def safe_json_loads(data, default=None):
    """Charge JSON en toute sécurité"""
    if default is None:
        default = {}
    try:
        if pd.isna(data) or data == "" or data is None:
            return default
        return json.loads(data)
    except:
        return default

def safe_date_parse(date_str):
    """Parse une date en toute sécurité"""
    try:
        if pd.isna(date_str) or date_str is None or date_str == "":
            return datetime.now().date()
        return pd.to_datetime(date_str).date()
    except:
        return datetime.now().date()

def calculer_gmq(poids_debut, poids_fin, jours):
    """Calcul sécurisé du GMQ"""
    try:
        if poids_debut is None or poids_fin is None or jours is None:
            return 0.0
        if float(jours) <= 0 or pd.isna(poids_debut) or pd.isna(poids_fin):
            return 0.0
        return round(((float(poids_fin) - float(poids_debut)) / float(jours)) * 1000, 1)
    except:
        return 0.0

def corriger_perspective(mesure, angle, dist):
    """Correction perspective sécurisée"""
    try:
        if angle == 0 or mesure == 0:
            return mesure
        return mesure / math.cos(math.radians(float(angle))) * (1 + (float(dist)-2.5)*0.02)
    except:
        return mesure

# ============================================================
# INITIALISATION AVEC DONNÉES DE DÉMONSTRATION RÉALISTES
# ============================================================

def init_demo_data():
    """Crée une base de données complète pour démonstration"""
    
    today = datetime.now().date()
    
    # 1. BÉILIERS
    beliers_data = [
        {
            'ID': 'ALG-REM-2024-101', 'Race': 'Rembi', 'Age': 24, 'BCS': 3.5,
            'PoidsActuel': 68.0, 'GMQ': 245.0, 'DateDernierePesee': str(today - timedelta(days=5)),
            'V2': 78.0, 'V4': 85.0, 'V5': 92.0, 'Sire': 'ALG-SIRE-001', 'Dam': 'ALG-DAM-045',
            'PRED_MUSCLE': 58.5, 'ICM': 1.18, 'Score_Global': 82.4,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=5)),
                'P30': str(today + timedelta(days=25)),
                'P70': str(today + timedelta(days=65))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=65)), 'poids': 53.0},
                {'date': str(today - timedelta(days=35)), 'poids': 61.5},
                {'date': str(today - timedelta(days=5)), 'poids': 68.0}
            ])
        },
        {
            'ID': 'ALG-OUL-2024-102', 'Race': 'Ouled-Djellal', 'Age': 28, 'BCS': 4.0,
            'PoidsActuel': 75.0, 'GMQ': 280.0, 'DateDernierePesee': str(today - timedelta(days=3)),
            'V2': 82.0, 'V4': 92.0, 'V5': 98.0, 'Sire': 'ALG-SIRE-002', 'Dam': 'ALG-DAM-032',
            'PRED_MUSCLE': 61.2, 'ICM': 1.20, 'Score_Global': 91.2,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=7)),
                'P30': str(today + timedelta(days=27)),
                'P70': str(today + timedelta(days=67))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=90)), 'poids': 58.0},
                {'date': str(today - timedelta(days=60)), 'poids': 66.5},
                {'date': str(today - timedelta(days=30)), 'poids': 71.2},
                {'date': str(today - timedelta(days=3)), 'poids': 75.0}
            ])
        },
        {
            'ID': 'ALG-HAM-2024-103', 'Race': 'Hamra', 'Age': 20, 'BCS': 3.0,
            'PoidsActuel': 62.0, 'GMQ': 210.0, 'DateDernierePesee': str(today - timedelta(days=8)),
            'V2': 75.0, 'V4': 82.0, 'V5': 88.0, 'Sire': 'ALG-SIRE-003', 'Dam': 'ALG-DAM-028',
            'PRED_MUSCLE': 55.8, 'ICM': 1.17, 'Score_Global': 74.5,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=2)),
                'P30': str(today + timedelta(days=22)),
                'P70': str(today + timedelta(days=62))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=68)), 'poids': 48.0},
                {'date': str(today - timedelta(days=38)), 'poids': 55.0},
                {'date': str(today - timedelta(days=8)), 'poids': 62.0}
            ])
        },
        {
            'ID': 'ALG-DMA-2024-104', 'Race': 'D\'man', 'Age': 18, 'BCS': 3.2,
            'PoidsActuel': 48.0, 'GMQ': 195.0, 'DateDernierePesee': str(today - timedelta(days=12)),
            'V2': 68.0, 'V4': 75.0, 'V5': 78.0, 'Sire': 'ALG-SIRE-004', 'Dam': 'ALG-DAM-015',
            'PRED_MUSCLE': 52.0, 'ICM': 1.15, 'Score_Global': 68.3,
            'ProchainesPesees': json.dumps({
                'P10': str(today - timedelta(days=2)),
                'P30': str(today + timedelta(days=18)),
                'P70': str(today + timedelta(days=58))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=72)), 'poids': 38.0},
                {'date': str(today - timedelta(days=42)), 'poids': 43.0},
                {'date': str(today - timedelta(days=12)), 'poids': 48.0}
            ])
        },
        {
            'ID': 'ALG-BAR-2024-105', 'Race': 'Barbare', 'Age': 30, 'BCS': 3.8,
            'PoidsActuel': 72.0, 'GMQ': 265.0, 'DateDernierePesee': str(today - timedelta(days=6)),
            'V2': 80.0, 'V4': 88.0, 'V5': 95.0, 'Sire': 'ALG-SIRE-001', 'Dam': 'ALG-DAM-055',
            'PRED_MUSCLE': 59.5, 'ICM': 1.19, 'Score_Global': 86.7,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=4)),
                'P30': str(today + timedelta(days=24)),
                'P70': str(today + timedelta(days=64))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=96)), 'poids': 55.0},
                {'date': str(today - timedelta(days=36)), 'poids': 66.0},
                {'date': str(today - timedelta(days=6)), 'poids': 72.0}
            ])
        },
        {
            'ID': 'ALG-REM-2024-106', 'Race': 'Rembi', 'Age': 22, 'BCS': 2.8,
            'PoidsActuel': 58.0, 'GMQ': 180.0, 'DateDernierePesee': str(today - timedelta(days=10)),
            'V2': 74.0, 'V4': 80.0, 'V5': 85.0, 'Sire': 'ALG-SIRE-005', 'Dam': 'ALG-DAM-022',
            'PRED_MUSCLE': 54.0, 'ICM': 1.15, 'Score_Global': 65.2,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=0)),
                'P30': str(today + timedelta(days=20)),
                'P70': str(today + timedelta(days=60))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=70)), 'poids': 46.0},
                {'date': str(today - timedelta(days=40)), 'poids': 50.0},
                {'date': str(today - timedelta(days=10)), 'poids': 58.0}
            ])
        },
        {
            'ID': 'ALG-OUL-2024-107', 'Race': 'Ouled-Djellal', 'Age': 26, 'BCS': 3.6,
            'PoidsActuel': 73.0, 'GMQ': 275.0, 'DateDernierePesee': str(today - timedelta(days=4)),
            'V2': 81.0, 'V4': 90.0, 'V5': 96.0, 'Sire': 'ALG-SIRE-002', 'Dam': 'ALG-DAM-040',
            'PRED_MUSCLE': 60.5, 'ICM': 1.19, 'Score_Global': 89.1,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=6)),
                'P30': str(today + timedelta(days=26)),
                'P70': str(today + timedelta(days=66))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=94)), 'poids': 56.0},
                {'date': str(today - timedelta(days=34)), 'poids': 67.0},
                {'date': str(today - timedelta(days=4)), 'poids': 73.0}
            ])
        },
        {
            'ID': 'ALG-THZ-2024-108', 'Race': 'Tadmit', 'Age': 21, 'BCS': 3.3,
            'PoidsActuel': 65.0, 'GMQ': 235.0, 'DateDernierePesee': str(today - timedelta(days=7)),
            'V2': 77.0, 'V4': 84.0, 'V5': 90.0, 'Sire': 'ALG-SIRE-006', 'Dam': 'ALG-DAM-038',
            'PRED_MUSCLE': 57.2, 'ICM': 1.17, 'Score_Global': 79.8,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=3)),
                'P30': str(today + timedelta(days=23)),
                'P70': str(today + timedelta(days=63))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=67)), 'poids': 51.0},
                {'date': str(today - timedelta(days=37)), 'poids': 57.5},
                {'date': str(today - timedelta(days=7)), 'poids': 65.0}
            ])
        },
        {
            'ID': 'ALG-SRA-2024-109', 'Race': 'Sidaoun', 'Age': 19, 'BCS': 3.1,
            'PoidsActuel': 61.0, 'GMQ': 225.0, 'DateDernierePesee': str(today - timedelta(days=9)),
            'V2': 76.0, 'V4': 83.0, 'V5': 87.0, 'Sire': 'ALG-SIRE-007', 'Dam': 'ALG-DAM-025',
            'PRED_MUSCLE': 56.0, 'ICM': 1.14, 'Score_Global': 76.4,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=1)),
                'P30': str(today + timedelta(days=21)),
                'P70': str(today + timedelta(days=61))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=69)), 'poids': 49.0},
                {'date': str(today - timedelta(days=39)), 'poids': 54.0},
                {'date': str(today - timedelta(days=9)), 'poids': 61.0}
            ])
        },
        {
            'ID': 'ALG-WAD-2024-110', 'Race': 'Oued Souf', 'Age': 25, 'BCS': 3.9,
            'PoidsActuel': 71.0, 'GMQ': 260.0, 'DateDernierePesee': str(today - timedelta(days=5)),
            'V2': 79.0, 'V4': 87.0, 'V5': 93.0, 'Sire': 'ALG-SIRE-008', 'Dam': 'ALG-DAM-042',
            'PRED_MUSCLE': 59.0, 'ICM': 1.18, 'Score_Global': 84.2,
            'ProchainesPesees': json.dumps({
                'P10': str(today + timedelta(days=5)),
                'P30': str(today + timedelta(days=25)),
                'P70': str(today + timedelta(days=65))
            }),
            'HistoriquePoids': json.dumps([
                {'date': str(today - timedelta(days=95)), 'poids': 52.0},
                {'date': str(today - timedelta(days=35)), 'poids': 68.0},
                {'date': str(today - timedelta(days=5)), 'poids': 71.0}
            ])
        }
    ]
    
    # 2. AGNEAUX
    naiss_base = today - timedelta(days=100)
    
    agneaux_data = [
        {'ID_Agneau': 'BRB-023-A1-2024', 'ID_Mere': 'BRB-023', 'ID_Pere': 'ALG-REM-2024-101', 
         'Date_Naissance': str(naiss_base), 'Sexe': 'Mâle', 'Poids_Naissance': 4.2, 'APGAR_Score': 9,
         'Poids_J7': 5.8, 'Date_J7': str(naiss_base + timedelta(days=7)), 'GMQ_J0_J7': 228.6,
         'Poids_J30': 12.5, 'Date_J30': str(naiss_base + timedelta(days=30)), 'GMQ_J7_J30': 295.7, 'Cotation_J30': 5,
         'Poids_J90': 32.0, 'Date_J90': str(naiss_base + timedelta(days=90)), 'GMQ_J30_J90': 325.0},
        
        {'ID_Agneau': 'BRB-023-A2-2024', 'ID_Mere': 'BRB-023', 'ID_Pere': 'ALG-REM-2024-101', 
         'Date_Naissance': str(naiss_base), 'Sexe': 'Femelle', 'Poids_Naissance': 3.8, 'APGAR_Score': 8,
         'Poids_J7': 5.2, 'Date_J7': str(naiss_base + timedelta(days=7)), 'GMQ_J0_J7': 200.0,
         'Poids_J30': 11.0, 'Date_J30': str(naiss_base + timedelta(days=30)), 'GMQ_J7_J30': 275.9, 'Cotation_J30': 4,
         'Poids_J90': 28.5, 'Date_J90': str(naiss_base + timedelta(days=90)), 'GMQ_J30_J90': 291.7},
        
        {'ID_Agneau': 'BRB-015-A1-2024', 'ID_Mere': 'BRB-015', 'ID_Pere': 'ALG-OUL-2024-102', 
         'Date_Naissance': str(naiss_base + timedelta(days=5)), 'Sexe': 'Mâle', 'Poids_Naissance': 4.8, 'APGAR_Score': 10,
         'Poids_J7': 6.5, 'Date_J7': str(naiss_base + timedelta(days=12)), 'GMQ_J0_J7': 242.9,
         'Poids_J30': 14.2, 'Date_J30': str(naiss_base + timedelta(days=35)), 'GMQ_J7_J30': 337.9, 'Cotation_J30': 5,
         'Poids_J90': 36.5, 'Date_J90': str(naiss_base + timedelta(days=95)), 'GMQ_J30_J90': 372.2},
        
        {'ID_Agneau': 'BRB-015-A2-2024', 'ID_Mere': 'BRB-015', 'ID_Pere': 'ALG-OUL-2024-102', 
         'Date_Naissance': str(naiss_base + timedelta(days=5)), 'Sexe': 'Mâle', 'Poids_Naissance': 4.5, 'APGAR_Score': 9,
         'Poids_J7': 6.1, 'Date_J7': str(naiss_base + timedelta(days=12)), 'GMQ_J0_J7': 228.6,
         'Poids_J30': 13.5, 'Date_J30': str(naiss_base + timedelta(days=35)), 'GMQ_J7_J30': 324.1, 'Cotation_J30': 5,
         'Poids_J90': 34.0, 'Date_J90': str(naiss_base + timedelta(days=95)), 'GMQ_J30_J90': 341.7},
        
        {'ID_Agneau': 'BRB-031-A1-2024', 'ID_Mere': 'BRB-031', 'ID_Pere': 'ALG-HAM-2024-103', 
         'Date_Naissance': str(naiss_base - timedelta(days=10)), 'Sexe': 'Mâle', 'Poids_Naissance': 3.2, 'APGAR_Score': 6,
         'Poids_J7': 4.0, 'Date_J7': str(naiss_base - timedelta(days=3)), 'GMQ_J0_J7': 114.3,
         'Poids_J30': 8.5, 'Date_J30': str(naiss_base + timedelta(days=20)), 'GMQ_J7_J30': 206.9, 'Cotation_J30': 2,
         'Poids_J90': 22.0, 'Date_J90': str(naiss_base + timedelta(days=80)), 'GMQ_J30_J90': 225.0},
        
        {'ID_Agneau': 'BRB-008-A1-2024', 'ID_Mere': 'BRB-008', 'ID_Pere': 'ALG-BAR-2024-105', 
         'Date_Naissance': str(naiss_base - timedelta(days=5)), 'Sexe': 'Mâle', 'Poids_Naissance': 3.9, 'APGAR_Score': 8,
         'Poids_J7': 5.4, 'Date_J7': str(naiss_base + timedelta(days=2)), 'GMQ_J0_J7': 214.3,
         'Poids_J30': 11.8, 'Date_J30': str(naiss_base + timedelta(days=25)), 'GMQ_J7_J30': 290.9, 'Cotation_J30': 4,
         'Poids_J90': 30.5, 'Date_J90': str(naiss_base + timedelta(days=85)), 'GMQ_J30_J90': 311.7},
        
        {'ID_Agneau': 'BRB-008-A2-2024', 'ID_Mere': 'BRB-008', 'ID_Pere': 'ALG-BAR-2024-105', 
         'Date_Naissance': str(naiss_base - timedelta(days=5)), 'Sexe': 'Femelle', 'Poids_Naissance': 3.6, 'APGAR_Score': 7,
         'Poids_J7': 4.9, 'Date_J7': str(naiss_base + timedelta(days=2)), 'GMQ_J0_J7': 185.7,
         'Poids_J30': 10.5, 'Date_J30': str(naiss_base + timedelta(days=25)), 'GMQ_J7_J30': 258.1, 'Cotation_J30': 3,
         'Poids_J90': 27.0, 'Date_J90': str(naiss_base + timedelta(days=85)), 'GMQ_J30_J90': 275.0},
        
        {'ID_Agneau': 'BRB-008-A3-2024', 'ID_Mere': 'BRB-008', 'ID_Pere': 'ALG-BAR-2024-105', 
         'Date_Naissance': str(naiss_base - timedelta(days=5)), 'Sexe': 'Femelle', 'Poids_Naissance': 3.4, 'APGAR_Score': 7,
         'Poids_J7': 4.6, 'Date_J7': str(naiss_base + timedelta(days=2)), 'GMQ_J0_J7': 171.4,
         'Poids_J30': 10.0, 'Date_J30': str(naiss_base + timedelta(days=25)), 'GMQ_J7_J30': 245.2, 'Cotation_J30': 3,
         'Poids_J90': 26.0, 'Date_J90': str(naiss_base + timedelta(days=85)), 'GMQ_J30_J90': 266.7},
        
        {'ID_Agneau': 'BRB-019-A1-2024', 'ID_Mere': 'BRB-019', 'ID_Pere': 'ALG-OUL-2024-107', 
         'Date_Naissance': str(naiss_base + timedelta(days=8)), 'Sexe': 'Mâle', 'Poids_Naissance': 5.0, 'APGAR_Score': 10,
         'Poids_J7': 6.8, 'Date_J7': str(naiss_base + timedelta(days=15)), 'GMQ_J0_J7': 257.1,
         'Poids_J30': 15.0, 'Date_J30': str(naiss_base + timedelta(days=38)), 'GMQ_J7_J30': 350.0, 'Cotation_J30': 5,
         'Poids_J90': 38.0, 'Date_J90': str(naiss_base + timedelta(days=98)), 'GMQ_J30_J90': 383.3},
        
        {'ID_Agneau': 'BRB-012-A1-2024', 'ID_Mere': 'BRB-012', 'ID_Pere': 'ALG-THZ-2024-108', 
         'Date_Naissance': str(naiss_base - timedelta(days=15)), 'Sexe': 'Mâle', 'Poids_Naissance': 4.0, 'APGAR_Score': 8,
         'Poids_J7': 5.5, 'Date_J7': str(naiss_base - timedelta(days=8)), 'GMQ_J0_J7': 214.3,
         'Poids_J30': 12.0, 'Date_J30': str(naiss_base + timedelta(days=15)), 'GMQ_J7_J30': 288.9, 'Cotation_J30': 4,
         'Poids_J90': 31.0, 'Date_J90': str(naiss_base + timedelta(days=75)), 'GMQ_J30_J90': 316.7},
        
        {'ID_Agneau': 'BRB-027-A1-2024', 'ID_Mere': 'BRB-027', 'ID_Pere': 'ALG-WAD-2024-110', 
         'Date_Naissance': str(naiss_base + timedelta(days=3)), 'Sexe': 'Femelle', 'Poids_Naissance': 3.9, 'APGAR_Score': 8,
         'Poids_J7': 5.3, 'Date_J7': str(naiss_base + timedelta(days=10)), 'GMQ_J0_J7': 200.0,
         'Poids_J30': 11.5, 'Date_J30': str(naiss_base + timedelta(days=33)), 'GMQ_J7_J30': 295.5, 'Cotation_J30': 4,
         'Poids_J90': 29.5, 'Date_J90': str(naiss_base + timedelta(days=93)), 'GMQ_J30_J90': 300.0},
        
        {'ID_Agneau': 'BRB-045-A1-2024', 'ID_Mere': 'BRB-045', 'ID_Pere': 'ALG-SRA-2024-109', 
         'Date_Naissance': str(naiss_base - timedelta(days=8)), 'Sexe': 'Mâle', 'Poids_Naissance': 3.7, 'APGAR_Score': 7,
         'Poids_J7': 5.0, 'Date_J7': str(naiss_base - timedelta(days=1)), 'GMQ_J0_J7': 185.7,
         'Poids_J30': 10.8, 'Date_J30': str(naiss_base + timedelta(days=22)), 'GMQ_J7_J30': 258.1, 'Cotation_J30': 3,
         'Poids_J90': 28.0, 'Date_J90': str(naiss_base + timedelta(days=82)), 'GMQ_J30_J90': 286.7},
        
        {'ID_Agneau': 'BRB-033-A1-2024', 'ID_Mere': 'BRB-033', 'ID_Pere': 'ALG-REM-2024-101', 
         'Date_Naissance': str(naiss_base + timedelta(days=12)), 'Sexe': 'Femelle', 'Poids_Naissance': 3.5, 'APGAR_Score': 8,
         'Poids_J7': 4.8, 'Date_J7': str(naiss_base + timedelta(days=19)), 'GMQ_J0_J7': 185.7,
         'Poids_J30': 10.5, 'Date_J30': str(naiss_base + timedelta(days=42)), 'GMQ_J7_J30': 276.2, 'Cotation_J30': 3,
         'Poids_J90': 27.5, 'Date_J90': str(naiss_base + timedelta(days=102)), 'GMQ_J30_J90': 283.3},
         
        {'ID_Agneau': 'BRB-051-A1-2024', 'ID_Mere': 'BRB-051', 'ID_Pere': 'ALG-OUL-2024-102', 
         'Date_Naissance': str(naiss_base - timedelta(days=20)), 'Sexe': 'Mâle', 'Poids_Naissance': 4.6, 'APGAR_Score': 9,
         'Poids_J7': 6.2, 'Date_J7': str(naiss_base - timedelta(days=13)), 'GMQ_J0_J7': 228.6,
         'Poids_J30': 13.5, 'Date_J30': str(naiss_base + timedelta(days=10)), 'GMQ_J7_J30': 324.1, 'Cotation_J30': 5,
         'Poids_J90': 35.0, 'Date_J90': str(naiss_base + timedelta(days=70)), 'GMQ_J30_J90': 358.3},
         
        {'ID_Agneau': 'BRB-016-A1-2024', 'ID_Mere': 'BRB-016', 'ID_Pere': 'ALG-DMA-2024-104', 
         'Date_Naissance': str(naiss_base + timedelta(days=6)), 'Sexe': 'Femelle', 'Poids_Naissance': 3.3, 'APGAR_Score': 7,
         'Poids_J7': 4.5, 'Date_J7': str(naiss_base + timedelta(days=13)), 'GMQ_J0_J7': 171.4,
         'Poids_J30': 9.8, 'Date_J30': str(naiss_base + timedelta(days=36)), 'GMQ_J7_J30': 241.4, 'Cotation_J30': 3,
         'Poids_J90': 25.5, 'Date_J90': str(naiss_base + timedelta(days=96)), 'GMQ_J30_J90': 261.7}
    ]
    
    # 3. SAILLIES
    saillies_data = [
        {'ID_Saillie': 'SAIL-20240115-001', 'ID_Belier': 'ALG-REM-2024-101', 'ID_Brebis': 'BRB-023', 
         'Date_Saillie': str(today - timedelta(days=280)), 'Gest_Confirme': 'Oui', 
         'Date_Agnelage_Prevu': str(today - timedelta(days=130))},
        
        {'ID_Saillie': 'SAIL-20240120-002', 'ID_Belier': 'ALG-OUL-2024-102', 'ID_Brebis': 'BRB-015', 
         'Date_Saillie': str(today - timedelta(days=275)), 'Gest_Confirme': 'Oui', 
         'Date_Agnelage_Prevu': str(today - timedelta(days=125))},
        
        {'ID_Saillie': 'SAIL-20240201-003', 'ID_Belier': 'ALG-HAM-2024-103', 'ID_Brebis': 'BRB-031', 
         'Date_Saillie': str(today - timedelta(days=290)), 'Gest_Confirme': 'Oui', 
         'Date_Agnelage_Prevu': str(today - timedelta(days=140))},
        
        {'ID_Saillie': 'SAIL-20241115-004', 'ID_Belier': 'ALG-BAR-2024-105', 'ID_Brebis': 'BRB-100', 
         'Date_Saillie': str(today - timedelta(days=45)), 'Gest_Confirme': 'Oui', 
         'Date_Agnelage_Prevu': str(today + timedelta(days=105))},
        
        {'ID_Saillie': 'SAIL-20241020-005', 'ID_Belier': 'ALG-OUL-2024-107', 'ID_Brebis': 'BRB-098', 
         'Date_Saillie': str(today - timedelta(days=70)), 'Gest_Confirme': 'Oui', 
         'Date_Agnelage_Prevu': str(today + timedelta(days=80))},
        
        {'ID_Saillie': 'SAIL-20241201-006', 'ID_Belier': 'ALG-REM-2024-101', 'ID_Brebis': 'BRB-110', 
         'Date_Saillie': str(today - timedelta(days=10)), 'Gest_Confirme': 'Non testé', 
         'Date_Agnelage_Prevu': str(today + timedelta(days=140))}
    ]
    
    agnelages_data = [
        {'ID_Agnelage': 'AGN-20240515-001', 'ID_Saillie': 'SAIL-20240115-001', 'ID_Mere': 'BRB-023', 
         'ID_Pere': 'ALG-REM-2024-101', 'Date_Naissance': str(today - timedelta(days=130)),
         'Nombre_Vivants': 2, 'APGAR_Moyen': 8.5},
        
        {'ID_Agnelage': 'AGN-20240520-002', 'ID_Saillie': 'SAIL-20240120-002', 'ID_Mere': 'BRB-015', 
         'ID_Pere': 'ALG-OUL-2024-102', 'Date_Naissance': str(today - timedelta(days=125)),
         'Nombre_Vivants': 2, 'APGAR_Moyen': 9.5},
        
        {'ID_Agnelage': 'AGN-20240610-003', 'ID_Saillie': 'SAIL-20240201-003', 'ID_Mere': 'BRB-031', 
         'ID_Pere': 'ALG-HAM-2024-103', 'Date_Naissance': str(today - timedelta(days=140)),
         'Nombre_Vivants': 1, 'APGAR_Moyen': 6.0}
    ]
    
    # 4. CONSOMMATION
    conso_data = [
        {
            'ID_Lot': 'LOT-2024-POSTSEVRAGE-A', 'Date_Debut': str(today - timedelta(days=90)), 
            'Date_Fin': str(today - timedelta(days=30)), 'Duree_Jours': 60,
            'Nombre_Tetes': 8, 'Poids_Total_Debut': 160.0, 'Poids_Total_Fin': 280.0,
            'Aliment_Distribue_Kg': 480.0, 'Aliment_MS_Perc': 88.0,
            'Consommation_Matiere_Seche': 422.4, 'Gain_Lot_Kg': 120.0,
            'IC_Lot': 3.52, 'Cout_Kg_Gain': 1.23, 'Marge_Alimentaire': 296.8,
            'Efficacite': 'Excellente'
        },
        {
            'ID_Lot': 'LOT-2024-CROISSANCE-B', 'Date_Debut': str(today - timedelta(days=60)), 
            'Date_Fin': str(today - timedelta(days=10)), 'Duree_Jours': 50,
            'Nombre_Tetes': 7, 'Poids_Total_Debut': 140.0, 'Poids_Total_Fin': 235.0,
            'Aliment_Distribue_Kg': 420.0, 'Aliment_MS_Perc': 88.0,
            'Consommation_Matiere_Seche': 369.6, 'Gain_Lot_Kg': 95.0,
            'IC_Lot': 3.89, 'Cout_Kg_Gain': 1.36, 'Marge_Alimentaire': 210.9,
            'Efficacite': 'Bonne'
        },
        {
            'ID_Lot': 'LOT-2024-PROBLEME-C', 'Date_Debut': str(today - timedelta(days=45)), 
            'Date_Fin': str(today - timedelta(days=5)), 'Duree_Jours': 40,
            'Nombre_Tetes': 6, 'Poids_Total_Debut': 180.0, 'Poids_Total_Fin': 240.0,
            'Aliment_Distribue_Kg': 450.0, 'Aliment_MS_Perc': 88.0,
            'Consommation_Matiere_Seche': 396.0, 'Gain_Lot_Kg': 60.0,
            'IC_Lot': 6.60, 'Cout_Kg_Gain': 2.31, 'Marge_Alimentaire': -38.6,
            'Efficacite': 'Faible'
        }
    ]
    
    return pd.DataFrame(beliers_data), pd.DataFrame(agneaux_data), pd.DataFrame(saillies_data), \
           pd.DataFrame(agnelages_data), pd.DataFrame(conso_data)

# --- INITIALISATION SESSION STATE ---
if 'initialized' not in st.session_state:
    try:
        st.session_state.db_data, st.session_state.agneaux_db, st.session_state.saillies_db, \
        st.session_state.agnelages_db, st.session_state.consommation_lot_db = init_demo_data()
        st.session_state.initialized = True
        st.session_state.mesures_photo = []
    except Exception as e:
        st.error(f"Erreur initialisation données: {e}")
        # Créer DataFrames vides en cas d'erreur
        st.session_state.db_data = pd.DataFrame()
        st.session_state.agneaux_db = pd.DataFrame()
        st.session_state.saillies_db = pd.DataFrame()
        st.session_state.agnelages_db = pd.DataFrame()
        st.session_state.consommation_lot_db = pd.DataFrame()

# ============================================================
# FONCTION ALERTES SÉCURISÉE
# ============================================================

def get_alerts():
    """Récupère les alertes de manière sécurisée"""
    alerts = []
    today = datetime.now().date()
    
    try:
        # Alertes pesées béliers
        if 'db_data' in st.session_state and not st.session_state.db_data.empty:
            for _, row in st.session_state.db_data.iterrows():
                if 'ProchainesPesees' in row and pd.notna(row['ProchainesPesees']):
                    try:
                        dates = safe_json_loads(row['ProchainesPesees'], {})
                        for periode, date_str in dates.items():
                            try:
                                date_obj = safe_date_parse(date_str)
                                jours = (date_obj - today).days
                                if -2 <= jours <= 3:
                                    alerts.append({
                                        'type': 'pesee', 'id': str(row.get('ID', 'Inconnu')), 
                                        'date': date_str, 'jours': jours, 
                                        'icon': '⚖️', 'severite': 'high' if jours <= 0 else 'medium'
                                    })
                            except:
                                continue
                    except:
                        continue
        
        # Alertes agnelages
        if 'saillies_db' in st.session_state and not st.session_state.saillies_db.empty:
            for _, row in st.session_state.saillies_db.iterrows():
                try:
                    if pd.notna(row.get('Date_Agnelage_Prevu')) and row.get('Gest_Confirme') == 'Oui':
                        date_obj = safe_date_parse(row['Date_Agnelage_Prevu'])
                        jours = (date_obj - today).days
                        if -3 <= jours <= 7:
                            alerts.append({
                                'type': 'agnelage', 'brebis': str(row.get('ID_Brebis', 'Inconnu')), 
                                'date': str(row.get('Date_Agnelage_Prevu')), 'jours': jours, 
                                'icon': '🍼', 'severite': 'high'
                            })
                except:
                    continue
        
        # Alertes croissance agneaux
        if 'agneaux_db' in st.session_state and not st.session_state.agneaux_db.empty:
            for _, row in st.session_state.agneaux_db.iterrows():
                try:
                    gmq = row.get('GMQ_J7_J30')
                    if pd.notna(gmq) and isinstance(gmq, (int, float)) and gmq < 200:
                        alerts.append({
                            'type': 'croissance_faible', 
                            'agneau': str(row.get('ID_Agneau', 'Inconnu')), 
                            'gmq': gmq, 'icon': '📉', 'severite': 'high'
                        })
                except:
                    continue
    except Exception as e:
        st.sidebar.error(f"Erreur alertes: {e}")
    
    return sorted(alerts, key=lambda x: abs(x.get('jours', 0)))

# --- INTERFACE ---
st.sidebar.title("🐏 BélierSelector Pro")
st.sidebar.success("✅ Mode Démo Actif (Données pré-chargées)")

menu = st.sidebar.radio("Navigation", [
    "🏠 Tableau de Bord",
    "👶 Suivi Agneaux & Croissance", 
    "🧬 Performance Béliers",
    "📸 Photogrammétrie",
    "🌾 Efficacité Alimentaire",
    "❤️ Reproduction & Alertes"
])

# Alertes avec gestion d'erreur
try:
    alerts = get_alerts()
    st.sidebar.divider()
    st.sidebar.subheader(f"🔔 Alertes Actives ({len(alerts)})")
    if alerts:
        for alert in alerts[:5]:
            try:
                msg = f"{alert.get('icon', '•')} "
                if alert['type'] == 'pesee':
                    msg += f"{str(alert.get('id', 'N/A'))[:10]}: J{alert.get('jours', 0):+d}"
                elif alert['type'] == 'agnelage':
                    msg += f"{str(alert.get('brebis', 'N/A'))[:10]}: J{alert.get('jours', 0)}"
                elif alert['type'] == 'croissance_faible':
                    msg += f"{str(alert.get('agneau', 'N/A'))[:8]} GMQ {alert.get('gmq', 0)}"
                
                if alert.get('severite') == 'high':
                    st.sidebar.error(msg)
                else:
                    st.sidebar.warning(msg)
            except:
                continue
    else:
        st.sidebar.info("Aucune alerte urgente")
except Exception as e:
    st.sidebar.error("Erreur affichage alertes")

# --- PAGE D'ACCUEIL ---
if menu == "🏠 Tableau de Bord":
    st.title("🏠 Tableau de Bord - Elevage Démo")
    
    try:
        # Vérification existence données
        if 'db_data' not in st.session_state or st.session_state.db_data.empty:
            st.error("⚠️ Données non chargées. Veuillez réinitialiser.")
            if st.button("🔄 Réinitialiser les données"):
                del st.session_state.initialized
                st.rerun()
            st.stop()
        
        # Métriques globales
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🐏 Béliers", len(st.session_state.db_data))
        col2.metric("👶 Agneaux", len(st.session_state.agneaux_db) if 'agneaux_db' in st.session_state else 0)
        col3.metric("🍼 Agnelages", len(st.session_state.agnelages_db) if 'agnelages_db' in st.session_state else 0)
        col4.metric("💰 Lots conduits", len(st.session_state.consommation_lot_db) if 'consommation_lot_db' in st.session_state else 0)
        col5.metric("🔔 Alertes", len(alerts), delta="Actives")
        
        st.divider()
        
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("📈 Top Performances Béliers")
            try:
                if 'Score_Global' in st.session_state.db_data.columns:
                    top_beliers = st.session_state.db_data.nlargest(3, 'Score_Global')[['ID', 'Race', 'Score_Global', 'GMQ']]
                    st.dataframe(top_beliers, hide_index=True)
                else:
                    st.info("Données de score non disponibles")
            except Exception as e:
                st.error(f"Erreur affichage béliers: {e}")
            
            st.subheader("🌾 Dernier Lot Alimenté")
            try:
                if 'consommation_lot_db' in st.session_state and not st.session_state.consommation_lot_db.empty:
                    last_lot = st.session_state.consommation_lot_db.iloc[-1]
                    st.write(f"**{last_lot.get('ID_Lot', 'N/A')}** ({last_lot.get('Duree_Jours', 0)} jours)")
                    st.write(f"IC: {last_lot.get('IC_Lot', 0)} | Marge: {last_lot.get('Marge_Alimentaire', 0):.0f} €")
                    if last_lot.get('IC_Lot', 0) > 6:
                        st.error("⚠️ IC élevé - Problème détecté!")
            except Exception as e:
                st.error(f"Erreur affichage lot: {e}")
        
        with col_right:
            st.subheader("👶 Meilleurs Agneaux (J30)")
            try:
                if 'agneaux_db' in st.session_state and not st.session_state.agneaux_db.empty:
                    if 'Cotation_J30' in st.session_state.agneaux_db.columns and 'GMQ_J7_J30' in st.session_state.agneaux_db.columns:
                        top_agn = st.session_state.agneaux_db[st.session_state.agneaux_db['Cotation_J30'].notna()].nlargest(3, 'GMQ_J7_J30')[['ID_Agneau', 'Poids_J30', 'GMQ_J7_J30', 'Cotation_J30']]
                        if not top_agn.empty:
                            st.dataframe(top_agn, hide_index=True)
                        else:
                            st.info("Aucun agneau avec données J30")
                    else:
                        st.info("Colonnes de croissance non disponibles")
            except Exception as e:
                st.error(f"Erreur affichage agneaux: {e}")
            
        
