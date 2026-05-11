import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import warnings
warnings.filterwarnings("ignore")

# ---------- CONFIGURATION PAGE ----------
st.set_page_config(
    page_title="DCA Optimizer DCAM",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.stApp {max-width: 100%; padding: 0.5rem;}
.score-box {font-size: 1.4rem; font-weight: bold; text-align: center; padding: 0.8rem; border-radius: 1rem; margin: 1rem 0;}
.warning-box {background-color: #fff3cd; padding: 0.5rem; border-radius: 0.5rem; margin: 0.5rem 0; font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)

# ---------- PARAMÈTRES ----------
TICKER = "DCAM.PA"
NB_PARTS = 481
PRM = 5.5937

# ---------- FONCTIONS DE CALCUL ----------
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def compute_bollinger(series, window=20, num_std=2):
    sma = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return lower.iloc[-1], sma.iloc[-1], upper.iloc[-1]

def compute_vwap(df):
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (typical * df['Volume']).cumsum() / df['Volume'].cumsum()
    return vwap.iloc[-1] if not vwap.empty else None

# ---------- CHARGEMENT DES DONNÉES (robuste) ----------
@st.cache_data(ttl=120, show_spinner="Chargement des données journalières...")
def load_daily_data():
    try:
        ticker = yf.Ticker(TICKER)
        df = ticker.history(period="3mo")
        if df.empty:
            df = yf.download(TICKER, period="3mo", progress=False)
        return df if not df.empty else None
    except Exception as e:
        st.error(f"Erreur lors du téléchargement : {e}")
        return None

@st.cache_data(ttl=60, show_spinner="Chargement des données intraday...")
def load_intraday_data():
    try:
        ticker = yf.Ticker(TICKER)
        df = ticker.history(period="1d", interval="5m")
        if df.empty:
            df = yf.download(TICKER, period="1d", interval="5m", progress=False)
        return df if not df.empty else None
    except Exception:
        return None

# ---------- INITIALISATION ----------
daily = load_daily_data()
if daily is None:
    st.error("⚠️ Impossible de récupérer les données journalières pour DCAM.PA.")
    st.info("💡 Cliquez sur le bouton ci-dessous pour réessayer.")
    if st.button("🔄 Forcer le rechargement des données"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

current_price = daily['Close'].iloc[-1]

# ---------- ANALYSE JOURNALIÈRE ----------
rsi_val = compute_rsi(daily['Close'], 14)
high_20 = daily['High'].rolling(20).max().iloc[-1]
drawdown_pct = (current_price - high_20) / high_20 * 100

score = 5
if rsi_val is not None:
    if rsi_val < 30: score += 4
    elif rsi_val < 45: score += 2
    elif rsi_val > 70: score -= 3
if drawdown_pct < -2: score += 3
elif drawdown_pct < -1.5: score += 2
elif drawdown_pct < -1: score += 1
score = max(0, min(10, score))

if rsi_val and rsi_val < 45 and drawdown_pct < -1.5:
    conseil = "✅ Aujourd'hui est un bon jour statistique pour ton DCA"
elif rsi_val and rsi_val > 70:
    conseil = "⚠️ Risque de repli, envisagez d'attendre 24/48h"
else:
    conseil = "ℹ️ Conditions neutres, vous pouvez investir sans urgence"

# ---------- INTRAJOUR ----------
tz_paris = ZoneInfo("Europe/Paris")
now = datetime.now(tz_paris)
market_open = (now.hour >= 9 and now.hour < 17) or (now.hour == 17 and now.minute <= 30)
vwap = boll_lower = boll_upper = price_limit = None
if market_open:
    intraday = load_intraday_data()
    if intraday is not None and not intraday.empty:
        vwap = compute_vwap(intraday)
        # Choisir une fenêtre adaptée aux données disponibles
        n_points = len(intraday)
        window = 20 if n_points >= 20 else (10 if n_points >= 10 else n_points)
        if window >= 2:
            boll_lower, _, boll_upper = compute_bollinger(intraday['Close'], window, 2)
        price_limit = vwap * 0.9995 if vwap else current_price * 0.999

# ---------- INTERFACE ----------
st.title("🎯 DCAM DCA Optimizer")
st.caption(f"Données du {now.strftime('%d/%m/%Y %H:%M')} (heure de Paris)")

col_refresh, _ = st.columns([1, 4])
with col_refresh:
    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()

st.subheader("📌 Ma position PEA")
c1,c2,c3 = st.columns(3)
c1.metric("Parts", f"{NB_PARTS}")
c2.metric("PRM (poche)", f"{PRM:.4f} €")
c3.metric("Dernier cours", f"{current_price:.4f} €")

gain_pct = (current_price - PRM) / PRM * 100
gain_eur = NB_PARTS * (current_price - PRM)
st.markdown(f"**Gain latent :** {gain_eur:+,.2f} € ({gain_pct:+.2f} %)")

st.markdown("---")

st.subheader("📊 Analyse journalière")
c4,c5,c6 = st.columns(3)
c4.metric("RSI (14)", f"{rsi_val:.1f}" if rsi_val else "N/A")
c5.metric("+ Haut 20j", f"{high_20:.4f} €")
c6.metric("Drawdown", f"{drawdown_pct:+.2f} %")

st.markdown(f"**Score du jour : {score}/10**")
st.progress(score/10)

st.markdown(f"""
<div class="score-box" style="background-color: {'#d4edda' if 'bon jour' in conseil else '#fff3cd' if 'risque' in conseil.lower() else '#e9ecef'};">
    {conseil}
</div>
""", unsafe_allow_html=True)

st.markdown("---")

st.subheader("⚡ Ordre limite intraday")
if market_open:
    if intraday is not None and not intraday.empty:
        st.success("Marché ouvert – données intraday disponibles")
        c7,c8,c9 = st.columns(3)
        c7.metric("VWAP", f"{vwap:.4f} €" if vwap else "N/A")
        if boll_lower is not None and not np.isnan(boll_lower):
            c8.metric("Boll. inf.", f"{boll_lower:.4f} €")
        else:
            c8.metric("Boll. inf.", "N/A")
        if boll_upper is not None and not np.isnan(boll_upper):
            c9.metric("Boll. sup.", f"{boll_upper:.4f} €")
        else:
            c9.metric("Boll. sup.", "N/A")
        if price_limit:
            st.markdown(f"**Prix limite idéal : `{price_limit:.4f} €`** (VWAP -0.05%)")
    else:
        st.warning("Les données intraday ne sont pas encore disponibles (peut prendre quelques minutes après l'ouverture).")
else:
    st.info("Marché fermé (horaire Paris : 9h00 - 17h30).")

st.markdown("""
<div class="warning-box">
⚠️ <strong>Attention :</strong> Yahoo Finance peut avoir 15 min de retard. Vérifiez le prix sur votre courtier avant de passer un ordre.
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.caption("DCA Optimizer · Outil personnel d'aide à la décision")
