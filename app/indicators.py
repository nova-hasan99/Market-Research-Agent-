"""
Pure technical-analysis functions.
All functions are stateless and depend only on pandas / numpy.
Run this file directly to smoke-test: python -m app.indicators
"""
import numpy as np
import pandas as pd


# ── Core indicators ───────────────────────────────────────────────────────────

def _rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    """Full RSI series (needed for divergence and slope)."""
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rsi(series: pd.Series, period: int = 14) -> float:
    val = _rsi_series(series, period)
    last = val.iloc[-1]
    return float(last) if not pd.isna(last) else 50.0


def rsi_slope(series: pd.Series, period: int = 14, bars: int = 5) -> float:
    """
    Slope of RSI over recent `bars` candles (linear regression).
    Positive = RSI rising (bullish momentum building).
    Negative = RSI falling (bearish momentum building).
    This is critical for distinguishing between a trend CONTINUING
    vs a trend that is EXHAUSTING (e.g. falling price + rising RSI = bullish divergence).
    """
    rsi_s = _rsi_series(series, period).dropna()
    if len(rsi_s) < bars + 1:
        return 0.0
    recent = rsi_s.tail(bars + 1).values
    x      = np.arange(len(recent))
    slope  = float(np.polyfit(x, recent, 1)[0])
    return round(slope, 4)


def macd(series: pd.Series) -> tuple[float, float]:
    """Returns (macd_line, signal_line)."""
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    line   = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    return float(line.iloc[-1]), float(signal.iloc[-1])


def macd_histogram(series: pd.Series) -> tuple[float, float]:
    """
    Returns (current_histogram, prev_histogram).
    Histogram = macd_line - signal.
    Rising histogram = momentum BUILDING in that direction.
    Falling histogram = momentum FADING (potential reversal warning).
    """
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    line   = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    hist   = line - signal
    cur    = float(hist.iloc[-1])  if not pd.isna(hist.iloc[-1])  else 0.0
    prev   = float(hist.iloc[-2])  if len(hist) > 1 and not pd.isna(hist.iloc[-2]) else cur
    return cur, prev


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


