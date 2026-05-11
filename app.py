# DCA Optimizer - Exécution Professionnelle sur DCAM.PA
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import warnings
warnings.filterwarnings("ignore")

# ---------- AUTO-REFRESH (2 min) ----------
st_autorefresh(interval=120_000, key="autorefresh")

# ---------- CONFIGURATION PAGE ----------
st.set_page_config(page_title="DCA Optimizer", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

# Custom CSS moderne
st.markdown("""
<style>
    body {font-family: 'Inter', sans-serif; background-color: #f8f9fa;}
    .stApp {background-color: #f8f9fa;}
    .big-price {font-size: 2.8rem; font-weight: 800; color: #0d6efd; text-align: center;}
    .decision-banner {font-size: 1.6rem; font-weight: bold; text-align: center; padding: 0.8rem; border-radius: 1rem; margin: 1rem 0;}
    .warning-box {background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 0.8rem; border-radius: 0.5rem; margin: 0.5rem 0;}
    .metric-card {background: white; border-radius: 1rem; padding: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 0.5rem;}
    .sidebar .stNumberInput label {font-size: 0.9rem; font-weight: 600;}
</style>
""", unsafe_allow_html=True)

# ---------- SIDEBAR PARAMÈTRES ----------
st.sidebar.header("⚙️ Paramètres Portefeuille")
parts = st.sidebar.number_input("Nombre de parts actuelles", min_value=1, value=481, step=1)
prm_actuel = st.sidebar.number_input("PRM actuel (€)", min_value=0.01, value=5.261, step=0.001, format="%.4f")
bonus = st.sidebar.number_input("Bonus à injecter (€)", min_value=0.0, value=160.0, step=10.0)

# PRM ajusté (le bonus réduit le coût de revient)
prm_ajuste = ((parts * prm_actuel) - bonus) / parts
st.sidebar.metric("PRM ajusté (après bonus)", f"{prm_ajuste:.4f} €", delta=f"-{bonus:.2f} € de bonus")

# Montant à investir pour le calculateur
montant_investir = st.sidebar.number_input("Montant à investir (€)", min_value=0.0, value=500.0, step=100.0)

st.sidebar.caption("Les données sont mises à jour toutes les 2 minutes (09:00-17:30).")

# ---------- FONCTIONS DE CALCUL ----------
@st.cache_data(ttl=120, show_spinner=False)
def get_data(ticker, period="3mo", interval="1d"):
    """Récupère les données avec fallback"""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            # Tentative avec l'objet Ticker
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval)
        return df
    except Exception:
        return pd.DataFrame()

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_atr(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def compute_vwap(df):
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (typical * df['Volume']).cumsum() / df['Volume'].cumsum()
    return vwap.iloc[-1]

def compute_bollinger(series, window=20, std=2):
    sma = series.rolling(window).mean()
    std = series.rolling(window).std()
    return sma.iloc[-1] - std.iloc[-1]*std, sma.iloc[-1], sma.iloc[-1] + std.iloc[-1]*std

# ---------- CHARGEMENT DES DONNÉES ----------
now = datetime.now()
market_open = (now.hour >= 9 and now.hour < 17) or (now.hour == 17 and now.minute <= 30)

daily = get_data("DCAM.PA", period="3mo")
if daily.empty:
    st.error("Données journalières indisponibles. Veuillez réessayer.")
    st.stop()

# Remplir les éventuelles données manquantes
daily.ffill(inplace=True)

current_price = daily['Close'].iloc[-1]
open_price = daily['Open'].iloc[-1] if 'Open' in daily.columns else None
prev_close = daily['Close'].iloc[-2] if len(daily) > 1 else None

# Intraday (5 minutes) uniquement si marché ouvert
intraday = pd.DataFrame()
if market_open:
    intraday = get_data("DCAM.PA", period="1d", interval="5m")
    if not intraday.empty:
        intraday.ffill(inplace=True)
    else:
        intraday = pd.DataFrame()

# ---------- INDICATEURS JOURNALIERS ----------
rsi_series = compute_rsi(daily['Close'], 14)
rsi_val = rsi_series.iloc[-1] if not rsi_series.empty else None

high_20 = daily['High'].rolling(20).max().iloc[-1]
drawdown_pct = (current_price - high_20) / high_20 * 100

atr_series = compute_atr(daily, 14)
atr_val = atr_series.iloc[-1] if not atr_series.empty else None
volatility_pct = (atr_val / current_price * 100) if atr_val and current_price else 0

# Score de journée (0-10)
score = 5
if rsi_val:
    if rsi_val < 30: score += 4
    elif rsi_val < 45: score += 2
    elif rsi_val > 70: score -= 3
if drawdown_pct < -2: score += 3
elif drawdown_pct < -1.5: score += 2
elif drawdown_pct < -1: score += 1
if volatility_pct > 2.0: score -= 2  # forte volatilité pénalise
score = max(0, min(10, score))

# ---------- SENTIMENT WALL STREET ----------
es_fut = get_data("ES=F", period="1d", interval="5m")  # intraday pour les futures
nq_fut = get_data("NQ=F", period="1d", interval="5m")
es_var = 0
nq_var = 0
if not es_fut.empty and not nq_fut.empty:
    es_close = es_fut['Close'].iloc[-1]
    nq_close = nq_fut['Close'].iloc[-1]
    # Variation par rapport à la veille (utiliser le close précédent si dispo, sinon open)
    if len(es_fut) > 1:
        es_prev = es_fut['Close'].iloc[-2]
        es_var = (es_close - es_prev) / es_prev * 100
    if len(nq_fut) > 1:
        nq_prev = nq_fut['Close'].iloc[-2]
        nq_var = (nq_close - nq_prev) / nq_prev * 100

us_alert = False
if 14 <= now.hour < 16 or (now.hour == 16 and now.minute == 0):
    if es_var < -0.8 or nq_var < -0.8:
        us_alert = True

# Règle du gap
gap_alert = False
if open_price and prev_close:
    gap_pct = (open_price - prev_close) / prev_close * 100
    if abs(gap_pct) > 0.5:
        gap_alert = True

# ---------- MODULE INTRAJOUR ----------
vwap = None
boll_lower = boll_upper = None
if market_open and not intraday.empty:
    vwap = compute_vwap(intraday)
    if len(intraday) >= 20:
        boll_lower, _, boll_upper = compute_bollinger(intraday['Close'], 20, 2)

price_limit = vwap * 0.9995 if vwap else current_price * 0.999

# ---------- CALCULATEUR DE PARTS ----------
if montant_investir > 0 and current_price > 0:
    nb_parts_frac = montant_investir / price_limit
    nb_parts_entieres = int(nb_parts_frac)
    cout_total = nb_parts_entieres * price_limit
    nouveau_prm = (parts * prm_ajuste + cout_total) / (parts + nb_parts_entieres) if nb_parts_entieres > 0 else prm_ajuste
else:
    nb_parts_entieres = 0
    cout_total = 0
    nouveau_prm = prm_ajuste

# ---------- DÉCISION FINALE ----------
decision = "ATTENDRE"
if us_alert:
    decision = "PRUDENCE MACRO"
elif score >= 7:
    decision = "ACHAT FAVORABLE"
elif score >= 4:
    decision = "ATTENDRE"
else:
    decision = "PRUDENCE MACRO"

# Couleurs associées
colors = {"ACHAT FAVORABLE": "green", "ATTENDRE": "orange", "PRUDENCE MACRO": "red"}

# ---------- INTERFACE ----------
st.title("🎯 DCAM DCA Optimizer")
st.caption(f"Analyse du {now.strftime('%d/%m/%Y à %H:%M')} · Mise à jour auto / 2 min")

# Bannière de décision
st.markdown(f"""
<div class="decision-banner" style="background-color: {colors[decision]}; color: white;">
    {decision}
</div>
""", unsafe_allow_html=True)

# Bloc 1 : Résumé & Score
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric("Prix actuel DCAM", f"{current_price:.4f} €")
    st.metric("Ouverture", f"{open_price:.4f} €" if open_price else "N/A")
    st.metric("Clôture veille", f"{prev_close:.4f} €" if prev_close else "N/A")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric("Score de la journée", f"{score}/10")
    st.progress(score/10)
    st.markdown(f"**RSI (14)** : {rsi_val:.1f}" if rsi_val else "RSI N/A")
    st.markdown(f"**Drawdown 20j** : {drawdown_pct:.2f}%")
    st.markdown(f"**Volatilité (ATR)** : {volatility_pct:.2f}%")
    st.markdown('</div>', unsafe_allow_html=True)

with col3:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric("PRM ajusté", f"{prm_ajuste:.4f} €")
    gain_latent = current_price - prm_ajuste
    gain_pct = (gain_latent / prm_ajuste) * 100
    st.metric("Gain latent", f"{gain_latent:.4f} €", delta=f"{gain_pct:+.2f}%")
    st.markdown('</div>', unsafe_allow_html=True)

# Bloc Alertes Macro
if us_alert or gap_alert:
    st.markdown("---")
    if us_alert:
        st.warning("⚠️ Volatilité US détectée (Futures < -0.8% entre 14h30-16h00). Attendre 15h45 pour l'achat.")
    if gap_alert:
        st.warning("⚠️ Gap d'ouverture > 0.5% détecté. Attendre 10h30 pour une éventuelle stabilisation.")
    st.markdown("---")

# Bloc Exécution intraday
if market_open and not intraday.empty:
    st.markdown("### ⚡ Exécution Intraday (5 min)")
    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric("VWAP", f"{vwap:.4f} €" if vwap else "N/A")
        if boll_lower:
            st.metric("Boll. Inf.", f"{boll_lower:.4f} €")
    with col5:
        # Prix limite très visible
        st.markdown(f'<div class="big-price">{price_limit:.4f} €</div>', unsafe_allow_html=True)
        st.caption("Prix limite idéal (VWAP -0.05%)")
    with col6:
        if boll_upper:
            st.metric("Boll. Sup.", f"{boll_upper:.4f} €")
        st.metric("Volume (5m)", f"{intraday['Volume'].iloc[-1]:.0f}" if 'Volume' in intraday.columns else "N/A")
else:
    if market_open:
        st.info("Données intraday non disponibles pour le moment (patientez quelques minutes).")
    else:
        st.info("Marché fermé. Le module intraday sera actif aux horaires d'ouverture (9h-17h30).")

# Calculateur de parts
st.markdown("### 🧮 Calculateur de parts")
colA, colB, colC = st.columns(3)
with colA:
    st.metric("Parts achetées", f"{nb_parts_entieres}")
with colB:
    st.metric("Coût total", f"{cout_total:.2f} €")
with colC:
    st.metric("Nouveau PRM estimé", f"{nouveau_prm:.4f} €")

# Avertissement
st.markdown("""
<div class="warning-box">
⚠️ <strong>Attention :</strong> Yahoo Finance peut présenter un décalage jusqu'à 15 minutes. Vérifiez toujours le cours réel sur votre courtier avant d'exécuter un ordre.
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.caption("DCA Optimizer · Outil d'aide à la décision — ne constitue pas un conseil en investissement.")
