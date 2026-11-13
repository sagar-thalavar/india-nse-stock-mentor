"""Market data layer.

Uses live India NSE data (yfinance) by default, with local sample fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

import pandas as pd

from modules.paths import load_json
from modules.sample_prices import ensure_sample_prices

PROVIDER_KIND = "india_live"


@dataclass
class StockMeta:
    ticker: str
    name: str
    sector: str
    listed_price: float


class LocalMarketDataProvider:
    """Reads fictional OHLCV and company metadata from disk.

    FUTURE: Replace LocalMarketDataProvider with NSE/BSE/other market data provider.
    """

    def __init__(self) -> None:
        self._stocks = load_json("stocks.json", [])
        self._prices: pd.DataFrame | None = None

    def list_stocks(self) -> list[StockMeta]:
        out: list[StockMeta] = []
        for row in self._stocks:
            out.append(
                StockMeta(
                    ticker=row["ticker"],
                    name=row["name"],
                    sector=row.get("sector", ""),
                    listed_price=float(row.get("current_price", 0)),
                )
            )
        return out

    def name_for(self, ticker: str) -> str:
        for s in self.list_stocks():
            if s.ticker == ticker:
                return s.name
        return ticker

    def ticker_for_name(self, name: str) -> str:
        for s in self.list_stocks():
            if s.name == name:
                return s.ticker
        return name

    def prices(self) -> pd.DataFrame:
        if self._prices is None:
            path = ensure_sample_prices()
            df = pd.read_csv(path, parse_dates=["date"])
            df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
            self._prices = df
        return self._prices.copy()

    def history(self, ticker: str) -> pd.DataFrame:
        df = self.prices()
        return df[df["ticker"] == ticker].copy().reset_index(drop=True)

    def latest_bar(self, ticker: str) -> dict:
        hist = self.history(ticker)
        if hist.empty:
            return {}
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else last
        return {
            "date": last["date"],
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "volume": int(last["volume"]),
            "prev_close": float(prev["close"]),
        }

    def snapshot(self, ticker: str) -> dict:
        hist = self.history(ticker)
        if hist.empty:
            return {}
        last = hist.iloc[-1]
        close = float(last["close"])
        prev = float(hist.iloc[-2]["close"]) if len(hist) > 1 else close

        def pct_change(days: int) -> float | None:
            if len(hist) <= days:
                return None
            older = float(hist.iloc[-(days + 1)]["close"])
            if older == 0:
                return None
            return (close - older) / older * 100.0

        week_high = float(hist["high"].max())
        week_low = float(hist["low"].min())
        meta = next((s for s in self.list_stocks() if s.ticker == ticker), None)
        daily = close - prev
        daily_pct = (daily / prev * 100.0) if prev else 0.0
        return {
            "ticker": ticker,
            "name": meta.name if meta else ticker,
            "sector": meta.sector if meta else "",
            "current_price": close,
            "previous_close": prev,
            "daily_change": daily,
            "daily_change_pct": daily_pct,
            "week_change_pct": pct_change(5),
            "month_change_pct": pct_change(21),
            "three_month_change_pct": pct_change(63),
            "volume": int(last["volume"]),
            "week_52_high": week_high,
            "week_52_low": week_low,
            "as_of": str(pd.Timestamp(last["date"]).date()),
        }

    def slice_range(self, ticker: str, period: str) -> pd.DataFrame:
        hist = self.history(ticker)
        mapping = {"1D": 2, "1W": 6, "1M": 22, "3M": 66, "6M": 132, "1Y": 252}
        n = mapping.get(period, 66)
        return hist.tail(max(n, 2)).copy()


def get_market_provider():
    """Prefer live NSE data; set MARKET_PROVIDER=local to force sample data."""
    mode = (os.getenv("MARKET_PROVIDER") or "live").strip().lower()
    if mode in {"local", "sample", "demo"}:
        return LocalMarketDataProvider()
    try:
        from modules.live_market import IndiaMarketDataProvider

        return IndiaMarketDataProvider()
    except Exception:
        return LocalMarketDataProvider()
