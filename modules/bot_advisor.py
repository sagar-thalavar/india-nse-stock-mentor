"""Interactive stock chat bot.

Free chatbot / LLM APIs (pick one key in .env):
  - GROQ_API_KEY      → https://console.groq.com  (easiest, fast, no card)
  - GEMINI_API_KEY    → https://aistudio.google.com (Google free tier)

Market facts still come from Finnhub + Yahoo Finance.
If no LLM key is set, a lively rule-based coach replies instead.
"""
from __future__ import annotations

import re
from typing import Any

import requests

from modules.config import get_finnhub_api_key, get_gemini_api_key, get_groq_api_key
from modules.live_market import IndiaMarketDataProvider
from modules.live_news import LiveNewsProvider
from modules.mentor import get_mentor
from modules.news_analysis import score_news
from modules.paths import load_settings
from modules.signal_engine import analyze_stock

TICKER_ALIASES = {
    "reliance": "RELIANCE.NS",
    "ril": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "tata consultancy": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "airtel": "BHARTIARTL.NS",
    "bharti": "BHARTIARTL.NS",
    "itc": "ITC.NS",
}

SYSTEM_PROMPT = """You are "NSE Coach", a friendly educational stock chat bot for Indian NSE stocks.
Be conversational, warm, and clear — like a helpful coach, not a stiff report.
Use short paragraphs and bullets when useful.
Always ground answers in the MARKET CONTEXT provided (price, direction, news, signals).
Never invent prices or headlines that are not in the context.
Always end with: "Educational only — not financial advice."
If the user asks something off-topic, gently steer back to stocks/news.
Suggest 1-2 short follow-up questions at the end.
"""


def active_llm_provider() -> str:
    if get_groq_api_key():
        return "groq"
    if get_gemini_api_key():
        return "gemini"
    return "rules"


def resolve_ticker(text: str, watchlist: list[str] | None = None) -> str | None:
    t = (text or "").strip().upper()
    m = re.search(r"\b([A-Z]{2,15}(?:\.NS)?)\b", t)
    if m:
        sym = m.group(1)
        if watchlist and sym in watchlist:
            return sym
        if watchlist and f"{sym}.NS" in watchlist:
            return f"{sym}.NS"
        if sym.endswith(".NS"):
            return sym

    low = (text or "").lower()
    for alias, ticker in TICKER_ALIASES.items():
        if alias in low:
            return ticker

    if watchlist:
        for w in watchlist:
            base = w.replace(".NS", "").lower()
            if base and base in low:
                return w
    return None


def finnhub_market_news(limit: int = 6) -> list[dict]:
    key = get_finnhub_api_key()
    if not key:
        return []
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general"},
            headers={"X-Finnhub-Token": key},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        out = []
        for item in rows[:limit]:
            headline = item.get("headline") or ""
            if not headline:
                continue
            out.append(
                {
                    "headline": headline,
                    "source": item.get("source") or "Finnhub",
                    "url": item.get("url"),
                    "summary": (item.get("summary") or "")[:240],
                }
            )
        return out
    except Exception:
        return []


def finnhub_recommendation(symbol: str) -> dict | None:
    key = get_finnhub_api_key()
    if not key:
        return None
    candidates = [symbol]
    if symbol.endswith(".NS"):
        candidates.append(symbol.replace(".NS", ""))
    for sym in candidates:
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": sym},
                headers={"X-Finnhub-Token": key},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            rows = resp.json()
            if isinstance(rows, list) and rows:
                latest = rows[0]
                return {
                    "symbol": sym,
                    "period": latest.get("period"),
                    "strongBuy": latest.get("strongBuy", 0),
                    "buy": latest.get("buy", 0),
                    "hold": latest.get("hold", 0),
                    "sell": latest.get("sell", 0),
                    "strongSell": latest.get("strongSell", 0),
                }
        except Exception:
            continue
    return None


def _recommendation_label(rec: dict) -> str:
    scores = {
        "Strong Buy": rec.get("strongBuy", 0),
        "Buy": rec.get("buy", 0),
        "Hold": rec.get("hold", 0),
        "Sell": rec.get("sell", 0),
        "Strong Sell": rec.get("strongSell", 0),
    }
    return max(scores, key=scores.get)


