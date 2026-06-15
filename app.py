import os
import datetime
import requests
import streamlit as st
import pandas as pd
import numpy as np
import pytz
from dhanhq import DhanContext, dhanhq

# ── Force Indian Standard Time globally across all hosting servers ────────────
IST = pytz.timezone("Asia/Kolkata")

# ── Dynamic Inline Definition of Highly Accurate Custom Rule Implementations ──
def get_trend(current: float, previous: float) -> tuple[str, str]:
    """Calculates trend momentum with a 0.1% volatility filter to prevent noise."""
    if current > previous * 1.001:
        return "Rising", "⬆️"
    elif current < previous * 0.999:
        return "Falling", "⬇️"
    return "Stable", "➡️"

def interpret_rsi(rsi_val: float) -> tuple[str, str]:
    """Advanced RSI Interpretation using institutional 60/40 trend regimes."""
    if rsi_val >= 70:
        return "Overbought (Blow-off Top Risk)", "Bearish Bias / Caution"
    elif rsi_val >= 60:
        return "Bullish Momentum Zone (Buying on Dips)", "Bullish"
    elif rsi_val <= 30:
        return "Oversold (Capitulation / Reversal Near)", "Bullish Bias / Watch Reversal"
    elif rsi_val <= 40:
        return "Bearish Momentum Zone (Selling Rallies)", "Bearish"
    return "Neutral / Confined Range", "Neutral"

def interpret_delta(delta_val: float) -> tuple[str, str]:
    """Handles Call (positive) and Put (negative) deltas to prevent mapping gaps."""
    if delta_val > 0:  # CALL OPTIONS
        if delta_val >= 0.75:
            return "Deep ITM Call (Ultra-Bullish)", "Aggressive Bullish"
        elif delta_val >= 0.55:
            return "ITM Call (Directional Long Build)", "Bullish"
        elif delta_val >= 0.45:
            return "Near ATM Call (Balanced Sensitivity)", "Neutral-Bullish"
        elif delta_val >= 0.20:
            return "OTM Call (High Decay Risk)", "Speculative Bullish"
        else:
            return "Deep OTM Call (Tail-Risk)", "Short Premium Bias"
    else:  # PUT OPTIONS
        abs_d = abs(delta_val)
        if abs_d >= 0.75:
            return "Deep ITM Put (Ultra-Bearish)", "Aggressive Bearish"
        elif abs_d >= 0.55:
            return "ITM Put (Directional Short Build)", "Bearish"
        elif abs_d >= 0.45:
            return "Near ATM Put (Balanced Sensitivity)", "Neutral-Bearish"
        elif abs_d >= 0.20:
            return "OTM Put (High Decay Risk)", "Speculative Bearish"
        else:
            return "Deep OTM Put (Tail-Risk)", "Short Premium Bias"

def interpret_vega(vega_val: float) -> tuple[str, str]:
    """Tracks chain premium metrics relative to volatile index options pricing."""
    if vega_val > 50:
        return "Vol Expansion — IV rising across chain", "Buy Premium / Long Vol"
    elif vega_val < -50:
        return "Vol Contraction — IV crushing", "Sell Premium / Short Vol"
    return "Stable Volatility Environments", "Neutral"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Market Intelligence Console", layout="wide")

# ── Session State for Credentials ──────────────────────────────────────────────
if "dhan_authenticated" not in st.session_state:
    st.session_state["dhan_authenticated"] = False
    st.session_state["client_id"] = ""
    st.session_state["access_token"] = ""

