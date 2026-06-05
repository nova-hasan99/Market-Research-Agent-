"""
Standard worldwide technical pattern detection.
Works for any asset: Forex, Stocks, Commodities, Crypto.

Two categories:
  1. Candlestick patterns  (1-3 candle formations)
  2. Chart patterns        (structural patterns over 20-100 candles)

Each detected pattern returns:
  {
    "name":        str,          # pattern name
    "type":        str,          # "candlestick" | "chart"
    "direction":   str,          # "up", "down", "neutral"
    "strength":    int,          # 1 (weak) | 2 (moderate) | 3 (strong)
    "description": str,          # what it means for traders
    "reliability": str,          # "low" | "moderate" | "high"
  }
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ── Candle helpers ────────────────────────────────────────────────────────────

def _body(c: pd.Series) -> float:
    return abs(float(c["close"]) - float(c["open"]))

def _upper_wick(c: pd.Series) -> float:
    return float(c["high"]) - max(float(c["close"]), float(c["open"]))

def _lower_wick(c: pd.Series) -> float:
    return min(float(c["close"]), float(c["open"])) - float(c["low"])

def _range(c: pd.Series) -> float:
    return float(c["high"]) - float(c["low"])

def _is_bull(c: pd.Series) -> bool:
    return float(c["close"]) > float(c["open"])

def _is_bear(c: pd.Series) -> bool:
    return float(c["close"]) < float(c["open"])

def _midpoint(c: pd.Series) -> float:
    return (float(c["open"]) + float(c["close"])) / 2


# ── Candlestick patterns ──────────────────────────────────────────────────────

def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict]:
    """
    Detect all standard candlestick patterns from the last 3 candles.
    Requires columns: open, high, low, close.
    """
    if len(df) < 3 or "open" not in df.columns:
        return []

    results: list[dict] = []
    c1 = df.iloc[-3]   # 3 bars ago
    c2 = df.iloc[-2]   # 2 bars ago
    c3 = df.iloc[-1]   # Current / most recent

    # ── Single-candle patterns ─────────────────────────────────────────────

    r3  = _range(c3)
    b3  = _body(c3)
    uw3 = _upper_wick(c3)
    lw3 = _lower_wick(c3)

    if r3 > 0:
        body_ratio = b3 / r3

        # Doji (open ≈ close)
        if body_ratio < 0.08:
            if lw3 > uw3 * 2:
                results.append({
                    "name": "Dragonfly Doji", "type": "candlestick",
                    "direction": "up", "strength": 2,
                    "description": "Long lower wick with tiny body - strong bullish reversal signal at support",
                    "reliability": "high",
                })
            elif uw3 > lw3 * 2:
                results.append({
                    "name": "Gravestone Doji", "type": "candlestick",
                    "direction": "down", "strength": 2,
                    "description": "Long upper wick with tiny body - strong bearish reversal signal at resistance",
                    "reliability": "high",
                })
            else:
                results.append({
                    "name": "Doji", "type": "candlestick",
                    "direction": "neutral", "strength": 1,
                    "description": "Market indecision - buyers and sellers in equilibrium. Watch for breakout",
                    "reliability": "moderate",
                })

        # Marubozu (strong momentum, minimal wicks) — check before others
        elif body_ratio > 0.85:
            dir_ = "up" if _is_bull(c3) else "down"
            results.append({
                "name": f"{'Bullish' if dir_ == 'up' else 'Bearish'} Marubozu",
                "type": "candlestick", "direction": dir_, "strength": 2,
                "description": (
                    "Strong bullish candle with almost no wicks - buyers in full control"
                    if dir_ == "up" else
                    "Strong bearish candle with almost no wicks - sellers in full control"
                ),
                "reliability": "moderate",
            })

        # Hammer / Hanging Man — check BEFORE Spinning Top (more specific)
        # Long lower wick (>= 2x body), small upper wick (<= body or 30% of lower wick)
        elif lw3 >= b3 * 2.0 and uw3 <= max(b3, lw3 * 0.3) and body_ratio < 0.4:
            if _is_bear(c2):   # After downtrend = Hammer (bullish)
                results.append({
                    "name": "Hammer", "type": "candlestick",
                    "direction": "up", "strength": 2,
                    "description": "Hammer after downtrend - sellers rejected lower prices, buyers stepping in",
                    "reliability": "high",
                })
            elif _is_bull(c2):   # After uptrend = Hanging Man (bearish warning)
                results.append({
                    "name": "Hanging Man", "type": "candlestick",
                    "direction": "down", "strength": 2,
                    "description": "Hanging Man after uptrend - selling pressure emerging, potential top",
                    "reliability": "moderate",
                })

        # Inverted Hammer / Shooting Star — check BEFORE Spinning Top (more specific)
        # Long upper wick (>= 2x body), small lower wick (<= body or 30% of upper wick)
        elif uw3 >= b3 * 2.0 and lw3 <= max(b3, uw3 * 0.3) and body_ratio < 0.4:
            if _is_bear(c2):   # After downtrend = Inverted Hammer (bullish)
                results.append({
                    "name": "Inverted Hammer", "type": "candlestick",
                    "direction": "up", "strength": 2,
                    "description": "Inverted Hammer after downtrend - buyers testing higher prices, potential reversal",
                    "reliability": "moderate",
                })
            elif _is_bull(c2):   # After uptrend = Shooting Star (bearish)
                results.append({
                    "name": "Shooting Star", "type": "candlestick",
                    "direction": "down", "strength": 3,
                    "description": "Shooting Star at top - buyers rejected, strong reversal signal",
                    "reliability": "high",
                })

        # Spinning Top — least specific, catches remaining small-body candles
        # Only if NEITHER wick clearly dominates (Hammer/Shooting Star not triggered)
        elif body_ratio < 0.25 and uw3 > b3 * 0.5 and lw3 > b3 * 0.5:
            results.append({
                "name": "Spinning Top", "type": "candlestick",
                "direction": "neutral", "strength": 1,
                "description": "Small body with both wicks - indecision, potential trend pause or reversal",
                "reliability": "low",
            })

    # ── Two-candle patterns ────────────────────────────────────────────────

    b2  = _body(c2)
    r2  = _range(c2)

    # Bullish Engulfing
    if (_is_bear(c2) and _is_bull(c3) and
            float(c3["open"]) <= float(c2["close"]) and
            float(c3["close"]) >= float(c2["open"]) and b3 > b2):
        results.append({
            "name": "Bullish Engulfing", "type": "candlestick",
            "direction": "up", "strength": 3,
            "description": "Bullish candle fully engulfs previous bearish candle - strong reversal. Volume confirmation increases reliability",
            "reliability": "high",
        })

    # Bearish Engulfing
    elif (_is_bull(c2) and _is_bear(c3) and
          float(c3["open"]) >= float(c2["close"]) and
          float(c3["close"]) <= float(c2["open"]) and b3 > b2):
        results.append({
            "name": "Bearish Engulfing", "type": "candlestick",
            "direction": "down", "strength": 3,
            "description": "Bearish candle fully engulfs previous bullish candle - strong reversal. Volume confirmation increases reliability",
            "reliability": "high",
        })

    # Bullish Harami (inside bar after downtrend)
    elif (_is_bear(c2) and _is_bull(c3) and
          float(c3["open"]) > float(c2["close"]) and
          float(c3["close"]) < float(c2["open"]) and b3 < b2):
        results.append({
            "name": "Bullish Harami", "type": "candlestick",
            "direction": "up", "strength": 1,
            "description": "Small bullish candle inside previous bearish candle - possible pause in downtrend",
            "reliability": "low",
        })

    # Bearish Harami (inside bar after uptrend)
    elif (_is_bull(c2) and _is_bear(c3) and
          float(c3["open"]) < float(c2["close"]) and
          float(c3["close"]) > float(c2["open"]) and b3 < b2):
        results.append({
            "name": "Bearish Harami", "type": "candlestick",
            "direction": "down", "strength": 1,
            "description": "Small bearish candle inside previous bullish candle - possible pause in uptrend",
            "reliability": "low",
        })

    # Tweezer Tops (two candles with same high = double rejection)
    if (abs(float(c2["high"]) - float(c3["high"])) < _range(c2) * 0.05 and
            _is_bull(c2) and _is_bear(c3)):
        results.append({
            "name": "Tweezer Top", "type": "candlestick",
            "direction": "down", "strength": 2,
            "description": "Two candles with equal highs - price rejected twice at same level, strong resistance",
            "reliability": "moderate",
        })

    # Tweezer Bottoms (two candles with same low = double support)
    if (abs(float(c2["low"]) - float(c3["low"])) < _range(c2) * 0.05 and
            _is_bear(c2) and _is_bull(c3)):
        results.append({
            "name": "Tweezer Bottom", "type": "candlestick",
            "direction": "up", "strength": 2,
            "description": "Two candles with equal lows - price supported twice at same level, strong support",
            "reliability": "moderate",
        })

    # ── Three-candle patterns ──────────────────────────────────────────────

    b1 = _body(c1)
    r1 = _range(c1)

    # Morning Star (bullish reversal)
    if (_is_bear(c1) and b2 < r2 * 0.35 and _is_bull(c3) and
            float(c3["close"]) > _midpoint(c1) and b1 > r1 * 0.5):
        results.append({
            "name": "Morning Star", "type": "candlestick",
            "direction": "up", "strength": 3,
            "description": "Morning Star: bearish candle, indecision, then strong bullish - classic reversal at bottom",
            "reliability": "high",
        })

    # Evening Star (bearish reversal)
    elif (_is_bull(c1) and b2 < r2 * 0.35 and _is_bear(c3) and
          float(c3["close"]) < _midpoint(c1) and b1 > r1 * 0.5):
        results.append({
            "name": "Evening Star", "type": "candlestick",
            "direction": "down", "strength": 3,
            "description": "Evening Star: bullish candle, indecision, then strong bearish - classic reversal at top",
            "reliability": "high",
        })

    # Three White Soldiers (strong bullish continuation)
    if (_is_bull(c1) and _is_bull(c2) and _is_bull(c3) and
            float(c2["close"]) > float(c1["close"]) and
            float(c3["close"]) > float(c2["close"]) and
            b1 > r1 * 0.5 and b2 > r2 * 0.5 and b3 > r3 * 0.5):
        results.append({
            "name": "Three White Soldiers", "type": "candlestick",
            "direction": "up", "strength": 3,
            "description": "Three consecutive strong bullish candles - powerful upward momentum, bulls in control",
            "reliability": "high",
        })

    # Three Black Crows (strong bearish continuation)
    elif (_is_bear(c1) and _is_bear(c2) and _is_bear(c3) and
          float(c2["close"]) < float(c1["close"]) and
          float(c3["close"]) < float(c2["close"]) and
          b1 > r1 * 0.5 and b2 > r2 * 0.5 and b3 > r3 * 0.5):
        results.append({
            "name": "Three Black Crows", "type": "candlestick",
            "direction": "down", "strength": 3,
            "description": "Three consecutive strong bearish candles - powerful downward momentum, bears in control",
            "reliability": "high",
        })

    # Three Inside Up (bullish reversal confirmation)
    if (_is_bear(c1) and _is_bull(c2) and _is_bull(c3) and
            float(c2["open"]) > float(c1["close"]) and
            float(c2["close"]) < float(c1["open"]) and
            float(c3["close"]) > float(c1["open"])):
        results.append({
            "name": "Three Inside Up", "type": "candlestick",
            "direction": "up", "strength": 2,
            "description": "Bullish harami followed by confirmation candle - reversal confirmed",
            "reliability": "moderate",
        })

    # Three Inside Down (bearish reversal confirmation)
    elif (_is_bull(c1) and _is_bear(c2) and _is_bear(c3) and
          float(c2["open"]) < float(c1["close"]) and
          float(c2["close"]) > float(c1["open"]) and
          float(c3["close"]) < float(c1["open"])):
        results.append({
            "name": "Three Inside Down", "type": "candlestick",
            "direction": "down", "strength": 2,
            "description": "Bearish harami followed by confirmation candle - reversal confirmed",
            "reliability": "moderate",
        })

    return results


# ── Chart patterns ────────────────────────────────────────────────────────────

def _find_swing_highs_lows(highs: np.ndarray, lows: np.ndarray,
                            win: int = 3) -> tuple[list[int], list[int]]:
    """Return indices of swing highs and swing lows."""
    n      = len(highs)
    s_high = [i for i in range(win, n - win)
               if highs[i] == max(highs[i - win: i + win + 1])]
    s_low  = [i for i in range(win, n - win)
               if lows[i]  == min(lows[i  - win: i + win + 1])]
    return s_high, s_low


def detect_chart_patterns(df: pd.DataFrame, lookback: int = 60) -> list[dict]:
    """
    Detect structural chart patterns over the last `lookback` candles.
    Works for any timeframe and any globally traded asset.
    """
    if len(df) < 20:
        return []

    results: list[dict] = []
    recent = df.tail(lookback)

    highs  = recent["high"].values.astype(float)
    lows   = recent["low"].values.astype(float)
    closes = recent["close"].values.astype(float)
    n      = len(closes)
    cur    = closes[-1]

    swing_highs_idx, swing_lows_idx = _find_swing_highs_lows(highs, lows)

    sh_vals = [highs[i]  for i in swing_highs_idx]
    sl_vals = [lows[i]   for i in swing_lows_idx]

    price_range = highs.max() - lows.min()
    if price_range < 1e-10:
        return []

    tol = price_range * 0.025   # 2.5% tolerance for "equal" levels

    # ── Double Top ───────────────────────────────────────────────────────────
    if len(sh_vals) >= 2:
        h1, h2 = sh_vals[-2], sh_vals[-1]
        if abs(h1 - h2) < tol and h1 > cur * 1.001:
            # Neckline: lowest low between the two tops
            between = sl_vals[max(0, len(sl_vals) - 3):]
            neck    = min(between) if between else (h1 + h2) / 2 * 0.97
            results.append({
                "name": "Double Top", "type": "chart",
                "direction": "down", "strength": 3,
                "description": (
                    f"Two peaks at similar level ({h1:.5g} / {h2:.5g}). "
                    f"Neckline around {neck:.5g}. Break below neckline confirms bearish reversal."
                ),
                "reliability": "high",
            })

    # ── Double Bottom ────────────────────────────────────────────────────────
    if len(sl_vals) >= 2:
        l1, l2 = sl_vals[-2], sl_vals[-1]
        if abs(l1 - l2) < tol and l1 < cur * 0.999:
            between = sh_vals[max(0, len(sh_vals) - 3):]
            neck    = max(between) if between else (l1 + l2) / 2 * 1.03
            results.append({
                "name": "Double Bottom", "type": "chart",
                "direction": "up", "strength": 3,
                "description": (
                    f"Two troughs at similar level ({l1:.5g} / {l2:.5g}). "
                    f"Neckline around {neck:.5g}. Break above neckline confirms bullish reversal."
                ),
                "reliability": "high",
            })

    # ── Head and Shoulders ───────────────────────────────────────────────────
    if len(sh_vals) >= 3 and len(sl_vals) >= 2:
        left, head, right = sh_vals[-3], sh_vals[-2], sh_vals[-1]
        if (head > left * 1.005 and head > right * 1.005 and
                abs(left - right) < tol * 2):
            neck = min(sl_vals[-2], sl_vals[-1]) if len(sl_vals) >= 2 else lows.min()
            results.append({
                "name": "Head and Shoulders", "type": "chart",
                "direction": "down", "strength": 3,
                "description": (
                    f"Classic H&S top: head at {head:.5g}, shoulders at {left:.5g}/{right:.5g}. "
                    f"Neckline around {neck:.5g}. Highly reliable bearish reversal pattern."
                ),
                "reliability": "high",
            })

    # ── Inverse Head and Shoulders ───────────────────────────────────────────
    if len(sl_vals) >= 3 and len(sh_vals) >= 2:
        left, head, right = sl_vals[-3], sl_vals[-2], sl_vals[-1]
        if (head < left * 0.995 and head < right * 0.995 and
                abs(left - right) < tol * 2):
            neck = max(sh_vals[-2], sh_vals[-1]) if len(sh_vals) >= 2 else highs.max()
            results.append({
                "name": "Inverse Head and Shoulders", "type": "chart",
                "direction": "up", "strength": 3,
                "description": (
                    f"Inverse H&S bottom: head at {head:.5g}, shoulders at {left:.5g}/{right:.5g}. "
                    f"Neckline around {neck:.5g}. Highly reliable bullish reversal pattern."
                ),
                "reliability": "high",
            })

    # ── Triangle patterns (using trendlines) ─────────────────────────────────
    if len(sh_vals) >= 2 and len(sl_vals) >= 2:
        # Slopes of highs trendline and lows trendline
        high_slope = (sh_vals[-1] - sh_vals[-2]) / max(
            swing_highs_idx[-1] - swing_highs_idx[-2], 1)
        low_slope  = (sl_vals[-1] - sl_vals[-2]) / max(
            swing_lows_idx[-1] - swing_lows_idx[-2], 1)

        # Ascending Triangle: flat resistance + rising support
        if abs(high_slope) < price_range * 0.0005 and low_slope > price_range * 0.0005:
            results.append({
                "name": "Ascending Triangle", "type": "chart",
                "direction": "up", "strength": 2,
                "description": (
                    f"Rising support meets flat resistance around {sh_vals[-1]:.5g}. "
                    "Bullish continuation - break above resistance expected."
                ),
                "reliability": "moderate",
            })

        # Descending Triangle: falling resistance + flat support
        elif high_slope < -price_range * 0.0005 and abs(low_slope) < price_range * 0.0005:
            results.append({
                "name": "Descending Triangle", "type": "chart",
                "direction": "down", "strength": 2,
                "description": (
                    f"Falling resistance meets flat support around {sl_vals[-1]:.5g}. "
                    "Bearish continuation - break below support expected."
                ),
                "reliability": "moderate",
            })

        # Symmetrical Triangle: converging trendlines
        elif high_slope < -price_range * 0.0003 and low_slope > price_range * 0.0003:
            results.append({
                "name": "Symmetrical Triangle", "type": "chart",
                "direction": "neutral", "strength": 1,
                "description": (
                    "Converging highs and lows - consolidation. "
                    "Breakout direction will determine next trend. Watch volume on breakout."
                ),
                "reliability": "moderate",
            })

        # Rising Wedge (bearish - both trendlines rising but converging)
        elif (high_slope > 0 and low_slope > 0 and
              low_slope > high_slope * 1.2 and n > 15):
            results.append({
                "name": "Rising Wedge", "type": "chart",
                "direction": "down", "strength": 2,
                "description": (
                    "Both support and resistance rising but converging - bearish. "
                    "Break below rising support signals reversal."
                ),
                "reliability": "moderate",
            })

        # Falling Wedge (bullish - both trendlines falling but converging)
        elif (high_slope < 0 and low_slope < 0 and
              abs(high_slope) > abs(low_slope) * 1.2 and n > 15):
            results.append({
                "name": "Falling Wedge", "type": "chart",
                "direction": "up", "strength": 2,
                "description": (
                    "Both support and resistance falling but converging - bullish. "
                    "Break above falling resistance signals reversal."
                ),
                "reliability": "moderate",
            })

    # ── Flag / Pennant (momentum continuation) ───────────────────────────────
    if n >= 15:
        # Check for sharp move followed by consolidation
        first_third  = closes[:n // 3]
        last_third   = closes[2 * n // 3:]

        pre_move  = abs(first_third[-1] - first_third[0])
        consol    = abs(last_third.max() - last_third.min())

        if pre_move > price_range * 0.3 and consol < pre_move * 0.4:
            direction = "up" if first_third[-1] > first_third[0] else "down"
            results.append({
                "name": f"{'Bullish' if direction == 'up' else 'Bearish'} Flag",
                "type": "chart",
                "direction": direction, "strength": 2,
                "description": (
                    f"Strong {'upward' if direction == 'up' else 'downward'} move "
                    f"followed by tight consolidation. "
                    "Continuation pattern - breakout likely in same direction as the pole."
                ),
                "reliability": "moderate",
            })

    # ── Support/Resistance breakout ───────────────────────────────────────────
    if len(sh_vals) >= 2 and len(sl_vals) >= 2:
        recent_res = sh_vals[-1]
        recent_sup = sl_vals[-1]

        # Bullish breakout above resistance
        if cur > recent_res and closes[-2] <= recent_res:
            results.append({
                "name": "Resistance Breakout", "type": "chart",
                "direction": "up", "strength": 2,
                "description": (
                    f"Price just broke above resistance at {recent_res:.5g}. "
                    "Former resistance becomes new support. Confirm with above-average volume."
                ),
                "reliability": "moderate",
            })

        # Bearish breakdown below support
        elif cur < recent_sup and closes[-2] >= recent_sup:
            results.append({
                "name": "Support Breakdown", "type": "chart",
                "direction": "down", "strength": 2,
                "description": (
                    f"Price just broke below support at {recent_sup:.5g}. "
                    "Former support becomes new resistance. Confirm with above-average volume."
                ),
                "reliability": "moderate",
            })

    return results


# ── Combined pattern analysis ─────────────────────────────────────────────────

def analyze_patterns(df: pd.DataFrame) -> dict:
    """
    Run both candlestick and chart pattern detection.
    Returns a summary with overall direction bias from patterns.
    """
    if "open" not in df.columns:
        return {"available": False, "patterns": [], "bias": "neutral", "count": 0}

    candle_patterns = detect_candlestick_patterns(df)
    chart_patterns  = detect_chart_patterns(df)
    all_patterns    = candle_patterns + chart_patterns

    if not all_patterns:
        return {
            "available": True,
            "patterns":  [],
            "bias":      "neutral",
            "count":     0,
            "strongest": None,
        }

    # Weighted direction vote (strength * direction)
    vote = sum(
        p["strength"] * (1 if p["direction"] == "up" else -1 if p["direction"] == "down" else 0)
        for p in all_patterns
    )
    max_strength = sum(p["strength"] for p in all_patterns)
    bias_score   = vote / max_strength if max_strength > 0 else 0

    bias = "up" if bias_score > 0.2 else "down" if bias_score < -0.2 else "neutral"

    # Sort by strength (highest first)
    all_patterns.sort(key=lambda x: x["strength"], reverse=True)

    return {
        "available": True,
        "patterns":  all_patterns,
        "bias":      bias,
        "count":     len(all_patterns),
        "strongest": all_patterns[0] if all_patterns else None,
        "bias_score": round(bias_score, 3),
    }
