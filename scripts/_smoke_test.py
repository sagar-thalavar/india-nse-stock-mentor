"""Local smoke test — prints status only, never secrets."""
from __future__ import annotations

from modules.config import get_database_url, get_finnhub_api_key, load_env
from modules.db import (
    db_status,
    ensure_schema,
    persist_analysis,
    save_news_articles,
    save_price_snapshot,
    upsert_stock,
)
from modules.live_market import IndiaMarketDataProvider
from modules.live_news import LiveNewsProvider
from modules.news_analysis import get_news_provider
from modules.paths import load_settings
from modules.signal_engine import analyze_stock


def main() -> None:
    load_env()
    print("DB_SET", bool(get_database_url()))
    print("FH_SET", bool(get_finnhub_api_key()))

    with __import__("modules.db", fromlist=["connection"]).connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY 1"
            )
            print("TABLES_BEFORE", [r[0] for r in cur.fetchall()])

    print("SCHEMA", ensure_schema())
    print("STATUS", db_status())

    market = IndiaMarketDataProvider()
    stocks = market.list_stocks()
    print("WATCH", len(stocks), stocks[0].ticker)
    snap = market.snapshot("RELIANCE.NS")
    hist = market.history("RELIANCE.NS")
    print("HIST_ROWS", len(hist))
    print("SNAP_NAME", snap.get("name"))
    print("SNAP_PX", round(float(snap.get("current_price") or 0), 2))
    print("SNAP_PCT", round(float(snap.get("daily_change_pct") or 0), 2))

    upsert_stock(snap["ticker"], snap["name"], snap.get("sector") or "", "NSE")
    save_price_snapshot(snap["ticker"], snap)

    news = LiveNewsProvider()
    arts = news.for_ticker("RELIANCE.NS", snap.get("name"))
    print("NEWS_COUNT", len(arts))
    if arts:
        print("NEWS_HEAD", (arts[0].get("headline") or "")[:80])
        save_news_articles("RELIANCE.NS", arts[:5])

    settings = load_settings()
    analysis = analyze_stock(
        "RELIANCE.NS",
        snap.get("name") or "RELIANCE.NS",
        hist,
        settings,
        get_news_provider(),
    )
    analysis["snapshot"] = snap
    persist_analysis(analysis)
    print("SIGNAL", analysis.get("signal"), analysis.get("overall"))
    print("STATUS2", db_status())


if __name__ == "__main__":
    main()