# ── Login Form Control ────────────────────────────────────────────────────────
if not st.session_state["dhan_authenticated"]:
    st.title("🔐 Connect to Dhan API")
    st.markdown("Because Dhan API keys refresh frequently, please input your current credentials below to launch the console.")
    
    with st.form("dhan_login_form"):
        input_client_id = st.text_input("Dhan Client ID", value=st.session_state["client_id"], help="Enter your Dhan Client ID")
        input_token = st.text_input("Access Token", value=st.session_state["access_token"], type="password", help="Enter your Access Token")
        submit_btn = st.form_submit_button("Launch Dashboard")
        
        if submit_btn:
            if input_client_id.strip() == "" or input_token.strip() == "":
                st.error("Both Client ID and Access Token are required.")
            else:
                st.session_state["client_id"] = input_client_id.strip()
                st.session_state["access_token"] = input_token.strip()
                st.session_state["dhan_authenticated"] = True
                st.rerun()
    st.stop()

# ── Active Credentials Setup ──────────────────────────────────────────────────
CLIENT_ID    = st.session_state["client_id"]
ACCESS_TOKEN = st.session_state["access_token"]
BASE_URL     = "https://api.dhan.co/v2"

NIFTY_SCRIP   = 13          
NIFTY_SEG     = "IDX_I"     
NIFTY_SEC_ID  = "13"        
NSE_EQ_SEG    = "NSE_EQ"

# ── Dhan helpers ──────────────────────────────────────────────────────────────
def _headers() -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": ACCESS_TOKEN,
        "client-id": CLIENT_ID,
    }

def _post(path: str, payload: dict):
    r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

# ── Timezone Aware Live data fetchers ──────────────────────────────────────────
@st.cache_data(ttl=60, scope="session")
def fetch_nifty_ltp() -> float:
    resp = _post("/marketfeed/ltp", {"IDX_I": [NIFTY_SCRIP]})
    return float(resp["data"]["IDX_I"][str(NIFTY_SCRIP)]["last_price"])

@st.cache_data(ttl=180, scope="session")
def fetch_expiry_list() -> list:
    resp = _post("/optionchain/expirylist", {
        "UnderlyingScrip": NIFTY_SCRIP,
        "UnderlyingSeg": NIFTY_SEG,
    })
    return resp.get("data", [])

@st.cache_data(ttl=180, scope="session")
def fetch_option_chain(expiry: str) -> pd.DataFrame:
    resp = _post("/optionchain", {
        "UnderlyingScrip": NIFTY_SCRIP,
        "UnderlyingSeg": NIFTY_SEG,
        "Expiry": expiry,
    })

    rows = []
    chain_data = resp.get("data", {})
    oc = chain_data.get("oc", {})

    for strike_str, v in oc.items():
        strike = float(strike_str)
        ce = v.get("ce", {})
        pe = v.get("pe", {})
        rows.append({
            "strike":        strike,
            "call_premium":  ce.get("last_price", 0.0),
            "call_oi":       ce.get("oi", 0),
            "call_volume":   ce.get("volume", 0),
            "call_iv":       ce.get("implied_volatility", 0.0),
            "put_premium":   pe.get("last_price", 0.0),
            "put_oi":        pe.get("oi", 0),
            "put_volume":    pe.get("volume", 0),
            "put_iv":        pe.get("implied_volatility", 0.0),
            "delta":         ce.get("greeks", {}).get("delta", 0.0),
            "gamma":         ce.get("greeks", {}).get("gamma", 0.0),
            "theta":         ce.get("greeks", {}).get("theta", 0.0),
            "vega":          ce.get("greeks", {}).get("vega", 0.0),
            "put_delta":     pe.get("greeks", {}).get("delta", 0.0),
            "put_theta":     pe.get("greeks", {}).get("theta", 0.0),
        })

    df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
    return df

@st.cache_data(ttl=60, scope="session")
def fetch_intraday_history() -> pd.DataFrame:
    """Fetches historical daily chart data utilizing timezone-safe constraints."""
    now_in_india = datetime.datetime.now(IST)
    today_str = now_in_india.strftime("%Y-%m-%d")
    past_str = (now_in_india - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    
    try:
        resp = _post("/charts/historical", {
            "securityId": NIFTY_SEC_ID,
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "expiryCode": 0,
            "oi": False,
            "fromDate": past_str,
            "toDate": today_str,
        })
        data = resp.get("data", {})
        closes = data.get("c", [])
        if closes:
            return pd.DataFrame({"close": closes})
    except Exception:
        pass
    return pd.DataFrame()

# ── Mathematical Helper Operations ──────────────────────────────────────────
def calc_rsi(series: pd.Series, period: int = 14) -> float:
    if len(series) < period + 1:
        return 50.0
    delta = series.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)