def atr_absolute(df: pd.DataFrame, period: int = 14) -> float:
    """ATR in price units (needed for TP/SL calculation)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr   = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr  = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else 0.0


def swing_support_resistance(df: pd.DataFrame, lookback: int = 50) -> tuple[float, float]:
    """
    Find support/resistance using swing pivot highs/lows instead of raw min/max.
    A swing high is a bar where high[i] > high[i-2..i-1] AND high[i] > high[i+1..i+2].
    This avoids using a single spike as S/R and finds structural price levels.
    Returns (nearest_support_below_price, nearest_resistance_above_price).
    Falls back to raw min/max if not enough pivots are found.
    """
    recent   = df.tail(max(lookback, 20))
    highs    = recent["high"].values
    lows     = recent["low"].values
    closes   = recent["close"].values
    n        = len(highs)
    cur      = float(closes[-1])

    swing_highs: list[float] = []
    swing_lows:  list[float] = []
    win = 2  # bars each side to confirm pivot

    for i in range(win, n - win):
        if (highs[i] >= max(highs[i-win:i]) and highs[i] >= max(highs[i+1:i+win+1])):
            swing_highs.append(highs[i])
        if (lows[i]  <= min(lows[i-win:i])  and lows[i]  <= min(lows[i+1:i+win+1])):
            swing_lows.append(lows[i])

    # Nearest resistance above current price
    above = sorted(h for h in swing_highs if h > cur * 1.0001)
    res   = above[0] if above else float(recent["high"].max())

    # Nearest support below current price
    below = sorted((l for l in swing_lows if l < cur * 0.9999), reverse=True)
    sup   = below[0] if below else float(recent["low"].min())

    return round(sup, 5), round(res, 5)


def trend_direction(series: pd.Series) -> str:
    """Compare last close to 50-period MA."""
    ma   = series.rolling(50).mean().iloc[-1]
    last = series.iloc[-1]
    if pd.isna(ma):
        return "neutral"
    return "up" if last > ma else "down"


def momentum_divergence(df: pd.DataFrame, rsi_period: int = 14,
                        lookback: int = 30) -> str:
    """
    Detect price/RSI divergence -- the most important mean-reversion signal.

    Bullish divergence: price makes a lower low, but RSI makes a higher low.
      Signals that selling MOMENTUM is exhausting even though price is still falling.
      Next move is MORE LIKELY to be upward. Do NOT extrapolate the downtrend.

    Bearish divergence: price makes a higher high, but RSI makes a lower high.
      Signals that buying MOMENTUM is exhausting even though price is still rising.
      Next move is MORE LIKELY to be downward. Do NOT extrapolate the uptrend.

    Returns 'bullish', 'bearish', or 'none'.
    """
    if len(df) < lookback + rsi_period + 5:
        return "none"

    close    = df["close"]
    rsi_full = _rsi_series(close, rsi_period).dropna()
    prices   = close.values[-lookback:]
    rsi_vals = rsi_full.values[-lookback:]

    if len(rsi_vals) < lookback - 2:
        return "none"

    mid = lookback // 2
    p1, p2 = prices[:mid],    prices[mid:]
    r1, r2 = rsi_vals[:mid],  rsi_vals[mid:]

    # Bullish divergence: price lower low, RSI higher low
    # Require meaningful gap to avoid noise
    if (p2.min() < p1.min() * 0.9985 and r2.min() > r1.min() + 3.0):
        return "bullish"

    # Bearish divergence: price higher high, RSI lower high
    if (p2.max() > p1.max() * 1.0015 and r2.max() < r1.max() - 3.0):
        return "bearish"

    return "none"


def consecutive_candle_bias(df: pd.DataFrame, lookback: int = 5) -> str:
    """
    Count consecutive up/down candles in the last `lookback` bars.
    Returns 'extended_up', 'extended_down', or 'normal'.

    After 4+ consecutive candles in the SAME direction, mean reversion probability
    increases significantly. A 5th consecutive candle in the same direction is
    NOT a reliable signal to continue -- it is often an exhaustion signal.
    This function flags that condition so the scorer can reduce confidence.
    """
    recent = df.tail(lookback)
    directions = (recent["close"] > recent["open"]).tolist()  # True = bullish candle

    if all(directions):
        return "extended_up"
    if not any(directions):
        return "extended_down"
    return "normal"


def fibonacci_levels(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    Calculate Fibonacci retracement and extension levels from the
    most significant recent swing (highest high to lowest low over lookback).

    Retracement levels: potential S/R zones within the current range.
    Extension levels:   potential targets beyond the swing high/low.
    Used for TP placement and identifying key S/R levels.
    """
    recent     = df.tail(lookback)
    swing_high = float(recent["high"].max())
    swing_low  = float(recent["low"].min())
    diff       = swing_high - swing_low
    last_close = float(df["close"].iloc[-1])

    if diff < 1e-8:
        return {
            "swing_high": round(swing_high, 5),
            "swing_low":  round(swing_low,  5),
            "range":      0.0,
            "retracements": {},
            "extensions_up": {},
            "extensions_down": {},
        }

    # Key Fibonacci ratios
    fib_retrace = [0.236, 0.382, 0.500, 0.618, 0.786]
    fib_extend  = [1.000, 1.272, 1.618, 2.000]

    # Retracements measured from the swing high downward
    retrace_levels = {
        f"{r*100:.1f}%": round(swing_high - r * diff, 5)
        for r in fib_retrace
    }

    # Extensions above swing high (bullish targets)
    ext_up = {
        f"{e*100:.1f}%": round(swing_low + e * diff, 5)
        for e in fib_extend
    }

    # Extensions below swing low (bearish targets)
    ext_down = {
        f"{e*100:.1f}%": round(swing_high - e * diff, 5)
        for e in fib_extend
    }

    return {
        "swing_high":       round(swing_high, 5),
        "swing_low":        round(swing_low,  5),
        "range":            round(diff, 5),
        "retracements":     retrace_levels,    # Support zones in uptrend / resistance in downtrend
        "extensions_up":    ext_up,            # Bullish targets above swing high
        "extensions_down":  ext_down,          # Bearish targets below swing low
        "last_close":       round(last_close, 5),
    }


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
    mask     = dm_plus >= dm_minus
    dm_plus[~mask]  = 0.0
    dm_minus[mask]  = 0.0

    alpha  = 1.0 / period
    atr_s  = tr.ewm(alpha=alpha, adjust=False).mean()
    dip_s  = dm_plus.ewm(alpha=alpha, adjust=False).mean()
    dim_s  = dm_minus.ewm(alpha=alpha, adjust=False).mean()

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
    adx_val         = adx(df)
    bb_cur, bb_prev = bb_width(df["close"])
    expanding       = bb_cur > bb_prev * 1.005

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


