"""
Pure technical-analysis functions.
All functions are stateless and depend only on pandas / numpy.
Run this file directly to smoke-test: python -m app.indicators
"""
import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    val   = 100 - (100 / (1 + rs))
    last  = val.iloc[-1]
    return float(last) if not pd.isna(last) else 50.0


def macd(series: pd.Series) -> tuple[float, float]:
    """Returns (macd_line, signal_line)."""
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    line   = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    return float(line.iloc[-1]), float(signal.iloc[-1])


def moving_averages(series: pd.Series) -> tuple[float, float]:
    """Returns (MA20, MA50)."""
    return (
        float(series.rolling(20).mean().iloc[-1]),
        float(series.rolling(50).mean().iloc[-1]),
    )


def atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range expressed as % of last close price."""
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr   = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr  = tr.rolling(period).mean().iloc[-1]
    last = close.iloc[-1]
    return float(atr / last * 100) if last else 0.0


def support_resistance(df: pd.DataFrame, lookback: int = 30) -> tuple[float, float]:
    """Simple recent support (min low) and resistance (max high)."""
    recent = df.tail(lookback)
    return float(recent["low"].min()), float(recent["high"].max())


def trend_direction(series: pd.Series) -> str:
    """Compare last close to 50-period MA."""
    ma   = series.rolling(50).mean().iloc[-1]
    last = series.iloc[-1]
    if pd.isna(ma):
        return "neutral"
    return "up" if last > ma else "down"


def adx(df: pd.DataFrame, period: int = 14) -> float:
    """Average Directional Index (Wilder smoothing)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    dm_plus  = (high - prev_high).clip(lower=0)
    dm_minus = (prev_low - low).clip(lower=0)
    mask = dm_plus >= dm_minus
    dm_plus[~mask]  = 0.0
    dm_minus[mask]  = 0.0

    alpha   = 1.0 / period
    atr_s   = tr.ewm(alpha=alpha, adjust=False).mean()
    dip_s   = dm_plus.ewm(alpha=alpha, adjust=False).mean()
    dim_s   = dm_minus.ewm(alpha=alpha, adjust=False).mean()

    denom = (dip_s + dim_s).replace(0, np.nan)
    dx    = ((dip_s - dim_s).abs() / denom) * 100
    adx_s = dx.ewm(alpha=alpha, adjust=False).mean()

    last = adx_s.iloc[-1]
    return float(last) if not pd.isna(last) else 20.0


def bb_width(close: pd.Series, period: int = 20) -> tuple[float, float]:
    """Returns (current_bb_width_pct, previous_bb_width_pct)."""
    sma   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    width = (sma + 2 * std - (sma - 2 * std)) / sma * 100

    cur  = float(width.iloc[-1])  if not pd.isna(width.iloc[-1])  else 1.0
    prev = float(width.iloc[-2])  if len(width) > 1 and not pd.isna(width.iloc[-2]) else cur
    return cur, prev


def volatility_regime(df: pd.DataFrame) -> dict:
    """
    Determine market regime from ADX(14) and Bollinger Band width.
    Returns regime label: 'trending', 'ranging', or 'transitioning'.
    """
    adx_val        = adx(df)
    bb_cur, bb_prev = bb_width(df["close"])
    expanding       = bb_cur > bb_prev * 1.005    # 0.5% tolerance

    if adx_val > 25 and expanding:
        regime = "trending"
        label  = f"Trending (ADX {adx_val:.1f}, BB expanding)"
    elif adx_val < 20 and not expanding:
        regime = "ranging"
        label  = f"Ranging (ADX {adx_val:.1f}, BB contracting)"
    else:
        regime = "transitioning"
        label  = f"Transitioning (ADX {adx_val:.1f})"

    return {
        "regime":       regime,
        "adx":          round(adx_val, 1),
        "bb_width":     round(bb_cur, 3),
        "bb_expanding": bool(expanding),
        "label":        label,
    }


def analyze_timeframe(df: pd.DataFrame) -> dict:
    """
    Run all indicators on one OHLCV dataframe (hourly or daily).
    Returns a flat dict ready for JSON serialisation.
    """
    close = df["close"]

    _rsi              = rsi(close)
    macd_line, macd_s = macd(close)
    ma_fast, ma_slow  = moving_averages(close)
    sup, res          = support_resistance(df)
    vol               = atr_pct(df)
    trend             = trend_direction(close)

    # Each signal votes: +1 bullish, -1 bearish
    votes = [
        1 if _rsi < 30 else -1 if _rsi > 70 else (1 if _rsi > 50 else -1),
        1 if macd_line > macd_s else -1,
        1 if ma_fast   > ma_slow else -1,
        1 if trend == "up"       else -1,
    ]
    net = float(np.mean(votes))   # -1 .. +1

    return {
        "direction":          "up" if net > 0 else "down" if net < 0 else "neutral",
        "strength":           round(abs(net), 3),   # 0 .. 1
        "rsi":                round(_rsi, 1),
        "macd_above_signal":  bool(macd_line > macd_s),
        "ma20_above_ma50":    bool(ma_fast > ma_slow),
        "trend":              trend,
        "support":            round(sup, 5),
        "resistance":         round(res, 5),
        "volatility_atr_pct": round(vol, 3),
        "last_price":         round(float(close.iloc[-1]), 5),
    }


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pandas as pd, numpy as np
    np.random.seed(42)
    prices = pd.Series(1.08 + np.cumsum(np.random.randn(200) * 0.001))
    df = pd.DataFrame({"close": prices, "high": prices + 0.002, "low": prices - 0.002})
    print("RSI :", rsi(prices))
    print("MACD:", macd(prices))
    print("Full:", analyze_timeframe(df))
