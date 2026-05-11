import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ---------- CONFIGURATION ----------
st.set_page_config(page_title="DCA Optimizer", page_icon="🎯", layout="wide")

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

# ---------- SIDEBAR ----------
st.sidebar.header("⚙️ Paramètres")
parts = st.sidebar.number_input("Parts actuelles", value=481, step=1)
prm_actuel = st.sidebar.number_input("PRM actuel (€)", value=5.261, step=0.001, format="%.4f")
bonus = st.sidebar.number_input("Bonus injecté (€)", value=160.0, step=10.0)
prm_ajuste = ((parts * prm_actuel) - bonus) / parts
st.sidebar.metric("PRM ajusté", f"{prm_ajuste:.4f} €", delta=f"Bonus -{bonus:.0f}€")

montant = st.sidebar.number_input("Montant à investir (€)", value=500.0, step=100.0)
if st.sidebar.button("🔄 Rafraîchir les données"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Données actualisées en cache pendant 2 min.")

# ---------- FONCTIONS DE TÉLÉCHARGEMENT ROBUSTE ----------
@st.cache_data(ttl=120, show_spinner="Chargement...")
def fetch_data(ticker, period="3mo", interval="1d"):
    """Essaie plusieurs méthodes pour obtenir les données."""
    # Méthode 1 : download standard
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if not df.empty:
            return df
    except:
        pass
    # Méthode 2 : utiliser l'objet Ticker
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if not df.empty:
            return df
    except:
        pass
    # Méthode 3 : période exacte avec dates
    try:
        end = datetime.now()
        start = end - timedelta(days=100)
        df = yf.download(ticker, start=start, end=end, interval=interval, progress=False)
        if not df.empty:
            return df
    except:
        pass
    return pd.DataFrame()

# ---------- CHARGEMENT ----------
daily = fetch_data("DCAM.PA", "3mo")
if daily.empty:
    st.error("❌ Données DCAM.PA temporairement indisponibles (Yahoo Finance).")
    st.info("💡 Appuyez sur **🔄 Rafraîchir les données** dans la barre latérale pour réessayer.")
    st.stop()

daily.ffill(inplace=True)
current = daily['Close'].iloc[-1]
open_p = daily['Open'].iloc[-1] if 'Open' in daily.columns else None
prev_c = daily['Close'].iloc[-2] if len(daily) > 1 else None

# Intraday (5 min) si marché ouvert
now = datetime.now()
market_open = 9 <= now.hour < 17 or (now.hour == 17 and now.minute <= 30)
intraday = pd.DataFrame()
if market_open:
    intraday = fetch_data("DCAM.PA", "1d", "5m")
    if not intraday.empty:
        intraday.ffill(inplace=True)

# ---------- INDICATEURS MANUELS ----------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def vwap(df):
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    return (typical * df['Volume']).cumsum() / df['Volume'].cumsum()

def bb(series, window=20, std=2):
    sma = series.rolling(window).mean()
    stdv = series.rolling(window).std()
    return sma.iloc[-1] - stdv.iloc[-1]*std, sma.iloc[-1], sma.iloc[-1] + stdv.iloc[-1]*std

rsi_val = rsi(daily['Close'], 14).iloc[-1] if len(daily) > 14 else None
high20 = daily['High'].rolling(20).max().iloc[-1]
drawdown = (current - high20) / high20 * 100
atr_val = atr(daily, 14).iloc[-1] if len(daily) > 14 else None
vol_pct = (atr_val / current * 100) if atr_val else 0

score = 5
if rsi_val:
    if rsi_val < 30: score += 4
    elif rsi_val < 45: score += 2
    elif rsi_val > 70: score -= 3
if drawdown < -2: score += 3
elif drawdown < -1.5: score += 2
elif drawdown < -1: score += 1
if vol_pct > 2.0: score -= 2
score = max(0, min(10, score))

# Sentinelles US
es = fetch_data("ES=F", "1d", "5m")
nq = fetch_data("NQ=F", "1d", "5m")
es_var = nq_var = 0.0
if not es.empty and not nq.empty:
    es_var = (es['Close'].iloc[-1] / es['Close'].iloc[-2] - 1) * 100 if len(es)>1 else 0
    nq_var = (nq['Close'].iloc[-1] / nq['Close'].iloc[-2] - 1) * 100 if len(nq)>1 else 0

us_alert = (14 <= now.hour < 16 or (now.hour==16 and now.minute==0)) and (es_var < -0.8 or nq_var < -0.8)

# Gap
gap_alert = False
if open_p and prev_c:
    gap_alert = abs(open_p / prev_c - 1) * 100 > 0.5

# VWAP et prix limite
vwap_val = None
boll_low = boll_up = None
if not intraday.empty:
    vwap_val = vwap(intraday).iloc[-1]
    if len(intraday) >= 20:
        boll_low, _, boll_up = bb(intraday['Close'], 20, 2)

price_lim = vwap_val * 0.9995 if vwap_val else current * 0.999

# Calculateur
if montant > 0 and price_lim > 0:
    nb_parts_frac = montant / price_lim
    nb_parts = int(nb_parts_frac)
    cout = nb_parts * price_lim
    new_prm = (parts * prm_ajuste + cout) / (parts + nb_parts) if nb_parts else prm_ajuste
else:
    nb_parts = cout = 0
    new_prm = prm_ajuste

# Décision
if us_alert:
    decision, color = "PRUDENCE MACRO", "red"
elif score >= 7:
    decision, color = "ACHAT FAVORABLE", "green"
elif score >= 4:
    decision, color = "ATTENDRE", "orange"
else:
    decision, color = "PRUDENCE MACRO", "red"

# ---------- INTERFACE ----------
st.title("🎯 DCAM DCA Optimizer")
st.caption(f"Analyse du {now.strftime('%d/%m/%Y à %H:%M')}")

st.markdown(f"<div class='decision-banner' style='background-color:{color};color:white;'>{decision}</div>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    st.metric("Dernier cours", f"{current:.4f}€")
    st.metric("Ouverture", f"{open_p:.4f}€" if open_p else "N/A")
    st.metric("Clôture veille", f"{prev_c:.4f}€" if prev_c else "N/A")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    st.metric("Score du jour", f"{score}/10")
    st.progress(score/10)
    st.write(f"RSI(14) : {rsi_val:.1f}" if rsi_val else "RSI N/A")
    st.write(f"Drawdown 20j : {drawdown:.2f}%")
    st.write(f"Volatilité (ATR) : {vol_pct:.2f}%")
    st.markdown("</div>", unsafe_allow_html=True)

with col3:
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    gain_lat = current - prm_ajuste
    gain_pct_lat = (gain_lat / prm_ajuste * 100)
    st.metric("PRM ajusté", f"{prm_ajuste:.4f}€")
    st.metric("Gain latent", f"{gain_lat:+.4f}€", delta=f"{gain_pct_lat:+.2f}%")
    st.markdown("</div>", unsafe_allow_html=True)

if us_alert:
    st.warning("⚠️ Volatilité US détectée (Futures < -0.8% entre 14h30-16h00). Attendez 15h45.")
if gap_alert:
    st.warning("⚠️ Gap d'ouverture > 0.5%. Attendez 10h30.")

if market_open and not intraday.empty:
    st.subheader("⚡ Exécution Intraday")
    c4,c5,c6 = st.columns(3)
    c4.metric("VWAP", f"{vwap_val:.4f}€")
    if boll_low: c4.metric("Boll. inf.", f"{boll_low:.4f}€")
    if boll_up: c6.metric("Boll. sup.", f"{boll_up:.4f}€")
    c5.markdown(f"<div class='big-price'>{price_lim:.4f}€</div>", unsafe_allow_html=True)
    c5.caption("Prix limite idéal (VWAP -0.05%)")
elif market_open:
    st.info("Données intraday en attente... Réessayez dans quelques minutes.")
else:
    st.info("Marché fermé (9h-17h30 Paris).")

st.subheader("🧮 Calculateur de parts")
ca,cb,cc = st.columns(3)
ca.metric("Parts", f"{nb_parts}")
cb.metric("Coût total", f"{cout:.2f}€")
cc.metric("Nouveau PRM", f"{new_prm:.4f}€")

st.markdown("<div class='warning-box'>⚠️ Yahoo Finance peut avoir 15 min de retard. Vérifiez le cours sur votre courtier.</div>", unsafe_allow_html=True)
st.caption("DCA Optimizer · Outil personnel d'aide à la décision")
