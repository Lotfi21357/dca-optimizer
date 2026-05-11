import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings("ignore")

# ---------- AUTO-REFRESH FIABLE (120 secondes) ----------
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

elapsed = time.time() - st.session_state.last_refresh
if elapsed >= 120:
    st.session_state.last_refresh = time.time()
    st.rerun()

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

# ---------- FONCTIONS ----------
@st.cache_data(ttl=120, show_spinner=False)
def load_daily_data():
    start = datetime.now() - timedelta(days=120)
    df = yf.download(TICKER, start=start, progress=False)
    return df if not df.empty else None

@st.cache_data(ttl=60, show_spinner=False)
def load_intraday_data():
    df = yf.download(TICKER, period="1d", interval="5m", progress=False)
    return df if not df.empty else None

def compute_vwap(df):
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (typical * df['Volume']).cumsum() / df['Volume'].cumsum()
    return vwap.iloc[-1] if not vwap.empty else None

def compute_bollinger(df, length=20, std=2):
    bbands = ta.bbands(df['Close'], length=length, std=std)
    if bbands is not None and not bbands.empty:
        last = bbands.iloc[-1]
        return last[f'BBL_{length}_{std}'], last[f'BBM_{length}_{std}'], last[f'BBU_{length}_{std}']
    return None, None, None

def compute_rsi(df, length=14):
    rsi = ta.rsi(df['Close'], length=length)
    return rsi.iloc[-1] if rsi is not None and not rsi.empty else None

# ---------- CHARGEMENT ----------
daily = load_daily_data()
if daily is None:
    st.error("Données journalières indisponibles. Vérifiez votre connexion.")
    st.stop()

current_price = daily['Close'].iloc[-1]

# ---------- ANALYSE JOURNALIÈRE ----------
rsi_val = compute_rsi(daily, 14)
high_20 = daily['High'].rolling(20).max().iloc[-1]
drawdown_pct = (current_price - high_20) / high_20 * 100

score = 5
if rsi_val is not None:
    if rsi_val < 30:
        score += 4
    elif rsi_val < 45:
        score += 2
    elif rsi_val > 70:
        score -= 3
if drawdown_pct < -2:
    score += 3
elif drawdown_pct < -1.5:
    score += 2
    score += 2
elif drawdown_pct < -1:
    score += 1
score = max(0, min(10, score))

if rsi_val is not None and rsi_val < 45 and drawdown_pct < -1.5:
    conseil = "✅ Aujourd'hui est un bon jour statistique pour ton DCA"
elif rsi_val is not None and rsi_val > 70:
    conseil = "⚠️ Risque de repli, envisagez d'attendre 24/48h"
else:
    conseil = "ℹ️ Conditions neutres, vous pouvez investir sans urgence"

# ---------- EXÉCUTION INTRAJOUR ----------
now = datetime.now()
market_open = (now.hour >= 9 and now.hour < 17) or (now.hour == 17 and now.minute <= 30)
vwap = None
boll_lower = boll_upper = None
price_limit = None
if market_open:
    intraday = load_intraday_data()
    if intraday is not None and not intraday.empty:
        vwap = compute_vwap(intraday)
        boll_lower, _, boll_upper = compute_bollinger(intraday)
        price_limit = vwap * 0.9995 if vwap else current_price * 0.999

# ---------- INTERFACE ----------
st.title("🎯 DCAM DCA Optimizer")
st.caption(f"Données du {now.strftime('%d/%m/%Y %H:%M')} · Rafraîchi auto / 2 min")

st.subheader("📌 Ma position PEA")
col1,col2,col3 = st.columns(3)
col1.metric("Parts", f"{NB_PARTS}")
col2.metric("PRM (poche)", f"{PRM:.4f} €")
col3.metric("Dernier cours", f"{current_price:.4f} €")

gain_pct = (current_price - PRM) / PRM * 100
gain_eur = NB_PARTS * (current_price - PRM)
st.markdown(f"**Gain latent :** {gain_eur:+,.2f} € ({gain_pct:+.2f} %)")

st.markdown("---")

st.subheader("📊 Analyse journalière")
c4,c5,c6 = st.columns(3)
c4.metric("RSI (14)", f"{rsi_val:.1f}" if rsi_val is not None else "N/A")
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
        col7,col8,col9 = st.columns(3)
        col7.metric("VWAP", f"{vwap:.4f} €" if vwap else "N/A")
        if boll_lower and boll_upper:
            col8.metric("Boll. inf.", f"{boll_lower:.4f} €")
            col9.metric("Boll. sup.", f"{boll_upper:.4f} €")
        if price_limit:
            st.markdown(f"**Prix limite idéal : `{price_limit:.4f} €`** (VWAP -0.05%)")
    else:
        st.warning("Données intraday pas encore disponibles. Réessayez dans quelques minutes.")
else:
    st.info("Marché fermé (heures d'ouverture : 9h00 - 17h30, Paris).")

st.markdown("""
<div class="warning-box">
⚠️ <strong>Attention :</strong> Les données Yahoo Finance peuvent avoir un décalage de 15 minutes. Vérifiez toujours le prix sur votre courtier avant de passer un ordre.
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.caption("DCA Optimizer · Outil personnel d’aide à la décision")
