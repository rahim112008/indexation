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
                {'date': str(today
