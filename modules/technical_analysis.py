"""Rule-based technical indicators using Pandas.

This is transparent demo math, not a machine-learning predictor.
"""
from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    close = out["close"]
    vol = out["volume"]

    out["sma20"] = close.rolling(20, min_periods=1).mean()
    out["sma50"] = close.rolling(50, min_periods=1).mean()
    out["ema20"] = close.ewm(span=20, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    out["rsi14"] = 100 - (100 / (1 + rs))
    out["rsi14"] = out["rsi14"].fillna(50.0)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    out["momentum"] = close.pct_change(10) * 100.0
    out["volatility"] = close.pct_change().rolling(20, min_periods=5).std() * (252 ** 0.5) * 100
    out["volume_sma20"] = vol.rolling(20, min_periods=1).mean()
    out["volume_trend"] = (vol / out["volume_sma20"].replace(0, pd.NA) - 1.0) * 100.0
    return out


def latest_metrics(df: pd.DataFrame) -> dict:
    row = add_indicators(df).iloc[-1]
    price = float(row["close"])
    sma20 = float(row["sma20"])
    sma50 = float(row["sma50"])
    return {
        "price": price,
        "sma20": sma20,
        "sma50": sma50,
        "ema20": float(row["ema20"]),
        "rsi14": float(row["rsi14"]),
        "macd": float(row["macd"]),
        "macd_signal": float(row["macd_signal"]),
        "momentum": float(row["momentum"]) if pd.notna(row["momentum"]) else 0.0,
        "volatility": float(row["volatility"]) if pd.notna(row["volatility"]) else 0.0,
        "volume": int(row["volume"]),
        "volume_sma20": float(row["volume_sma20"]),
        "volume_trend": float(row["volume_trend"]) if pd.notna(row["volume_trend"]) else 0.0,
        "price_gt_sma20": price > sma20,
        "sma20_gt_sma50": sma20 > sma50,
        "price_lt_sma50": price < sma50,
    }


def technical_score(metrics: dict, settings: dict) -> tuple[int, list[dict]]:
    """Transparent scoring. Thresholds come from settings."""
    score = 0
    reasons: list[dict] = []

    if metrics["price_gt_sma20"]:
        score += 2
        reasons.append({"ok": True, "text": "Price is above SMA20 (+2)"})
    else:
        reasons.append({"ok": False, "text": "Price is below SMA20"})

    if metrics["sma20_gt_sma50"]:
        score += 2
        reasons.append({"ok": True, "text": "SMA20 is above SMA50 (+2)"})
    else:
        reasons.append({"ok": False, "text": "SMA20 is not above SMA50"})

    rsi = metrics["rsi14"]
    if 40 <= rsi <= 65:
        score += 1
        reasons.append({"ok": True, "text": f"RSI {rsi:.1f} is in a balanced 40–65 band (+1)"})
    else:
        reasons.append({"ok": False, "text": f"RSI {rsi:.1f} is outside the 40–65 band"})

    if metrics["macd"] > metrics["macd_signal"]:
        score += 1
        reasons.append({"ok": True, "text": "MACD is above its signal line (+1)"})
    else:
        reasons.append({"ok": False, "text": "MACD is below its signal line"})

    if metrics["momentum"] > 0:
        score += 1
        reasons.append({"ok": True, "text": f"10-day momentum is positive ({metrics['momentum']:.2f}%) (+1)"})
    else:
        score -= 1
        reasons.append({"ok": False, "text": f"10-day momentum is negative ({metrics['momentum']:.2f}%) (-1)"})

    if rsi > 75:
        score -= 2
        reasons.append({"ok": False, "text": f"RSI {rsi:.1f} is elevated above 75 (-2)"})

    if metrics["price_lt_sma50"]:
        score -= 2
        reasons.append({"ok": False, "text": "Price is below SMA50 (-2)"})

    label = "HOLD"
    buy_cut = int(settings.get("tech_score_buy", 4))
    hold_low = int(settings.get("tech_score_hold_low", 1))
    if score >= buy_cut:
        label = "BUY"
    elif score <= 0 or score < hold_low:
        label = "SELL"
    else:
        label = "HOLD"
    return score, reasons


def max_drawdown(closes: pd.Series) -> float:
    if closes.empty:
        return 0.0
    peak = closes.cummax()
    dd = (closes - peak) / peak.replace(0, pd.NA)
    return float(dd.min() * 100.0) if dd.notna().any() else 0.0