def calc_ema(series: pd.Series, span: int) -> float:
    if len(series) < span:
        return float(series.iloc[-1])
    return round(float(series.ewm(span=span, adjust=False).mean().iloc[-1]), 2)

def calc_roc(series: pd.Series, period: int = 10) -> float:
    if len(series) < period + 1:
        return 0.0
    roc = ((series.iloc[-1] - series.iloc[-1 - period]) / series.iloc[-1 - period]) * 100
    return round(float(roc), 2)

def find_atm(spot: float, strikes: pd.Series) -> float:
    return float(strikes.iloc[(strikes - spot).abs().argsort().iloc[0]])

def day_change_pct(hist_df: pd.DataFrame, current_spot: float) -> str:
    """Calculates day change percentage against the previous session's confirmed close."""
    if hist_df.empty or len(hist_df) < 1:
        return "N/A"
    previous_close = float(hist_df["close"].iloc[-2]) if len(hist_df) >= 2 else float(hist_df["close"].iloc[-1])
    if previous_close == 0:
        return "N/A"
    pct = ((current_spot - previous_close) / previous_close) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"

def auto_regime(spot: float, ema20: float, ema50: float, rsi: float, agg_vega: float, call_oi: float, put_oi: float) -> tuple[str, str]:
    bullish = spot > ema20 > ema50
    bearish = spot < ema20 < ema50
    structure = "Bullish Trend" if bullish else ("Bearish Trend" if bearish else "Sideways / Choppy")
    vol_regime = "Expanding" if agg_vega > 0 else "Contracting"
    pcr = put_oi / call_oi if call_oi > 0 else 1.0
    positioning = "Put Heavy (Bearish hedge)" if pcr > 1.2 else ("Call Heavy (Bullish bets)" if pcr < 0.8 else "Balanced")

    if bullish and rsi < 70:
        playbook = "Buy on Dips / Long Call Spreads. Avoid naked short puts due to rising Vega."
    elif bullish and rsi >= 70:
        playbook = "Overbought — consider Bull Put Spreads or partial profit booking on calls."
    elif bearish and rsi > 30:
        playbook = "Sell rallies / Long Put Spreads. Avoid naked short calls."
    elif bearish and rsi <= 30:
        playbook = "Oversold — consider Bear Call Spreads or watch for reversal signals."
    else:
        playbook = "Range-bound — Iron Condors or short straddles near ATM if IV is elevated."

    info_line  = f"**Market Structure:** {structure} | **Volatility:** {vol_regime} | **Positioning:** {positioning}"
    return info_line, playbook

# ── Main Dashboard Execution ──────────────────────────────────────────────────
st.title("Market Intelligence Dashboard")
st.markdown("*A tabular decision-support console for NIFTY options — powered by live Dhan data.*")

st.sidebar.header("Live Controls")
if st.sidebar.button("🚪 Disconnect API Keys"):
    st.session_state["dhan_authenticated"] = False
    st.session_state["client_id"] = ""
    st.session_state["access_token"] = ""
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

try:
    expiries = fetch_expiry_list()
    if not expiries:
        st.error("Could not fetch expiry list from Dhan. Verify your credentials in the console.")
        st.stop()
except Exception as e:
    st.error(f"Authentication failed or invalid token: {e}")
    if st.button("Re-enter Credentials"):
        st.session_state["dhan_authenticated"] = False
        st.rerun()
    st.stop()

