"""Shared paths and JSON helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_json(name: str, default: Any = None) -> Any:
    path = DATA / name
    if not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(name: str, payload: Any) -> None:
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_settings() -> dict:
    defaults = {
        "initial_cash": 1_000_000,
        "buy_threshold": 70,
        "hold_low": 45,
        "sell_threshold": 44,
        "technical_weight": 0.50,
        "momentum_weight": 0.20,
        "news_weight": 0.20,
        "volume_weight": 0.10,
        "tech_score_buy": 4,
        "tech_score_hold_low": 1,
        "alert_percentage": 2.0,
        "theme": "light",
        "watchlist": ["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        "price_alerts": {},
    }
    stored = load_json("settings.json", {})
    defaults.update(stored or {})
    return defaults


def save_settings(settings: dict) -> None:
    save_json("settings.json", settings)