def gather_context(message: str, analyses: dict | None = None) -> dict[str, Any]:
    analyses = analyses or {}
    watchlist = list(analyses.keys()) or [s.ticker for s in IndiaMarketDataProvider().list_stocks()]
    ticker = resolve_ticker(message, watchlist)
    market_news = finnhub_market_news(5)

    if not ticker:
        return {
            "ticker": None,
            "context_text": (
                "No specific NSE ticker matched.\n"
                "Watchlist: " + ", ".join(watchlist) + "\n"
                "General market headlines:\n"
                + "\n".join(f"- {h['headline']} ({h['source']})" for h in market_news)
                or "- none"
            ),
            "articles": market_news,
            "recommendation": None,
            "direction": None,
            "signal": None,
            "sources": ["Finnhub /news"],
            "fallback_reply": _fallback_no_ticker(market_news, watchlist),
            "followups": [
                "How is RELIANCE.NS today?",
                "News on TCS",
                "Compare INFY vs TCS briefly",
            ],
        }

    a = analyses.get(ticker)
    if not a:
        market = IndiaMarketDataProvider()
        hist = market.history(ticker)
        snap = market.snapshot(ticker)
        news_p = LiveNewsProvider()
        a = analyze_stock(ticker, snap.get("name") or ticker, hist, load_settings(), news_p)
        a["snapshot"] = snap
        a["articles"] = news_p.for_ticker(ticker, snap.get("name"))[:6]
        a["name"] = snap.get("name") or ticker

    snap = a.get("snapshot") or {}
    pct = float(snap.get("daily_change_pct") or 0)
    direction = "UP" if pct > 0.05 else ("DOWN" if pct < -0.05 else "FLAT")
    articles = a.get("articles") or LiveNewsProvider().for_ticker(ticker, a.get("name"))
    news = a.get("news") or score_news(articles)
    mentor = get_mentor().generate_explanation(a)
    fh_rec = finnhub_recommendation(ticker)
    sources = ["Yahoo Finance (price)", "Finnhub/yfinance (news)", "local signal engine"]

    rec_line = "Finnhub analyst trend: unavailable for this symbol on free tier."
    if fh_rec:
        rec_line = (
            f"Finnhub analyst trend ({fh_rec.get('period')}): {_recommendation_label(fh_rec)} "
            f"(SB {fh_rec.get('strongBuy')}/B {fh_rec.get('buy')}/H {fh_rec.get('hold')}/"
            f"S {fh_rec.get('sell')}/SS {fh_rec.get('strongSell')})"
        )
        sources.append("Finnhub /stock/recommendation")

    headlines = "\n".join(
        f"- {art.get('date')}: {art.get('headline')} [{art.get('sentiment')}]"
        for art in (articles or [])[:5]
    ) or "- none"

    context_text = f"""
STOCK: {a.get('name')} ({ticker})
PRICE: ₹{float(snap.get('current_price') or 0):,.2f}
TODAY_MOVE: {direction} ({pct:+.2f}%)
APP_SIGNAL: {a.get('signal')} (score {float(a.get('overall') or 0):.0f}/100)
NEWS_TONE: {news.get('label')} ({news.get('score'):+.2f})
{rec_line}
HEADLINES:
{headlines}
RULE_BASED_WHY:
{mentor}
GENERAL_MARKET_HEADLINES:
{chr(10).join(f"- {h['headline']}" for h in market_news) or "- none"}
""".strip()

    return {
        "ticker": ticker,
        "context_text": context_text,
        "articles": articles[:6],
        "recommendation": fh_rec,
        "direction": direction,
        "signal": a.get("signal"),
        "sources": sources,
        "fallback_reply": _fallback_ticker(a, direction, pct, news, articles, fh_rec, mentor),
        "followups": [
            f"Why is {ticker} {direction.lower()} today?",
            f"What news matters most for {ticker}?",
            f"Give me a cautious vs optimistic view on {ticker}",
        ],
    }


def _fallback_no_ticker(market_news: list[dict], watchlist: list[str]) -> str:
    lines = [
        "Hey! I couldn't pin that to one NSE stock yet.",
        f"I can talk about: {', '.join(watchlist)}.",
        "Try: **How is RELIANCE.NS today?** or tap a quick action below.",
        "",
        "Meanwhile, market headlines:",
    ]
    if market_news:
        for m in market_news[:4]:
            lines.append(f"- {m['headline']}")
    else:
        lines.append("- None available right now.")
    lines.append("\nEducational only — not financial advice.")
    return "\n".join(lines)


