"""Neon Postgres persistence for stocks, prices, news, and signals."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from modules.config import get_database_url

_SCHEMA_READY = False


@contextmanager
def connection() -> Iterator[Any]:
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    import psycopg

    conn = psycopg.connect(url, connect_timeout=15)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_configured() -> bool:
    return bool(get_database_url())


def ensure_schema() -> bool:
    """Create tables if missing. Returns False when DB is not configured."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True
    if not db_configured():
        return False
    statements = [
        """
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sector TEXT,
            exchange TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id BIGSERIAL PRIMARY KEY,
            ticker TEXT NOT NULL REFERENCES stocks(ticker) ON DELETE CASCADE,
            price DOUBLE PRECISION NOT NULL,
            previous_close DOUBLE PRECISION,
            daily_change DOUBLE PRECISION,
            daily_change_pct DOUBLE PRECISION,
            volume BIGINT,
            as_of DATE,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_price_snapshots_ticker_time
            ON price_snapshots (ticker, captured_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS news_articles (
            id BIGSERIAL PRIMARY KEY,
            ticker TEXT NOT NULL REFERENCES stocks(ticker) ON DELETE CASCADE,
            headline TEXT NOT NULL,
            summary TEXT,
            source TEXT,
            url TEXT,
            article_date DATE,
            sentiment TEXT,
            importance TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (ticker, headline, article_date)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_news_articles_ticker_date
            ON news_articles (ticker, article_date DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS signals (
            id BIGSERIAL PRIMARY KEY,
            ticker TEXT NOT NULL REFERENCES stocks(ticker) ON DELETE CASCADE,
            signal TEXT NOT NULL,
            overall_score DOUBLE PRECISION,
            direction TEXT,
            daily_change_pct DOUBLE PRECISION,
            news_label TEXT,
            news_score DOUBLE PRECISION,
            explanation TEXT,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_signals_ticker_time
            ON signals (ticker, captured_at DESC)
        """,
    ]
    import psycopg

    with connection() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                try:
                    cur.execute(sql)
                    conn.commit()
                except psycopg.errors.UniqueViolation:
                    # Neon can surface transient catalog races; retry next statement.
                    conn.rollback()
                except psycopg.Error:
                    conn.rollback()
                    raise
    _SCHEMA_READY = True
    return True


def upsert_stock(ticker: str, name: str, sector: str = "", exchange: str = "NSE") -> None:
    if not ensure_schema():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stocks (ticker, name, sector, exchange, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector,
                    exchange = EXCLUDED.exchange,
                    updated_at = NOW()
                """,
                (ticker, name, sector or None, exchange or None),
            )


def save_price_snapshot(ticker: str, snap: dict) -> None:
    if not ensure_schema():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO price_snapshots (
                    ticker, price, previous_close, daily_change, daily_change_pct,
                    volume, as_of, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    ticker,
                    float(snap.get("current_price") or 0),
                    snap.get("previous_close"),
                    snap.get("daily_change"),
                    snap.get("daily_change_pct"),
                    snap.get("volume"),
                    snap.get("as_of"),
                ),
            )


def save_news_articles(ticker: str, articles: list[dict]) -> None:
    if not ensure_schema() or not articles:
        return
    with connection() as conn:
        with conn.cursor() as cur:
            for a in articles:
                cur.execute(
                    """
                    INSERT INTO news_articles (
                        ticker, headline, summary, source, url,
                        article_date, sentiment, importance, fetched_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (ticker, headline, article_date) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        source = EXCLUDED.source,
                        url = EXCLUDED.url,
                        sentiment = EXCLUDED.sentiment,
                        importance = EXCLUDED.importance,
                        fetched_at = NOW()
                    """,
                    (
                        ticker,
                        a.get("headline") or "",
                        a.get("summary"),
                        a.get("source"),
                        a.get("url"),
                        a.get("date"),
                        a.get("sentiment"),
                        a.get("importance"),
                    ),
                )


def save_signal(ticker: str, analysis: dict, direction: str) -> None:
    if not ensure_schema():
        return
    news = analysis.get("news") or {}
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signals (
                    ticker, signal, overall_score, direction, daily_change_pct,
                    news_label, news_score, explanation, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    ticker,
                    analysis.get("signal"),
                    analysis.get("overall"),
                    direction,
                    (analysis.get("snapshot") or {}).get("daily_change_pct"),
                    news.get("label"),
                    news.get("score"),
                    (news.get("explanation") or "")[:2000],
                ),
            )


def persist_analysis(analysis: dict) -> None:
    """Best-effort write of stock metadata, price, news, and signal."""
    if not db_configured():
        return
    try:
        ticker = analysis["ticker"]
        name = analysis.get("name") or ticker
        snap = analysis.get("snapshot") or {}
        upsert_stock(ticker, name, sector=str(snap.get("sector") or ""), exchange="NSE")
        if snap:
            save_price_snapshot(ticker, snap)
        save_news_articles(ticker, analysis.get("articles") or [])
        pct = float(snap.get("daily_change_pct") or 0)
        direction = "UP" if pct > 0.05 else ("DOWN" if pct < -0.05 else "FLAT")
        save_signal(ticker, analysis, direction)
    except Exception:
        # Demo app should keep running even if DB write fails.
        return


def db_status() -> dict:
    """Safe status for UI — never includes credentials."""
    if not db_configured():
        return {"ok": False, "message": "DATABASE_URL not set"}
    try:
        ensure_schema()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM stocks")
                stocks = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM price_snapshots")
                prices = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM news_articles")
                news = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM signals")
                signals = cur.fetchone()[0]
        return {
            "ok": True,
            "message": "Connected to Neon",
            "stocks": stocks,
            "prices": prices,
            "news": news,
            "signals": signals,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {"ok": False, "message": f"DB error: {type(exc).__name__}"}
