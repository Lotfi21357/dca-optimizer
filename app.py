# DCA Optimizer - Optimisation du DCA sur DCAM.PA (Amundi PEA Monde)
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import warnings
warnings.filterwarnings("ignore")

# ---------- AUTO-REFRESH (toutes les 2 minutes) ----------
st_autorefresh(interval=120_000, key="autorefresh")

# ---------- CONFIGURATION PAGE ----------
st.set_page_config(
    page_title="DCA Optimizer DCAM",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Style sobre pour mobile
st.markdown("""
<style>
.stApp {max-width: 100%; padding: 0.5rem;}
.big-number {font-size: 2rem; font-weight: bold; text-align: center;}
.score-box {font-size: 1.4rem; font-weight: bold; text-align: center; padding: 0.8rem; border-radius: 1rem; margin: 1rem 0;}
.warning-box {background-color: #fff3cd; padding: 0.5rem; border-radius: 0.5rem; margin: 0.5rem 0; font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)

# ---------- PARAMÈTRES DU PORTEFEUILLE ----------
TICKER = "DCAM.PA"
NB_PARTS = 481
PRM = 5.5937  # Prix de revient moyen poche

# ---------- FONCTIONS ----------
@st.cache_data(ttl=120, show_spinner=False)
def load_daily_data():
    """Récupère l'historique journalier des 3 derniers mois."""
    start = datetime.now() - timedelta(days=120)  # marge pour RSI
    df = yf.download(TICKER, start=start, progress=False)
    if df.empty:
        return None
    return df

@st.cache_data(ttl=120, show_spinner=False)
def load_intraday_data():
    """Récupère les données intraday de la journée (intervalle 5 minutes)."""
    # Yahoo permet '5m' pour les 60 derniers jours, mais pour aujourd'hui seulement
    df = yf.download(TICKER, period="1d", interval="5m", progress=False)
    if df.empty:
        return None
    return df

def compute_vwap(df):
    """Calcule le VWAP à partir des colonnes High, Low, Close, Volume."""
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (typical_price * df['Volume']).cumsum() / df['Volume'].cumsum()
    return vwap.iloc[-1] if not vwap.empty else None

def compute_bollinger(df, length=20, std=2):
    """Retourne les bandes de Bollinger (lower, middle, upper) en utilisant pandas_ta."""
    bbands = ta.bbands(df['Close'], length=length, std=std)
    if bbands is not None:
        last = bbands.iloc[-1]
        return last[f'BBL_{length}_{std}'], last[f'BBM_{length}_{std}'], last[f'BBU_{length}_{std}']
    return None, None, None

def compute_rsi(df, length=14):
    """Calcule le RSI avec pandas_ta."""
    rsi_series = ta.rsi(df['Close'], length=length)
    return rsi_series.iloc[-1] if rsi_series is not None and not rsi_series.empty else None

# ---------- CHARGEMENT DES DONNÉES ----------
daily_data = load_daily_data()
if daily_data is None:
    st.error("Impossible de récupérer les données journalières. Vérifiez la connexion.")
    st.stop()

# Prix actuel (dernier close journalier disponible)
current_price = daily_data['Close'].iloc[-1]

# Module 1 : Analyse journalière
# RSI(14)
rsi_val = compute_rsi(daily_data, 14)

# Plus haut des 20 derniers jours et drawdown
high_20 = daily_data['High'].rolling(20).max().iloc[-1]
drawdown_pct = (current_price - high_20) / high_20 * 100  # négatif si en dessous

# Score de journée (0 à 10)
score = 0
if rsi_val is not None:
    if rsi_val < 30:
        score += 4
    elif rsi_val < 45:
        score += 3
    elif rsi_val > 70:
        score -= 3
if drawdown_pct < -2:
    score += 3
elif drawdown_pct < -1.5:
    score += 2
elif drawdown_pct < -1:
    score += 1
score = max(0, min(10, score + 5))  # recentrage autour de 5

# Conseil
if rsi_val is not None and rsi_val < 45 and drawdown_pct < -1.5:
    conseil = "✅ Aujourd'hui est un bon jour statistique pour ton DCA"
elif rsi_val is not None and rsi_val > 70:
    conseil = "⚠️ Risque de repli, envisagez d'attendre 24/48h"
else:
    conseil = "ℹ️ Conditions neutres, vous pouvez investir sans urgence"

# Module 2 : Intraday (si marché ouvert)
# Heure de Paris (approximative, on considère ouverture 9h-17h30)
now = datetime.now()
market_open = (now.hour >= 9 and now.hour < 17) or (now.hour == 17 and now.minute <= 30)
intraday_available = False
vwap = None
boll_lower, boll_mid, boll_upper = None, None, None
price_limit = None

if market_open:
    intraday = load_intraday_data()
    if intraday is not None and not intraday.empty:
        intraday_available = True
        # VWAP
        vwap = compute_vwap(intraday)
        # Bandes de Bollinger (20 périodes sur 5 min)
        boll_lower, boll_mid, boll_upper = compute_bollinger(intraday, 20, 2)
        # Prix limite idéal : VWAP - 0.05% (si VWAP disponible)
        if vwap is not None:
            price_limit = vwap * 0.9995  # -0.05%
        else:
            price_limit = current_price * 0.999  # fallback léger
    else:
        intraday_available = False

# ---------- INTERFACE ----------
st.title("🎯 DCAM DCA Optimizer")
st.caption(f"Données au {now.strftime('%d/%m/%Y %H:%M')} · Rafraîchi toutes les 2 min")

# Position actuelle
st.markdown("### 📌 Ma position")
col1, col2, col3 = st.columns(3)
col1.metric("Parts", f"{NB_PARTS}")
col2.metric("PRM (poche)", f"{PRM:.4f} €")
col3.metric("Dernier cours", f"{current_price:.4f} €")

# Performance latente
gain_pct = (current_price - PRM) / PRM * 100
gain_eur = NB_PARTS * (current_price - PRM)
st.markdown(f"**Gain latent :** {gain_eur:+,.2f} € ({gain_pct:+.2f} %)")

st.markdown("---")

# ========== MODULE 1 : ANALYSE DE LA JOURNÉE ==========
st.header("📊 Analyse journalière (faut-il acheter aujourd'hui ?)")

col4, col5, col6 = st.columns(3)
col4.metric("RSI (14)", f"{rsi_val:.1f}" if rsi_val is not None else "N/A")
col5.metric("Plus haut 20j", f"{high_20:.4f} €")
col6.metric("Drawdown", f"{drawdown_pct:+.2f} %")

# Score visuel (barre de progression)
score_pct = score / 10
st.markdown(f"**Score de la journée : {score}/10**")
st.progress(score_pct)

# Conseil encadré
st.markdown(f"""
<div class="score-box" style="background-color: {'#d4edda' if 'bon jour' in conseil else '#fff3cd' if 'risque' in conseil.lower() else '#e9ecef'};">
    {conseil}
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ========== MODULE 2 : EXÉCUTION INTRAJOUR ==========
st.header("⚡ Exécution intraday (ordre limite)")

if market_open:
    if intraday_available:
        st.success("Marché ouvert – données intraday disponibles")
        col7, col8, col9 = st.columns(3)
        col7.metric("VWAP", f"{vwap:.4f} €" if vwap else "N/A")
        if boll_lower and boll_upper:
            col8.metric("Boll. inf.", f"{boll_lower:.4f} €")
            col9.metric("Boll. sup.", f"{boll_upper:.4f} €")
        # Prix limite idéal
        if price_limit:
            st.markdown(f"**Prix limite idéal suggéré : `{price_limit:.4f} €`** (VWAP -0.05%)")
        else:
            st.info("Données insuffisantes pour proposer un prix limite.")
    else:
        st.warning("Marché ouvert, mais données intraday non disponibles pour le moment. Réessayez dans quelques minutes.")
else:
    st.info("Marché fermé. Les données intraday seront disponibles pendant les heures d'ouverture (9h-17h30, Paris).")

# Avertissement
st.markdown("""
<div class="warning-box">
⚠️ <strong>Attention :</strong> Les données Yahoo Finance peuvent avoir un délai de 15 minutes. Vérifiez le prix direct sur votre courtier avant d'exécuter l'ordre limite proposé.
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.caption("DCA Optimizer · Outil d'aide à la décision, pas un conseil en investissement")
