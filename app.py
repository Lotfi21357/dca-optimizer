import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="DCA Optimizer", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.big-price {font-size: 2.5rem; font-weight: bold; color: #0d6efd; text-align: center;}
.decision-banner {font-size: 1.4rem; font-weight: bold; text-align: center; padding: 0.5rem; border-radius: 0.5rem; margin: 0.5rem 0;}
.warning-box {background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 0.5rem; margin: 0.5rem 0;}
</style>
""", unsafe_allow_html=True)

# ---------- SIDEBAR ----------
st.sidebar.header("Paramètres")
parts = st.sidebar.number_input("Parts", value=481, step=1)
prm = st.sidebar.number_input("PRM (€)", value=5.261, step=0.001, format="%.4f")
bonus = st.sidebar.number_input("Bonus (€)", value=160.0, step=10.0)
prm_ajuste = ((parts * prm) - bonus) / parts
st.sidebar.metric("PRM ajusté", f"{prm_ajuste:.4f}€")

montant = st.sidebar.number_input("Investir (€)", value=500.0, step=100.0)

# ---------- FONCTION DE TÉLÉCHARGEMENT ULTRA-ROBUSTE ----------
@st.cache_data(ttl=120, show_spinner="Chargement...")
def fetch_data(ticker, period="3mo"):
    """Essaie les méthodes download, Ticker.history, et fallback avec start/end."""
    methods = []
    # Méthode 1 : download
    try:
        df = yf.download(ticker, period=period, progress=False)
        if not df.empty:
            df.columns = [c.lower().strip() for c in df.columns]
            return df
    except Exception as e:
        methods.append(f"download: {e}")

    # Méthode 2 : objet Ticker
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        if not df.empty:
            df.columns = [c.lower().strip() for c in df.columns]
            return df
    except Exception as e:
        methods.append(f"Ticker: {e}")

    # Méthode 3 : avec dates explicites
    try:
        end = datetime.now()
        start = end - timedelta(days=100)
        df = yf.download(ticker, start=start, end=end, progress=False)
        if not df.empty:
            df.columns = [c.lower().strip() for c in df.columns]
            return df
    except Exception as e:
        methods.append(f"dates: {e}")

    # Si tout échoue, on retourne un DataFrame vide
    return pd.DataFrame()

# ---------- CHARGEMENT ----------
daily = fetch_data("DCAM.PA")
if daily.empty:
    st.error("❌ Données DCAM.PA temporairement indisponibles. Yahoo Finance est peut-être momentanément inaccessible.")
    st.info("💡 Cela peut arriver de temps en temps. Vous pouvez réessayer manuellement dans quelques minutes, ou cliquer sur le bouton ci-dessous.")
    if st.button("🔄 Réessayer maintenant"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

# ---------- CALCULS ----------
close = daily['close'].iloc[-1]
high20 = daily['high'].rolling(20).max().iloc[-1]
drawdown = (close / high20 - 1) * 100

# RSI
delta = daily['close'].diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
rs = gain / loss
rsi_val = 100 - (100 / (1 + rs)).iloc[-1]

# Score
score = 5
if rsi_val < 30: score += 4
elif rsi_val < 45: score += 2
elif rsi_val > 70: score -= 3
if drawdown < -2: score += 3
elif drawdown < -1.5: score += 2
score = max(0, min(10, score))

decision = "ACHAT" if score >= 7 else "ATTENDRE" if score >= 4 else "PRUDENCE"
colors = {"ACHAT": "green", "ATTENDRE": "orange", "PRUDENCE": "red"}

# Prix limite simple
price_limit = close * 0.999
nb_parts = int(montant // price_limit) if price_limit > 0 else 0
cout_total = nb_parts * price_limit
nouveau_prm = (parts * prm_ajuste + cout_total) / (parts + nb_parts) if nb_parts > 0 else prm_ajuste

# ---------- AFFICHAGE ----------
st.title("🎯 DCAM DCA Optimizer")
st.markdown(f"<div class='decision-banner' style='background-color:{colors[decision]};color:white;'>{decision}</div>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
col1.metric("Dernier cours", f"{close:.4f}€")
col2.metric("Score du jour", f"{score}/10")
st.progress(score/10)
st.write(f"RSI : {rsi_val:.1f} | Drawdown 20j : {drawdown:.2f}%")

gain_latent = close - prm_ajuste
st.metric("Gain latent", f"{gain_latent:+.4f}€", delta=f"{(gain_latent/prm_ajuste*100):+.2f}%")

st.markdown("---")
st.subheader("🧮 Calculateur de parts")
st.write(f"Prix limite suggéré : **{price_limit:.4f}€**")
colA, colB, colC = st.columns(3)
colA.metric("Parts", f"{nb_parts}")
colB.metric("Coût total", f"{cout_total:.2f}€")
colC.metric("Nouveau PRM", f"{nouveau_prm:.4f}€")

st.markdown("<div class='warning-box'>⚠️ Yahoo Finance : décalage possible de 15 min.</div>", unsafe_allow_html=True)