selected_expiry = st.sidebar.selectbox("Select Expiry", expiries)
strike_range    = st.sidebar.slider("Strikes around ATM (±N)", min_value=5, max_value=20, value=10)

try:
    nifty_spot = fetch_nifty_ltp()
    chain_df = fetch_option_chain(selected_expiry)
except Exception as e:
    st.error(f"Failed to fetch market data streams: {e}")
    st.stop()

hist_df = fetch_intraday_history()

# ── Compute Metric Values ─────────────────────────────────────────────────────
atm_strike  = find_atm(nifty_spot, chain_df["strike"])
day_chg     = day_change_pct(hist_df, nifty_spot)
closes      = hist_df["close"] if not hist_df.empty else pd.Series([nifty_spot])
rsi_val     = calc_rsi(closes)
ema20       = calc_ema(closes, 20)
ema50       = calc_ema(closes, 50)
roc_val     = calc_roc(closes)
now_str     = datetime.datetime.now(IST).strftime("%H:%M:%S")

all_strikes  = sorted(chain_df["strike"].unique())
atm_idx      = all_strikes.index(atm_strike)
low_idx      = max(0, atm_idx - strike_range)
high_idx     = min(len(all_strikes) - 1, atm_idx + strike_range)
nearby_strikes = all_strikes[low_idx:high_idx + 1]
filtered_df  = chain_df[chain_df["strike"].isin(nearby_strikes)]

atm_row = chain_df[chain_df["strike"] == atm_strike]
if atm_row.empty:
    st.error("ATM strike not found in option chain.")
    st.stop()
atm = atm_row.iloc[0]

# ── Section 1: Market Context ─────────────────────────────────────────────────
st.header("1. Market Context")
col1, col2, col3, col4 = st.columns(4)
col1.metric("NIFTY Spot",  f"{nifty_spot:.2f}")
col2.metric("ATM Strike",  f"{atm_strike:.0f}")
col3.metric("Time",        now_str)
col4.metric("Day Change",  day_chg)
st.divider()

# ── Section 2: Underlying NIFTY State ────────────────────────────────────────
st.header("2. Underlying (NIFTY State)")
rsi_interp, rsi_bias = interpret_rsi(rsi_val)

vs_ema20 = "Above" if nifty_spot > ema20 else "Below"
vs_ema50 = "Above" if nifty_spot > ema50 else "Below"
ema20_bias = "Bullish" if nifty_spot > ema20 else "Bearish"
ema50_bias = "Bullish" if nifty_spot > ema50 else "Bearish"
roc_bias   = "Bullish" if roc_val > 0 else "Bearish"
_, roc_trend = get_trend(nifty_spot, ema20)

nifty_state_data = {
    "Parameter":     ["RSI (14)", "Price vs 20 EMA", "Price vs 50 EMA", "Momentum (ROC 10)"],
    "Value":         [f"{rsi_val}", vs_ema20, vs_ema50, f"{roc_val:+.2f}%"],
    "Trend":         ["⬆️" if rsi_val > 50 else "⬇️", "⬆️" if nifty_spot > ema20 else "⬇️", "⬆️" if nifty_spot > ema50 else "⬇️", roc_trend],
    "Interpretation": [rsi_interp, f"Price {'above' if nifty_spot > ema20 else 'below'} 20 EMA ({ema20:.2f})", f"Price {'above' if nifty_spot > ema50 else 'below'} 50 EMA ({ema50:.2f})", "Accelerating" if roc_val > 0 else "Decelerating"],
    "Action Bias":   [rsi_bias, ema20_bias, ema50_bias, roc_bias],
}
st.dataframe(pd.DataFrame(nifty_state_data), width="stretch", hide_index=True)
st.divider()

# ── Section 3: ATM Analysis ───────────────────────────────────────────────────
st.header("3. ATM Analysis")
col1, col2 = st.columns(2)

