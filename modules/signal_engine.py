"""Combined Demo AI Mentor Signal.

Educational/demo scoring from sample data and predefined rules.
This is not financial advice and does not predict future prices with certainty.
"""
from __future__ import annotations

from modules.news_analysis import get_news_provider, score_news
from modules.technical_analysis import latest_metrics, technical_score


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def map_signal(overall: float, settings: dict) -> str:
    buy = float(settings.get("buy_threshold", 70))
    hold_low = float(settings.get("hold_low", 45))
    if overall >= buy:
        return "BUY"
    if overall >= hold_low:
        return "HOLD"
    return "SELL"


def strength_for(overall: float, signal: str) -> str:
    if signal == "BUY" and overall >= 85:
        return "Strong"
    if signal == "SELL" and overall <= 25:
        return "Strong"
    if signal == "HOLD" and 50 <= overall <= 60:
        return "Mild"
    if abs(overall - 50) < 8:
        return "Mild"
    return "Moderate"


def analyze_stock(
    ticker: str,
    name: str,
    hist,
    settings: dict,
    news_provider=None,
    *,
    include_news: bool = True,
) -> dict:
    metrics = latest_metrics(hist)
    tech_pts, tech_reasons = technical_score(metrics, settings)
    # Map technical integer score (~ -6 to +7) onto 0–100.
    tech_100 = _clip((tech_pts + 6) / 13 * 100)

    mom = metrics["momentum"]
    mom_100 = _clip(50 + mom * 4)

    if include_news:
        news_provider = news_provider or get_news_provider()
        articles = news_provider.for_ticker(ticker, name)
        news = score_news(articles)
    else:
        # Fast path for dashboard / first paint — news filled in lazily later.
        articles = []
        news = {
            "score": 0.0,
            "label": "Pending",
            "count": 0,
            "explanation": "News loads when you open Stocks, Analysis, or Bot.",
        }
    news_100 = _clip(50 + news["score"] * 40)

    vol_trend = metrics["volume_trend"]
    vol_100 = _clip(50 + vol_trend * 0.8)

    tw = float(settings.get("technical_weight", 0.50))
    mw = float(settings.get("momentum_weight", 0.20))
    nw = float(settings.get("news_weight", 0.20))
    vw = float(settings.get("volume_weight", 0.10))
    total_w = tw + mw + nw + vw or 1.0
    tw, mw, nw, vw = tw / total_w, mw / total_w, nw / total_w, vw / total_w

    overall = tw * tech_100 + mw * mom_100 + nw * news_100 + vw * vol_100
    overall = round(_clip(overall), 1)
    signal = map_signal(overall, settings)
    confidence = int(round(abs(overall - 50) * 1.6 + 20))
    confidence = max(20, min(92, confidence))

    factors = [
        {"name": "Technical Analysis", "weight": tw, "component": round(tech_100, 1), "note": f"Rule score {tech_pts}"},
        {"name": "Momentum", "weight": mw, "component": round(mom_100, 1), "note": f"{mom:.2f}% 10-day"},
        {"name": "News Sentiment", "weight": nw, "component": round(news_100, 1), "note": f"{news['label']} ({news['score']:+.2f}) news"},
        {"name": "Volume", "weight": vw, "component": round(vol_100, 1), "note": f"{vol_trend:+.1f}% vs 20-day avg"},
    ]

    checklist = []
    checklist.append({"ok": metrics["price_gt_sma20"], "text": "Price above SMA20"})
    checklist.append({"ok": metrics["sma20_gt_sma50"], "text": "SMA20 above SMA50 (uptrend stack)"})
    checklist.append({"ok": metrics["macd"] > metrics["macd_signal"], "text": "Positive MACD vs signal"})
    checklist.append({"ok": 40 <= metrics["rsi14"] <= 65, "text": "RSI in a moderate band"})
    checklist.append({"ok": metrics["rsi14"] <= 75, "text": "RSI is not elevated (>75)"})
    checklist.append({"ok": metrics["momentum"] > 0, "text": "Positive 10-day momentum"})
    checklist.append({"ok": news["score"] > 0, "text": "News sentiment is positive"})
    checklist.append({"ok": metrics["volume_trend"] >= -5, "text": "Volume not collapsing vs average"})

    return {
        "ticker": ticker,
        "name": name,
        "metrics": metrics,
        "technical_points": tech_pts,
        "technical_label": "BUY" if tech_pts >= int(settings.get("tech_score_buy", 4)) else ("SELL" if tech_pts <= 0 else "HOLD"),
        "technical_reasons": tech_reasons,
        "news": news,
        "articles": articles[:6],
        "overall": overall,
        "signal": signal,
        "strength": strength_for(overall, signal),
        "confidence": confidence,
        "factors": factors,
        "checklist": checklist,
        "disclaimer": (
            "Educational signal from live market data and rule-based scoring. "
            "Not financial advice. News reasons are best-effort correlations, not guaranteed causes."
        ),
    }