# ── Main analysis function ─────────────────────────────────────────────────────

def analyze_timeframe(df: pd.DataFrame) -> dict:
    """
    Run all indicators on one OHLCV dataframe (hourly or daily).
    Returns a rich dict for scoring and TP/SL calculation.

    Signal voting is divergence-aware and mean-reversion-aware:
    - Consecutive same-direction candles reduce confidence (not increase it)
    - RSI at extremes signals REVERSAL probability, not continuation
    - Shrinking MACD histogram signals FADING momentum (reduces confidence)
    - Price/RSI divergence is a strong reversal warning
    """
    close = df["close"]

    _rsi_val          = rsi(close)
    rsi_sl            = rsi_slope(close)
    macd_line, macd_s = macd(close)
    hist_cur, hist_prev = macd_histogram(close)
    ma_fast, ma_slow  = moving_averages(close)
    sup, res          = swing_support_resistance(df)
    vol_pct           = atr_pct(df)
    atr_abs           = atr_absolute(df)
    trend             = trend_direction(close)
    diverge           = momentum_divergence(df)
    candle_bias       = consecutive_candle_bias(df)
    fibs              = fibonacci_levels(df)

    # ── Divergence-aware, mean-reversion-aware voting ─────────────────────────
    #
    # RSI vote: extremes are REVERSAL signals, not continuation
    if _rsi_val <= 25:
        rsi_vote = 1.5    # Deeply oversold -> strong bounce likely
    elif _rsi_val <= 35:
        rsi_vote = 0.9    # Oversold zone -> lean bullish
    elif _rsi_val >= 75:
        rsi_vote = -1.5   # Deeply overbought -> pullback likely
    elif _rsi_val >= 65:
        rsi_vote = -0.9   # Overbought zone -> lean bearish
    else:
        # Neutral zone: combine RSI level with its slope
        level_v = 1.0 if _rsi_val > 53 else -1.0 if _rsi_val < 47 else 0.0
        slope_v = 1.0 if rsi_sl > 0.8 else -1.0 if rsi_sl < -0.8 else (
                  0.5 if rsi_sl > 0.3 else -0.5 if rsi_sl < -0.3 else 0.0)
        rsi_vote = level_v * 0.6 + slope_v * 0.4

    # MACD vote: use histogram direction, not just line vs signal
    # Rising histogram = momentum BUILDING; falling histogram = momentum FADING
    if hist_cur > 0:
        if hist_cur > hist_prev:   # Bullish momentum accelerating
            macd_vote = 1.0
        else:                       # Bullish but momentum fading -- cautious
            macd_vote = 0.3
    elif hist_cur < 0:
        if hist_cur < hist_prev:   # Bearish momentum accelerating
            macd_vote = -1.0
        else:                       # Bearish but momentum fading -- cautious
            macd_vote = -0.3
    else:
        macd_vote = 0.0

    # MA vote: structural trend
    ma_vote    = 1.0 if ma_fast > ma_slow else -1.0

    # Trend vote: price vs MA50
    trend_vote = 1.0 if trend == "up" else -1.0

    # Divergence override: strongest mean-reversion signal
    if diverge == "bullish":
        div_vote = 1.8    # Price/RSI divergence -> expect reversal UP
    elif diverge == "bearish":
        div_vote = -1.8   # Price/RSI divergence -> expect reversal DOWN
    else:
        div_vote = None

    # Consecutive candle exhaustion modifier
    # 4+ candles in same direction reduces confidence in continuation
    if candle_bias == "extended_up":
        exhaustion_adj = -0.4   # Reduce bullish confidence
    elif candle_bias == "extended_down":
        exhaustion_adj = 0.4    # Reduce bearish confidence (mean reversion likely)
    else:
        exhaustion_adj = 0.0

    votes = [rsi_vote, macd_vote, ma_vote, trend_vote]
    if div_vote is not None:
        votes.append(div_vote)  # Divergence carries significant weight

    net = float(np.mean(votes)) + exhaustion_adj

    # Clamp strength to [0, 1]
    direction = "up" if net > 0.1 else "down" if net < -0.1 else "neutral"
    strength  = round(min(abs(net), 1.0), 3)

    stoch_k, stoch_d = stochastic_rsi(close)
    ichi              = ichimoku(df)
    vol               = volume_analysis(df)
    session           = get_session_info()

    return {
        # Core fields (used by scoring)
        "direction":          direction,
        "strength":           strength,
        "rsi":                round(_rsi_val, 1),
        "macd_above_signal":  bool(macd_line > macd_s),
        "ma20_above_ma50":    bool(ma_fast > ma_slow),
        "trend":              trend,
        "support":            round(sup, 5),
        "resistance":         round(res, 5),
        "volatility_atr_pct": round(vol_pct, 3),
        "last_price":         round(float(close.iloc[-1]), 5),

        # New enriched fields (used for TP/SL, UI display)
        "rsi_slope":          round(rsi_sl, 3),
        "macd_histogram":     round(hist_cur, 6),
        "macd_hist_rising":   bool(hist_cur > hist_prev),
        "divergence":         diverge,            # 'bullish', 'bearish', or 'none'
        "candle_bias":        candle_bias,         # 'extended_up', 'extended_down', 'normal'
        "atr_absolute":       round(atr_abs, 6),
        "fibonacci":          fibs,

        # Advanced indicators
        "stoch_rsi_k":    stoch_k,
        "stoch_rsi_d":    stoch_d,
        "stoch_signal":   "overbought" if stoch_k > 80 else "oversold" if stoch_k < 20 else "neutral",
        "ichimoku":       ichi,
        "volume":         vol,
        "session":        session,
    }


