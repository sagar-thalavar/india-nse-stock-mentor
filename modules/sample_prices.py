"""Deterministic fictional OHLCV. Shared by the generator script and first app launch."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from modules.paths import DATA

SEED = 42
TRADING_DAYS = 250
END_DATE = datetime(2026, 9, 28)

PROFILES = {
    "ABCT": {"start": 980.0, "drift": 0.00055, "vol": 0.015, "pattern": "uptrend"},
    "XYZB": {"start": 920.0, "drift": -0.00025, "vol": 0.012, "pattern": "downtrend"},
    "GLMO": {"start": 640.0, "drift": -0.00015, "vol": 0.018, "pattern": "volatile_down"},
    "GREN": {"start": 320.0, "drift": 0.00085, "vol": 0.022, "pattern": "uptrend"},
    "BHCN": {"start": 950.0, "drift": 0.00008, "vol": 0.009, "pattern": "sideways"},
    "PHCR": {"start": 1480.0, "drift": 0.00018, "vol": 0.016, "pattern": "sideways_vol"},
    "INRC": {"start": 360.0, "drift": -0.00035, "vol": 0.014, "pattern": "downtrend"},
    "CSYS": {"start": 1750.0, "drift": 0.00070, "vol": 0.020, "pattern": "uptrend"},
}


def trading_calendar(n: int, end: datetime) -> list[datetime]:
    days: list[datetime] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def generate_series(ticker: str, rng: np.random.Generator) -> pd.DataFrame:
    p = PROFILES[ticker]
    dates = trading_calendar(TRADING_DAYS, END_DATE)
    n = len(dates)
    noise = rng.normal(p["drift"], p["vol"], n)
    if p["pattern"] == "sideways":
        noise = rng.normal(0.0, p["vol"] * 0.7, n)
        noise += 0.004 * np.sin(np.linspace(0, 8 * np.pi, n))
    elif p["pattern"] == "volatile_down":
        shock = np.zeros(n)
        shock[80:95] = rng.normal(-0.012, 0.008, 15)
        shock[160:170] = rng.normal(0.01, 0.01, 10)
        noise = noise + shock
    elif p["pattern"] == "sideways_vol":
        noise = rng.normal(0.00005, p["vol"] * 1.15, n)

    rets = noise
    close = p["start"] * np.exp(np.cumsum(rets))
    close = np.maximum(close, 5.0)

    rows = []
    for i, dt in enumerate(dates):
        c = float(close[i])
        prev = float(close[i - 1]) if i else c
        intra = abs(rng.normal(0, p["vol"] * 0.6))
        o = prev * (1 + rng.normal(0, p["vol"] * 0.25))
        h = max(o, c) * (1 + intra)
        l = min(o, c) * (1 - intra)
        l = max(l, 1.0)
        base_vol = 800_000 + (sum(ord(ch) for ch in ticker) * 1000)
        vol_mult = 1.0 + abs(rets[i]) * 18
        if i > 0 and abs(c - prev) / prev > 0.03:
            vol_mult *= 1.6
        volume = int(max(50_000, rng.normal(base_vol * vol_mult, base_vol * 0.15)))
        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": volume,
            }
        )
    return pd.DataFrame(rows)


def write_prices_csv(path: Path | None = None) -> Path:
    path = path or (DATA / "prices.csv")
    rng = np.random.default_rng(SEED)
    frames = [generate_series(t, rng) for t in PROFILES]
    df = pd.concat(frames, ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def ensure_sample_prices() -> Path:
    path = DATA / "prices.csv"
    if not path.exists() or path.stat().st_size < 100:
        write_prices_csv(path)
    return path
