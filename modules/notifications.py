"""In-app alerts stored in data/notifications.json.

FUTURE:
Add email notifications, WhatsApp/Telegram notifications, and mobile push
without changing the create_alert() contract.
"""
from __future__ import annotations

from datetime import datetime

from modules.paths import load_json, save_json


def load_alerts() -> list[dict]:
    return load_json("notifications.json", [])


def save_alerts(items: list[dict]) -> None:
    save_json("notifications.json", items)


def unread_count(items: list[dict] | None = None) -> int:
    items = items if items is not None else load_alerts()
    return sum(1 for a in items if not a.get("read"))


def mark_all_read() -> None:
    items = load_alerts()
    for a in items:
        a["read"] = True
    save_alerts(items)


def create_alert(message: str, kind: str = "info", ticker: str | None = None) -> dict:
    items = load_alerts()
    alert = {
        "id": (max((a.get("id", 0) for a in items), default=0) + 1),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "kind": kind,
        "ticker": ticker,
        "read": False,
    }
    items.insert(0, alert)
    save_alerts(items[:200])
    return alert


def load_signal_history() -> dict:
    return load_json("signal_history.json", {})


def save_signal_history(hist: dict) -> None:
    save_json("signal_history.json", hist)


def evaluate_rules(
    signals: dict[str, str],
    names: dict[str, str],
    portfolio_change_pct: float | None,
    settings: dict,
    price_map: dict[str, float],
) -> list[dict]:
    """Compare latest demo signals to last run and emit local alerts."""
    new_alerts: list[dict] = []
    hist = load_signal_history()
    prev_signals = hist.get("signals") or {}

    for ticker, sig in signals.items():
        old = prev_signals.get(ticker)
        name = names.get(ticker, ticker)
        if old and old != sig:
            msg = f"🔔 {name} has changed from {old} to {sig}."
            new_alerts.append(create_alert(msg, kind="signal", ticker=ticker))
        elif not old and sig == "SELL":
            new_alerts.append(
                create_alert(f"🔔 {name} has triggered a SELL demo signal.", kind="signal", ticker=ticker)
            )
        elif not old and sig == "BUY":
            new_alerts.append(
                create_alert(f"🔔 {name} has a BUY-style demo signal.", kind="signal", ticker=ticker)
            )

    alert_pct = float(settings.get("alert_percentage", 2.0))
    if portfolio_change_pct is not None and portfolio_change_pct <= -alert_pct:
        already = any("fallen" in a.get("message", "") and a.get("timestamp", "")[:10] == datetime.now().strftime("%Y-%m-%d") for a in load_alerts())
        if not already:
            new_alerts.append(
                create_alert(
                    f"🔔 Your simulated portfolio has fallen {abs(portfolio_change_pct):.2f}% today (demo P&L vs prior closes).",
                    kind="portfolio",
                )
            )

    price_alerts = settings.get("price_alerts") or {}
    triggered = set(hist.get("price_alerts_fired") or [])
    still_triggered: list[str] = []
    for ticker, level in price_alerts.items():
        try:
            level_f = float(level)
        except (TypeError, ValueError):
            continue
        px = price_map.get(ticker)
        if px is None:
            continue
        key = f"{ticker}:{level_f}"
        name = names.get(ticker, ticker)
        if px >= level_f:
            still_triggered.append(key)
            if key not in triggered:
                new_alerts.append(
                    create_alert(
                        f"🔔 {name} has reached your configured alert price of ₹{level_f:,.2f} (demo price ₹{px:,.2f}).",
                        kind="price",
                        ticker=ticker,
                    )
                )
    hist["signals"] = signals
    hist["price_alerts_fired"] = still_triggered
    save_signal_history(hist)
    return new_alerts
