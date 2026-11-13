"""Live news for NSE tickers.

Tries Finnhub company-news first (often limited for .NS on free plans),
then falls back to yfinance news for the same symbol.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from modules.config import get_finnhub_api_key
from modules.paths import load_json

POSITIVE = (
    "surge", "rally", "gain", "profit", "growth", "upgrade", "record", "strong",
    "beat", "rise", "up", "positive", "wins", "order", "deal", "expand",
)
NEGATIVE = (
    "fall", "drop", "loss", "weak", "downgrade", "cut", "miss", "decline",
    "down", "negative", "probe", "fraud", "slump", "crash", "warning", "fine",
)


def _guess_sentiment(text: str) -> str:
    t = (text or "").lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _importance_from_source(source: str) -> str:
    s = (source or "").lower()
    if any(x in s for x in ("reuters", "bloomberg", "moneycontrol", "economic times", "mint")):
        return "high"
    return "medium"


class LiveNewsProvider:
    """Fetches real headlines for a ticker; keeps LocalNewsProvider-compatible API."""

    def __init__(self) -> None:
        self._cache: dict[str, list[dict]] = {}

    def for_ticker(self, ticker: str, name: str | None = None) -> list[dict]:
        key = f"{ticker}|{name or ''}"
        if key in self._cache:
            return list(self._cache[key])
        articles = self._finnhub_news(ticker)
        if not articles:
            articles = self._yfinance_news(ticker, name)
        if not articles and name:
            # Last resort: reuse any local sample rows if present (dev fallback).
            for a in load_json("news.json", []) or []:
                if a.get("ticker") == ticker or a.get("stock") == name:
                    articles.append(a)
        articles = sorted(articles, key=lambda x: x.get("date", ""), reverse=True)
        self._cache[key] = articles
        return list(articles)

    def latest(self, n: int = 8) -> list[dict]:
        from modules.live_market import IndiaMarketDataProvider

        all_rows: list[dict] = []
        market = IndiaMarketDataProvider()
        for s in market.list_stocks():
            all_rows.extend(self.for_ticker(s.ticker, s.name)[:3])
        all_rows.sort(key=lambda x: x.get("date", ""), reverse=True)
        return all_rows[:n]

    def _finnhub_news(self, ticker: str) -> list[dict]:
        key = get_finnhub_api_key()
        if not key:
            return []
        # Try NSE form and bare symbol.
        candidates = [ticker]
        if ticker.endswith(".NS"):
            candidates.append(ticker.replace(".NS", ""))
        end = date.today()
        start = end - timedelta(days=14)
        out: list[dict] = []
        for symbol in candidates:
            try:
                resp = requests.get(
                    "https://finnhub.io/api/v1/company-news",
                    params={
                        "symbol": symbol,
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                    },
                    headers={"X-Finnhub-Token": key},
                    timeout=8,
                )
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                if not isinstance(payload, list) or not payload:
                    continue
                for item in payload[:12]:
                    headline = (item.get("headline") or "").strip()
                    if not headline:
                        continue
                    ts = item.get("datetime")
                    if ts:
                        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
                    else:
                        d = end.isoformat()
                    summary = (item.get("summary") or "").strip()
                    source = item.get("source") or "Finnhub"
                    out.append(
                        {
                            "date": d,
                            "stock": ticker,
                            "ticker": ticker,
                            "headline": headline,
                            "summary": summary[:400],
                            "source": source,
                            "url": item.get("url"),
                            "sentiment": _guess_sentiment(f"{headline} {summary}"),
                            "importance": _importance_from_source(source),
                        }
                    )
                if out:
                    break
            except Exception:
                continue
        return out

    def _yfinance_news(self, ticker: str, name: str | None = None) -> list[dict]:
        try:
            import yfinance as yf

            t = yf.Ticker(ticker)
            raw = getattr(t, "news", None) or []
        except Exception:
            return []
        out: list[dict] = []
        for item in raw[:12]:
            # yfinance news shape differs by version.
            content = item.get("content") if isinstance(item.get("content"), dict) else None
            if content:
                headline = (content.get("title") or "").strip()
                summary = (content.get("summary") or content.get("description") or "").strip()
                publisher = ((content.get("provider") or {}) if isinstance(content.get("provider"), dict) else {})
                source = publisher.get("displayName") or "Yahoo Finance"
                url = None
                click = content.get("clickThroughUrl") or content.get("canonicalUrl") or {}
                if isinstance(click, dict):
                    url = click.get("url")
                pub = content.get("pubDate") or content.get("displayTime")
                d = _parse_date(pub)
            else:
                headline = (item.get("title") or "").strip()
                summary = ""
                source = (item.get("publisher") or "Yahoo Finance")
                url = item.get("link")
                d = _parse_date(item.get("providerPublishTime"))
            if not headline:
                continue
            out.append(
                {
                    "date": d,
                    "stock": name or ticker,
                    "ticker": ticker,
                    "headline": headline,
                    "summary": summary[:400],
                    "source": source,
                    "url": url,
                    "sentiment": _guess_sentiment(f"{headline} {summary}"),
                    "importance": _importance_from_source(source),
                }
            )
        return out


def _parse_date(value: Any) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        except Exception:
            return date.today().isoformat()
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return text[:10] if len(text) >= 10 else date.today().isoformat()