with col1:
    st.subheader(f"ATM Call  ({atm_strike:.0f} CE)")
    call_delta_interp, call_delta_bias = interpret_delta(float(atm["delta"]))
    call_table = {
        "Parameter":     ["Premium", "Delta", "Theta", "IV"],
        "Value":         [f"{atm['call_premium']:.2f}", f"{atm['delta']:.4f}", f"{atm['theta']:.4f}", f"{atm['call_iv']:.2f}%"],
        "Trend":         ["⬆️", "⬆️", "⬇️", "➡️"],
        "Interpretation": ["Market price of call",  call_delta_interp, "Time decay per day", "Implied volatility"],
        "Action Bias":   [call_delta_bias, call_delta_bias, "Neutral", "Monitor"],
    }
    st.dataframe(pd.DataFrame(call_table), width="stretch", hide_index=True)

with col2:
    st.subheader(f"ATM Put  ({atm_strike:.0f} PE)")
    put_delta_interp, put_delta_bias = interpret_delta(float(atm["put_delta"]))
    put_table = {
        "Parameter":     ["Premium", "Delta", "Theta", "IV"],
        "Value":         [f"{atm['put_premium']:.2f}", f"{atm['put_delta']:.4f}", f"{atm['put_theta']:.4f}", f"{atm['put_iv']:.2f}%"],
        "Trend":         ["⬇️", "⬇️", "⬇️", "➡️"],
        "Interpretation": ["Market price of put",  put_delta_interp, "Time decay per day", "Implied volatility"],
        "Action Bias":   [put_delta_bias, put_delta_bias, "Neutral", "Monitor"],
    }
    st.dataframe(pd.DataFrame(put_table), width="stretch", hide_index=True)
st.divider()

# ── Section 4: Cumulative Greeks ──────────────────────────────────────────────
st.header("4. Cumulative Greeks")
agg_delta = filtered_df["delta"].sum()
agg_gamma = filtered_df["gamma"].sum()
agg_vega  = filtered_df["vega"].sum()
agg_theta = filtered_df["theta"].sum()
vega_interp, vega_bias = interpret_vega(float(agg_vega))

greeks_table = {
    "Greek":            ["Delta", "Gamma", "Vega", "Theta"],
    "Aggregated Value": [f"{agg_delta:.4f}", f"{agg_gamma:.6f}", f"{agg_vega:.4f}", f"{agg_theta:.4f}"],
    "Interpretation":   ["Net Long build" if agg_delta > 0 else "Net Short build", "High pinning risk" if agg_gamma > 0.05 else "Low pinning risk", vega_interp, "Chain decaying fast" if agg_theta < -50 else "Moderate decay"],
    "Bias":             ["Bullish" if agg_delta > 0 else "Bearish", "Caution" if agg_gamma > 0.05 else "Neutral", vega_bias, "Neutral"],
}
st.dataframe(pd.DataFrame(greeks_table), width="stretch", hide_index=True)

total_call_oi = filtered_df["call_oi"].sum()
total_put_oi  = filtered_df["put_oi"].sum()
pcr           = total_put_oi / total_call_oi if total_call_oi > 0 else 0
c1, c2, c3 = st.columns(3)
c1.metric("Total Call OI", f"{total_call_oi:,.0f}")
c2.metric("Total Put OI",  f"{total_put_oi:,.0f}")
c3.metric("PCR (Put/Call OI)", f"{pcr:.2f}")
st.divider()

# ── Section 5: Full Option Chain Table ───────────────────────────────────────
st.header("5. Option Chain (Filtered Strikes)")
display_chain = filtered_df[[
    "strike", "call_premium", "call_oi", "call_iv", "delta", "gamma", "vega", "theta", "put_premium", "put_oi", "put_iv"
]].copy()
display_chain.columns = ["Strike", "Call LTP", "Call OI", "Call IV%", "Delta", "Gamma", "Vega", "Theta", "Put LTP", "Put OI", "Put IV%"]

st.dataframe(display_chain.style.format(precision=2), width="stretch", hide_index=True)
st.divider()