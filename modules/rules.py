# modules/rules.py

def get_trend(current: float, previous: float) -> tuple[str, str]:
    """
    Calculates trend momentum with a 0.1% volatility filter to prevent noise.
    Matches your exact dashboard rendering icons.
    """
    if current > previous * 1.001:
        return "Rising", "⬆️"
    elif current < previous * 0.999:
        return "Falling", "⬇️"
    return "Stable", "➡️"


def interpret_rsi(rsi_val: float) -> tuple[str, str]:
    """
    Takes raw RSI float. Returns (interpretation, bias).
    """
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
    """
    Takes raw delta float (call delta: 0 to 1, put delta: -1 to 0).
    Returns (interpretation, bias).
    """
    # CALL OPTIONS (Positive Delta)
    if delta_val > 0:
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

    # PUT OPTIONS (Negative Delta)
    else:
        if delta_val <= -0.75:
            return "Deep ITM Put (Ultra-Bearish)", "Aggressive Bearish"
        elif delta_val <= -0.55:
            return "ITM Put (Directional Short Build)", "Bearish"
        elif delta_val <= -0.45:
            return "Near ATM Put (Balanced Sensitivity)", "Neutral-Bearish"
        elif delta_val <= -0.20:
            return "OTM Put (High Decay Risk)", "Speculative Bearish"
        else:
            return "Deep OTM Put (Tail-Risk)", "Short Premium Bias"


def interpret_vega(vega_val: float) -> tuple[str, str]:
    """
    Takes raw aggregated vega float. 
    Returns (interpretation, bias).
    """
    if vega_val > 50:
        return "Vol Expansion — IV rising across chain", "Buy Premium / Long Vol"
    elif vega_val < -50:
        return "Vol Contraction — IV crushing", "Sell Premium / Short Vol"
    return "Stable Volatility Environments", "Neutral"