def stochastic_rsi(series: pd.Series, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3) -> tuple[float, float]:
    """Stochastic RSI - more sensitive than standard RSI for overbought/oversold"""
    rsi_s = _rsi_series(series, rsi_period).dropna()
    if len(rsi_s) < stoch_period + k_smooth + d_smooth:
        return 50.0, 50.0
    rsi_min   = rsi_s.rolling(stoch_period).min()
    rsi_max   = rsi_s.rolling(stoch_period).max()
    rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
    stoch_raw = (rsi_s - rsi_min) / rsi_range * 100
    k = stoch_raw.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    k_val = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50.0
    d_val = float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 50.0
    return round(k_val, 1), round(d_val, 1)


def ichimoku(df: pd.DataFrame) -> dict:
    """
    Full Ichimoku Kinko Hyo. Standard settings 9/26/52.
    Returns cloud position, TK cross signal, and overall direction.
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tenkan  = (high.rolling(9).max()  + low.rolling(9).min())  / 2
    kijun   = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a  = ((tenkan + kijun) / 2).shift(26)
    span_b  = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    def _s(series):
        v = series.iloc[-1]
        return round(float(v), 5) if not pd.isna(v) else None

    t  = _s(tenkan)
    k  = _s(kijun)
    sa = _s(span_a)
    sb = _s(span_b)

    last = float(close.iloc[-1])

    cloud_top = max(sa, sb) if sa and sb else None
    cloud_bot = min(sa, sb) if sa and sb else None

    if cloud_top and cloud_bot:
        if last > cloud_top:
            cloud_pos = "above"
        elif last < cloud_bot:
            cloud_pos = "below"
        else:
            cloud_pos = "inside"
        cloud_bullish = sa > sb if sa and sb else None
    else:
        cloud_pos = "unknown"
        cloud_bullish = None

    if t and k:
        tk = "bullish" if t > k else "bearish" if t < k else "neutral"
    else:
        tk = "neutral"

    if cloud_pos == "above" and tk == "bullish":
        direction, strength = "up", 1.0
    elif cloud_pos == "below" and tk == "bearish":
        direction, strength = "down", 1.0
    elif cloud_pos == "above" or tk == "bullish":
        direction, strength = "up", 0.5
    elif cloud_pos == "below" or tk == "bearish":
        direction, strength = "down", 0.5
    else:
        direction, strength = "neutral", 0.0

    return {
        "tenkan": t, "kijun": k, "span_a": sa, "span_b": sb,
        "cloud_top": cloud_top, "cloud_bottom": cloud_bot,
        "cloud_position": cloud_pos,   # "above", "below", "inside", "unknown"
        "cloud_bullish":  cloud_bullish,
        "tk_cross":       tk,          # "bullish", "bearish", "neutral"
        "direction":      direction,
        "strength":       strength,
        "available":      cloud_top is not None,
    }


def volume_analysis(df: pd.DataFrame) -> dict:
    """
    OBV + volume ratio analysis. Returns bullish/bearish/neutral signal.
    Requires 'volume' column. Falls back gracefully if missing.
    Rising OBV + price rising = confirmed bullish.
    Rising OBV + price falling = bullish divergence (smart money accumulating).
    """
    if "volume" not in df.columns or df["volume"].isnull().all():
        return {"available": False}

    close  = df["close"]
    volume = df["volume"].fillna(0)

    # OBV
    price_dir = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv_s     = (price_dir * volume).cumsum()

    if len(obv_s.dropna()) < 10:
        return {"available": False}

    recent_obv   = obv_s.dropna().tail(10).values
    recent_price = close.tail(10).values
    x = np.arange(len(recent_obv))

    obv_slope   = float(np.polyfit(x, recent_obv,   1)[0])
    price_slope = float(np.polyfit(x, recent_price, 1)[0])

    obv_rising   = obv_slope   > 0
    price_rising = price_slope > 0

    if obv_rising and not price_rising:
        divergence = "bullish"
    elif not obv_rising and price_rising:
        divergence = "bearish"
    else:
        divergence = "none"

    vol_avg   = float(volume.rolling(20).mean().iloc[-1]) or 1.0
    vol_cur   = float(volume.tail(3).mean())
    vol_ratio = round(vol_cur / vol_avg, 2)

    # Signal: direction + volume confirmation
    if obv_rising and vol_ratio > 1.15:
        signal = "bullish"
    elif not obv_rising and vol_ratio > 1.15:
        signal = "bearish"
    elif divergence != "none":
        signal = divergence
    else:
        signal = "neutral"

    return {
        "available":   True,
        "obv_rising":  obv_rising,
        "divergence":  divergence,
        "vol_ratio":   vol_ratio,
        "high_volume": vol_ratio > 1.3,
        "signal":      signal,
        "direction":   "up" if obv_rising else "down",
    }


def get_session_info() -> dict:
    """
    Current Forex trading session based on UTC time.
    Returns session quality for signal reliability.
    Best trading time: London/NY overlap (13:00-17:00 UTC).
    """
    from datetime import datetime, timezone
    now  = datetime.now(timezone.utc)
    hour = now.hour
    wd   = now.weekday()

    if wd >= 5:
        return {"sessions": [], "quality": "closed", "note": "Market closed (weekend)", "best_time": False, "hour_utc": hour}

    sessions = []
    if hour >= 21 or hour < 6:  sessions.append("Sydney")
    if 0  <= hour < 9:          sessions.append("Tokyo")
    if 8  <= hour < 17:         sessions.append("London")
    if 13 <= hour < 22:         sessions.append("New York")

    ln_ny  = 13 <= hour < 17
    tk_ln  =  8 <= hour < 9

    if ln_ny:
        quality, note = "excellent", "London/New York overlap - best liquidity"
    elif "London" in sessions:
        quality, note = "good", "London session - high liquidity"
    elif "New York" in sessions:
        quality, note = "good", "New York session - high liquidity"
    elif tk_ln:
        quality, note = "good", "Tokyo/London overlap"
    elif "Tokyo" in sessions or "Sydney" in sessions:
        quality, note = "moderate", "Asian session - lower liquidity for major pairs"
    else:
        quality, note = "low", "Off-hours - avoid new positions"

    return {
        "sessions":  sessions or ["Off-Hours"],
        "quality":   quality,
        "note":      note,
        "best_time": quality in ("excellent", "good"),
        "hour_utc":  hour,
    }


# ── Smoke test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    np.random.seed(42)
    prices = pd.Series(1.08 + np.cumsum(np.random.randn(200) * 0.001))
    df = pd.DataFrame({
        "close": prices,
        "high":  prices + 0.002,
        "low":   prices - 0.002,
        "open":  prices.shift(1).fillna(prices),
    })
    print("RSI     :", rsi(prices))
    print("RSI slope:", rsi_slope(prices))
    print("MACD    :", macd(prices))
    print("Hist    :", macd_histogram(prices))
    print("Diverg  :", momentum_divergence(df))
    print("Candles :", consecutive_candle_bias(df))
    print("SwingS/R:", swing_support_resistance(df))
    print("Fibs    :", {k: v for k, v in fibonacci_levels(df).items() if k != "retracements"})
    print("Full    :", {k: v for k, v in analyze_timeframe(df).items() if k != "fibonacci"})
