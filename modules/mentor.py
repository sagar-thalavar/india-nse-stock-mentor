"""Rule-based mentor copy for live NSE analysis."""
from __future__ import annotations


class RuleBasedMentor:
    """Plain-language explanation: direction + likely why."""

    def generate_explanation(self, analysis: dict) -> str:
        name = analysis["name"]
        signal = analysis["signal"]
        m = analysis["metrics"]
        news = analysis["news"]
        overall = analysis["overall"]
        snap = analysis.get("snapshot") or {}
        pct = float(snap.get("daily_change_pct") or 0)
        if pct > 0.05:
            direction = "UP"
        elif pct < -0.05:
            direction = "DOWN"
        else:
            direction = "FLAT"

        lines = [
            f"{name} is {direction} today ({pct:+.2f}%).",
            f"Model signal: {signal} (score {overall:.0f}/100).",
            "",
            "Why (best effort):",
        ]

        articles = analysis.get("articles") or []
        if articles:
            lines.append("Recent headlines linked to this stock:")
            for a in articles[:3]:
                lines.append(f"- {a.get('headline')}")
            lines.append(
                f"News tone looks {news['label'].lower()} "
                f"(score {news['score']:+.2f} from {news['count']} articles)."
            )
        else:
            lines.append("No fresh headlines were available; using price/technical context only.")

        if m["price_gt_sma20"]:
            lines.append("Price is above its 20-day average.")
        else:
            lines.append("Price is below its 20-day average.")
        if m["sma20_gt_sma50"]:
            lines.append("Short-term trend (SMA20) is above the medium trend (SMA50).")
        else:
            lines.append("Short-term trend is not above the medium trend.")
        if m["momentum"] > 0:
            lines.append("10-day momentum is positive.")
        else:
            lines.append("10-day momentum is negative.")

        lines += [
            "",
            "Note: this is an educational read of price + news + indicators — "
            "not a guaranteed reason the market moved.",
        ]
        return "\n".join(lines)


def get_mentor() -> RuleBasedMentor:
    return RuleBasedMentor()
