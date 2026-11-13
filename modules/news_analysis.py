"""News sentiment scoring + providers.

LiveNewsProvider is preferred; LocalNewsProvider remains as offline fallback.
Keep score_news() contract so the signal engine stays unchanged.
"""
from __future__ import annotations

import os

from modules.paths import load_json

SENTIMENT_VALUE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
IMPORTANCE_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.5}


class LocalNewsProvider:
    """Reads articles from data/news.json (offline/demo fallback)."""

    def __init__(self) -> None:
        self.articles = load_json("news.json", [])

    def for_ticker(self, ticker: str, name: str | None = None) -> list[dict]:
        rows = []
        for a in self.articles:
            if a.get("ticker") == ticker or (name and a.get("stock") == name):
                rows.append(a)
        rows.sort(key=lambda x: x.get("date", ""), reverse=True)
        return rows

    def latest(self, n: int = 8) -> list[dict]:
        return sorted(self.articles, key=lambda x: x.get("date", ""), reverse=True)[:n]


def get_news_provider():
    mode = (os.getenv("NEWS_PROVIDER") or "live").strip().lower()
    if mode in {"local", "sample", "demo"}:
        return LocalNewsProvider()
    try:
        from modules.live_news import LiveNewsProvider

        return LiveNewsProvider()
    except Exception:
        return LocalNewsProvider()


def score_news(articles: list[dict]) -> dict:
    """Weighted average of article sentiment labels. Not a language model."""
    if not articles:
        return {
            "score": 0.0,
            "label": "Neutral",
            "count": 0,
            "explanation": "No recent news articles were found for this ticker.",
        }
    num = 0.0
    den = 0.0
    for a in articles:
        s = SENTIMENT_VALUE.get(str(a.get("sentiment", "neutral")).lower(), 0.0)
        w = IMPORTANCE_WEIGHT.get(str(a.get("importance", "medium")).lower(), 1.0)
        num += s * w
        den += w
    raw = num / den if den else 0.0
    if raw > 0.15:
        label = "Positive"
    elif raw < -0.15:
        label = "Negative"
    else:
        label = "Neutral"
    top = articles[0].get("headline") if articles else ""
    explanation = (
        f"Recent news lean {label.lower()} "
        f"({len(articles)} articles). "
        + (f"Latest headline: {top}" if top else "")
    )
    return {
        "score": round(raw, 2),
        "label": label,
        "count": len(articles),
        "explanation": explanation,
    }
