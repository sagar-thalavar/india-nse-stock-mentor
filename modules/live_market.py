"""Live India NSE market data via yfinance.

Finnhub free tier typically blocks .NS quotes, so prices/history/names
come from Yahoo Finance symbols (RELIANCE.NS, TCS.NS, ...).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from modules.paths import load_json

# Default NSE watchlist used when stocks.json is empty / outdated.
DEFAULT_NSE_WATCHLIST = [
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "sector": "Technology"},
    {"ticker": "INFY.NS", "name": "Infosys", "sector": "Technology"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking"},
    {"ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"ticker": "ITC.NS", "name": "ITC", "sector": "FMCG"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"ticker": "WIPRO.NS", "name": "Wipro", "sector": "Technology"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank", "sector": "Banking"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki", "sector": "Automobile"},
]


@dataclass
class StockMeta:
    ticker: str
    name: str
    sector: str
    listed_price: float = 0.0


def _watchlist_rows() -> list[dict]:
    rows = load_json("stocks.json", [])
    live = [r for r in rows if str(r.get("ticker", "")).endswith(".NS")]
    return live or DEFAULT_NSE_WATCHLIST


class IndiaMarketDataProvider:
    """Real NSE prices and OHLCV history through yfinance."""

    def list_stocks(self) -> list[StockMeta]:
        out: list[StockMeta] = []
        for row in _watchlist_rows():
            out.append(
                StockMeta(
                    ticker=row["ticker"],
                    name=row.get("name") or row["ticker"],
                    sector=row.get("sector", ""),
                    listed_price=float(row.get("current_price") or 0),
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

    @lru_cache(maxsize=32)
    def _download(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf

        t = yf.Ticker(ticker)
        # 6mo is enough for SMA50/RSI and much faster than 1y on first load.
        hist = t.history(period="6mo", auto_adjust=False)
        if hist is None or hist.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "ticker"])
        df = hist.reset_index()
        # Column names vary slightly by yfinance version.
        rename = {}
        for col in df.columns:
            low = str(col).lower()
            if low.startswith("date") or low == "datetime" or "datetime" in low:
                rename[col] = "date"
            elif low == "open":
                rename[col] = "open"
            elif low == "high":
                rename[col] = "high"
            elif low == "low":
                rename[col] = "low"
            elif low == "close":
                rename[col] = "close"
            elif low == "volume":
                rename[col] = "volume"
        df = df.rename(columns=rename)
        keep = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[keep].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["ticker"] = ticker
        df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        return df

    def refresh_cache(self) -> None:
        self._download.cache_clear()

    def prices(self) -> pd.DataFrame:
        frames = [self._download(s.ticker) for s in self.list_stocks()]
        if not frames:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "ticker"])
        return pd.concat(frames, ignore_index=True)

    def history(self, ticker: str) -> pd.DataFrame:
        return self._download(ticker).copy()

    def _info(self, ticker: str) -> dict:
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
            return info if isinstance(info, dict) else {}
        except Exception:
            return {}

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
            "volume": int(last["volume"]) if pd.notna(last["volume"]) else 0,
            "prev_close": float(prev["close"]),
        }

    def snapshot(self, ticker: str) -> dict:
        # Use watchlist metadata only — yfinance `.info` is very slow and blocked the UI.
        hist = self.history(ticker)
        meta = next((s for s in self.list_stocks() if s.ticker == ticker), None)
        name = meta.name if meta else ticker
        sector = meta.sector if meta else ""
        if hist.empty:
            return {
                "ticker": ticker,
                "name": name,
                "sector": sector,
                "current_price": 0.0,
                "previous_close": 0.0,
                "daily_change": 0.0,
                "daily_change_pct": 0.0,
                "week_change_pct": None,
                "month_change_pct": None,
                "three_month_change_pct": None,
                "volume": 0,
                "week_52_high": 0.0,
                "week_52_low": 0.0,
                "as_of": None,
            }

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

        daily = close - prev
        daily_pct = (daily / prev * 100.0) if prev else 0.0
        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "current_price": close,
            "previous_close": prev,
            "daily_change": daily,
            "daily_change_pct": daily_pct,
            "week_change_pct": pct_change(5),
            "month_change_pct": pct_change(21),
            "three_month_change_pct": pct_change(63),
            "volume": int(last["volume"]) if pd.notna(last["volume"]) else 0,
            "week_52_high": float(hist["high"].max()),
            "week_52_low": float(hist["low"].min()),
            "as_of": str(pd.Timestamp(last["date"]).date()),
        }

    def slice_range(self, ticker: str, period: str) -> pd.DataFrame:
        hist = self.history(ticker)
        mapping = {"1D": 2, "1W": 6, "1M": 22, "3M": 66, "6M": 132, "1Y": 252}
        n = mapping.get(period, 66)
        return hist.tail(max(n, 2)).copy()
