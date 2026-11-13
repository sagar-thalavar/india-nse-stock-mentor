"""Simulated portfolio and paper orders.

FUTURE:
Replace SimulatedBroker with RealBrokerAdapter.
This module must NEVER place a real trade.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.paths import load_json, load_settings, save_json

BROKER_KIND = "simulated"


class SimulatedBroker:
    """Local JSON portfolio. Demo only — no real money or broker account is connected.

    FUTURE: Replace SimulatedBroker with RealBrokerAdapter.
    """

    def __init__(self) -> None:
        self._ensure()

    def _ensure(self) -> None:
        data = load_json("portfolio.json", None)
        if not data:
            settings = load_settings()
            data = {
                "cash": float(settings.get("initial_cash", 1_000_000)),
                "holdings": {},
                "demo_only": True,
                "disclaimer": "SIMULATED PORTFOLIO — no real money or broker account is connected.",
            }
            save_json("portfolio.json", data)

    def load(self) -> dict:
        self._ensure()
        return load_json("portfolio.json")

    def save(self, data: dict) -> None:
        data["demo_only"] = True
        save_json("portfolio.json", data)

    def transactions(self) -> list[dict]:
        return load_json("transactions.json", [])

    def preview_order(self, side: str, ticker: str, name: str, qty: int, price: float) -> dict:
        qty = int(qty)
        total = round(qty * price, 2)
        return {
            "label": "SIMULATED ORDER",
            "warning": "Demo only — no real money or broker account is connected.",
            "side": side.upper(),
            "ticker": ticker,
            "name": name,
            "quantity": qty,
            "price": price,
            "total": total,
        }

    def execute(
        self,
        side: str,
        ticker: str,
        name: str,
        qty: int,
        price: float,
        signal: str | None = None,
        score: float | None = None,
    ) -> dict:
        """Paper fill only. Never sends an order anywhere."""
        side = side.upper()
        qty = int(qty)
        if qty <= 0:
            return {"ok": False, "error": "Quantity must be positive."}
        data = self.load()
        cash = float(data.get("cash", 0))
        holdings: dict[str, Any] = data.get("holdings") or {}
        pos = holdings.get(ticker) or {"ticker": ticker, "name": name, "qty": 0, "avg_price": 0.0}
        total = round(qty * price, 2)

        if side == "BUY":
            if total > cash + 1e-6:
                return {"ok": False, "error": "Not enough simulated cash for this demo order."}
            new_qty = int(pos["qty"]) + qty
            invested = float(pos["avg_price"]) * int(pos["qty"]) + total
            pos["avg_price"] = round(invested / new_qty, 4) if new_qty else 0.0
            pos["qty"] = new_qty
            pos["name"] = name
            pos["ticker"] = ticker
            cash -= total
            holdings[ticker] = pos
        elif side == "SELL":
            if int(pos.get("qty", 0)) < qty:
                return {"ok": False, "error": "Not enough simulated shares to sell."}
            pos["qty"] = int(pos["qty"]) - qty
            cash += total
            if pos["qty"] <= 0:
                holdings.pop(ticker, None)
            else:
                holdings[ticker] = pos
        else:
            return {"ok": False, "error": "Side must be BUY or SELL."}

        data["cash"] = round(cash, 2)
        data["holdings"] = holdings
        self.save(data)

        tx = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stock": name,
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "price": price,
            "total": total,
            "signal": signal or "—",
            "score": score if score is not None else "—",
            "simulated": True,
            "note": "SIMULATED ORDER — demo only.",
        }
        history = self.transactions()
        history.insert(0, tx)
        save_json("transactions.json", history)
        return {"ok": True, "transaction": tx, "portfolio": data}

    def reset(self) -> None:
        settings = load_settings()
        self.save(
            {
                "cash": float(settings.get("initial_cash", 1_000_000)),
                "holdings": {},
                "demo_only": True,
                "disclaimer": "SIMULATED PORTFOLIO — no real money or broker account is connected.",
            }
        )
        save_json("transactions.json", [])


def get_broker() -> SimulatedBroker:
    # FUTURE: return RealBrokerAdapter() — must still require explicit live-trading consent.
    return SimulatedBroker()


def holdings_table(broker: SimulatedBroker, price_map: dict[str, float]) -> tuple[list[dict], dict]:
    data = broker.load()
    cash = float(data.get("cash", 0))
    rows = []
    invested = 0.0
    current = 0.0
    prev_value_proxy = 0.0
    for ticker, pos in (data.get("holdings") or {}).items():
        qty = int(pos.get("qty", 0))
        avg = float(pos.get("avg_price", 0))
        px = float(price_map.get(ticker, avg))
        inv = qty * avg
        cur = qty * px
        pnl = cur - inv
        pnl_pct = (pnl / inv * 100.0) if inv else 0.0
        invested += inv
        current += cur
        rows.append(
            {
                "ticker": ticker,
                "stock": pos.get("name", ticker),
                "quantity": qty,
                "average_price": avg,
                "current_demo_price": px,
                "invested_value": inv,
                "current_value": cur,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "weight": 0.0,
            }
        )
    equity = cash + current
    for r in rows:
        r["weight"] = (r["current_value"] / equity * 100.0) if equity else 0.0
    summary = {
        "cash": cash,
        "invested": invested,
        "holdings_value": current,
        "portfolio_value": equity,
        "holdings_count": len(rows),
    }
    return rows, summary