def _fallback_ticker(a, direction, pct, news, articles, fh_rec, mentor) -> str:
    snap = a.get("snapshot") or {}
    lines = [
        f"Let's look at **{a.get('name')} ({a.get('ticker')})**.",
        f"Today it's **{direction}** ({pct:+.2f}%) at ₹{float(snap.get('current_price') or 0):,.2f}.",
        f"My model leans **{a.get('signal')}** · news feels **{news.get('label')}**.",
    ]
    if fh_rec:
        lines.append(f"Finnhub analysts lean **{_recommendation_label(fh_rec)}**.")
    if articles:
        lines.append("\nHeadlines catching my eye:")
        for art in articles[:3]:
            lines.append(f"- {art.get('headline')}")
    lines += ["", mentor.split("Note:")[0].strip(), "", "Educational only — not financial advice."]
    return "\n".join(lines)


def _call_groq(messages: list[dict]) -> str | None:
    key = get_groq_api_key()
    if not key:
        return None
    # Model IDs change over time on Groq free accounts — try a short fallback list.
    models = [
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
    ]
    for model in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.7,
                    "max_tokens": 700,
                    "messages": messages,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            if text:
                return text
        except Exception:
            continue
    return None


def _call_gemini(messages: list[dict]) -> str | None:
    key = get_gemini_api_key()
    if not key:
        return None
    # Flatten chat into Gemini contents
    system = ""
    contents = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
            continue
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    if system and contents and contents[0]["role"] == "user":
        contents[0]["parts"][0]["text"] = system + "\n\n" + contents[0]["parts"][0]["text"]
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            params={"key": key},
            headers={"Content-Type": "application/json"},
            json={"contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 700}},
            timeout=25,
        )
        if resp.status_code != 200:
            # fallback older flash name
            resp = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                params={"key": key},
                headers={"Content-Type": "application/json"},
                json={"contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 700}},
                timeout=25,
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except Exception:
        return None


def chat_with_bot(
    message: str,
    analyses: dict | None = None,
    history: list[dict] | None = None,
    style: str = "Friendly coach",
) -> dict[str, Any]:
    ctx = gather_context(message, analyses)
    provider = active_llm_provider()
    style_note = {
        "Friendly coach": "Tone: warm, encouraging coach.",
        "Concise": "Tone: short bullets, minimal fluff.",
        "News hunter": "Tone: focus on headlines and what they may imply.",
    }.get(style, "Tone: warm, encouraging coach.")

    user_block = (
        f"{style_note}\n\n"
        f"MARKET CONTEXT:\n{ctx['context_text']}\n\n"
        f"USER QUESTION:\n{message}"
    )

    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Keep a short chat memory for continuity
    for turn in (history or [])[-6:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            llm_messages.append({"role": "user" if role == "user" else "assistant", "content": content[:1500]})
    llm_messages.append({"role": "user", "content": user_block})

    reply = None
    used = "rules"
    if provider == "groq":
        reply = _call_groq(llm_messages)
        used = "groq" if reply else "rules"
    elif provider == "gemini":
        reply = _call_gemini(llm_messages)
        used = "gemini" if reply else "rules"

    if not reply:
        reply = ctx["fallback_reply"]
        used = "rules"

    sources = list(ctx.get("sources") or [])
    if used == "groq":
        sources.append("Groq Llama (free chatbot API)")
    elif used == "gemini":
        sources.append("Google Gemini (free chatbot API)")
    else:
        sources.append("Rule-based coach (no LLM key)")

    return {
        "ticker": ctx.get("ticker"),
        "reply": reply,
        "sources": sources,
        "articles": ctx.get("articles") or [],
        "recommendation": ctx.get("recommendation"),
        "direction": ctx.get("direction"),
        "signal": ctx.get("signal"),
        "followups": ctx.get("followups") or [],
        "provider": used,
    }


# Back-compat for older imports
def answer_user(message: str, analyses: dict | None = None) -> dict[str, Any]:
    return chat_with_bot(message, analyses)
