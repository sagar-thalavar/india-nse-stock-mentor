"""Stock Market Investment Planning — India NSE live data + paper portfolio."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.config import load_env

load_env()

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.auth import authenticate, seed_default_users
from modules.bot_advisor import active_llm_provider, chat_with_bot, finnhub_market_news
from modules.data_provider import get_market_provider
from modules.db import db_configured, db_status, persist_analysis
from modules.mentor import get_mentor
from modules.news_analysis import get_news_provider, score_news
from modules.notifications import evaluate_rules, load_alerts, mark_all_read, unread_count
from modules.paths import load_settings, save_settings
from modules.portfolio import SimulatedBroker, get_broker, holdings_table
from modules.signal_engine import analyze_stock, map_signal, strength_for
from modules.technical_analysis import add_indicators, max_drawdown

st.set_page_config(
    page_title="India Stocks — UP / DOWN",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEMO_BANNER = (
    "**Educational app** — live India NSE prices (delayed) + news headlines. "
    "Paper portfolio only — no broker, no real-money trading. "
    "UP/DOWN reasons are best-effort from news and indicators, not guarantees."
)


def inr(value: float, decimals: int = 0) -> str:
    if value is None:
        return "—"
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if decimals:
        whole, frac = f"{n:.{decimals}f}".split(".")
        return f"{sign}₹{indian_comma(whole)}.{frac}"
    return f"{sign}₹{indian_comma(f'{int(round(n))}')}"


def indian_comma(whole: str) -> str:
    if len(whole) <= 3:
        return whole
    last3 = whole[-3:]
    rest = whole[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts + [last3])


def signed_inr(value: float) -> str:
    prefix = "+" if value >= 0 else ""
    return prefix + inr(value)


def hide_host_chrome() -> None:
    """Hide Streamlit menu/footer/deploy controls as much as the host allows."""
    st.markdown(
        """
        <style>
        #MainMenu { visibility: hidden !important; }
        header[data-testid="stHeader"] { background: transparent !important; }
        div[data-testid="stToolbar"] { display: none !important; }
        .stDeployButton, div[data-testid="stAppDeployButton"] { display: none !important; }
        footer { visibility: hidden !important; height: 0 !important; }
        a[href*="streamlit.io"] { display: none !important; }
        a[href*="share.streamlit.io"] { display: none !important; }
        div[data-testid="stStatusWidget"] { display: none !important; }
        /* Cloud viewer badge / profile chip (best-effort; host may still inject) */
        [data-testid="stDecoration"] { display: none !important; }
        .viewerBadge_container__1QSob,
        .viewerBadge_link__1SLeV,
        .viewerBadge_text__1JaDK { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_theme(theme: str) -> None:
    hide_host_chrome()
    # High-contrast slate palette so Streamlit text never blends into the page.
    if theme == "light":
        st.markdown(
            """
            <style>
            :root {
              --bg: #eef2f5;
              --surface: #ffffff;
              --text: #142033;
              --muted: #4b5b70;
              --border: #b8c4d4;
              --accent: #1f5f4a;
            }
            .block-container { padding-top: 1.1rem; max-width: 1100px; }
            .stApp {
              background: var(--bg) !important;
              color: var(--text) !important;
            }
            section[data-testid="stSidebar"] {
              background: #e2e8ef !important;
              border-right: 1px solid var(--border);
            }
            h1, h2, h3, h4, .stMarkdown, .stCaption, label {
              color: var(--text) !important;
            }
            .stCaption, [data-testid="stCaptionContainer"] {
              color: var(--muted) !important;
              opacity: 1 !important;
            }
            [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
              color: var(--text) !important;
            }
            [data-testid="stMetricDelta"] { font-weight: 700; }
            .stAlert { color: var(--text) !important; }
            div[data-baseweb="select"] > div,
            .stTextInput input, .stNumberInput input {
              background: var(--surface) !important;
              color: var(--text) !important;
              border-color: var(--border) !important;
            }
            .stRadio label, .stCheckbox label { color: var(--text) !important; }
            .signal-buy, .dir-up {
              background:#d9f0e2 !important; color:#0f5132 !important; border:2px solid #0f5132 !important;
            }
            .signal-sell, .dir-down {
              background:#f8d7da !important; color:#842029 !important; border:2px solid #842029 !important;
            }
            .signal-hold, .dir-flat {
              background:#fff3cd !important; color:#664d03 !important; border:2px solid #997404 !important;
            }
            .kpi {
              background: var(--surface) !important;
              border: 1px solid var(--border);
              border-radius: 10px;
              padding: 14px 16px;
              box-shadow: 0 1px 2px rgba(20,32,51,0.06);
            }
            .kpi h3 { margin:0; font-size:0.8rem; color: var(--muted) !important; font-weight:600; }
            .kpi p { margin:6px 0 0; font-size:1.25rem; font-weight:700; color: var(--text) !important; }
            .mentor-box {
              background: var(--surface) !important;
              border: 1px solid var(--border);
              border-left: 5px solid var(--accent);
              padding: 14px 16px;
              border-radius: 6px;
              color: var(--text) !important;
              line-height: 1.45;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            :root {
              --bg: #0f1419;
              --surface: #1a2330;
              --text: #eef3f8;
              --muted: #a8b6c7;
              --border: #334155;
              --accent: #5dcea0;
            }
            .block-container { padding-top: 1.1rem; max-width: 1100px; }
            .stApp {
              background: var(--bg) !important;
              color: var(--text) !important;
            }
            section[data-testid="stSidebar"] {
              background: #141c27 !important;
              border-right: 1px solid var(--border);
            }
            h1, h2, h3, h4, .stMarkdown, .stCaption, label {
              color: var(--text) !important;
            }
            .stCaption, [data-testid="stCaptionContainer"] {
              color: var(--muted) !important;
              opacity: 1 !important;
            }
            [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
              color: var(--text) !important;
            }
            [data-testid="stMetricDelta"] { font-weight: 700; }
            .stAlert { color: var(--text) !important; }
            div[data-baseweb="select"] > div,
            .stTextInput input, .stNumberInput input {
              background: var(--surface) !important;
              color: var(--text) !important;
              border-color: var(--border) !important;
            }
            .stRadio label, .stCheckbox label { color: var(--text) !important; }
            .signal-buy, .dir-up {
              background:#123526 !important; color:#8ef0b8 !important; border:2px solid #3dd68c !important;
            }
            .signal-sell, .dir-down {
              background:#3a1717 !important; color:#ffb4b0 !important; border:2px solid #f07167 !important;
            }
            .signal-hold, .dir-flat {
              background:#3a3014 !important; color:#ffe08a !important; border:2px solid #e0b93a !important;
            }
            .kpi {
              background: var(--surface) !important;
              border: 1px solid var(--border);
              border-radius: 10px;
              padding: 14px 16px;
            }
            .kpi h3 { margin:0; font-size:0.8rem; color: var(--muted) !important; font-weight:600; }
            .kpi p { margin:6px 0 0; font-size:1.25rem; font-weight:700; color: var(--text) !important; }
            .mentor-box {
              background: var(--surface) !important;
              border: 1px solid var(--border);
              border-left: 5px solid var(--accent);
              padding: 14px 16px;
              border-radius: 6px;
              color: var(--text) !important;
              line-height: 1.45;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def direction_from_pct(pct: float | None) -> str:
    p = float(pct or 0)
    if p > 0.05:
        return "UP"
    if p < -0.05:
        return "DOWN"
    return "FLAT"


def direction_card(direction: str, pct: float, price: float) -> None:
    cls = {"UP": "dir-up", "DOWN": "dir-down", "FLAT": "dir-flat"}.get(direction, "dir-flat")
    st.markdown(
        f"""
        <div class="{cls}" style="border-radius:12px;padding:20px 22px;text-align:center;margin-bottom:12px;">
          <div style="font-size:0.75rem;letter-spacing:0.14em;">TODAY</div>
          <div style="font-size:2.4rem;font-weight:800;line-height:1.1;">{direction}</div>
          <div style="margin-top:8px;">{inr(price, 2)} · {pct:+.2f}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _persist_async(analysis: dict) -> None:
    """Best-effort Neon write off the UI thread."""
    try:
        persist_analysis(analysis)
    except Exception:
        return


def _spawn_persist(analysis: dict) -> None:
    threading.Thread(target=_persist_async, args=(analysis,), daemon=True).start()


@st.cache_data(ttl=60, show_spinner=False)
def cached_db_status() -> dict:
    return db_status()


@st.cache_data(show_spinner=False, ttl=300)
def analyze_ticker_light(ticker: str, name: str, _settings_key: str) -> dict:
    """Fast path: prices + technicals only (no news, no DB wait)."""
    settings = load_settings()
    market = get_market_provider()
    hist = market.history(ticker)
    snap = market.snapshot(ticker)
    display_name = snap.get("name") or name
    analysis = analyze_stock(
        ticker, display_name, hist, settings, include_news=False
    )
    analysis["snapshot"] = snap
    analysis["history"] = hist
    analysis["name"] = display_name
    analysis["news_loaded"] = False
    return analysis


@st.cache_data(show_spinner=False, ttl=300)
def fetch_ticker_news(ticker: str, name: str) -> dict:
    """Lazy news fetch for one ticker."""
    news_provider = get_news_provider()
    articles = news_provider.for_ticker(ticker, name)[:8]
    return score_news(articles) | {"articles": articles}


def enrich_analysis_with_news(analysis: dict, settings: dict | None = None) -> dict:
    """Attach news and refresh score when a detail page needs it."""
    if analysis.get("news_loaded"):
        return analysis
    settings = settings or load_settings()
    ticker = analysis["ticker"]
    name = analysis.get("name") or ticker
    packed = fetch_ticker_news(ticker, name)
    articles = packed.pop("articles", [])
    news = packed
    # Rebuild news component of overall score without re-downloading prices.
    tw = float(settings.get("technical_weight", 0.50))
    mw = float(settings.get("momentum_weight", 0.20))
    nw = float(settings.get("news_weight", 0.20))
    vw = float(settings.get("volume_weight", 0.10))
    total_w = tw + mw + nw + vw or 1.0
    tw, mw, nw, vw = tw / total_w, mw / total_w, nw / total_w, vw / total_w
    tech_100 = next((f["component"] for f in analysis["factors"] if f["name"] == "Technical Analysis"), 50)
    mom_100 = next((f["component"] for f in analysis["factors"] if f["name"] == "Momentum"), 50)
    vol_100 = next((f["component"] for f in analysis["factors"] if f["name"] == "Volume"), 50)
    news_100 = max(0.0, min(100.0, 50 + float(news["score"]) * 40))
    overall = round(tw * tech_100 + mw * mom_100 + nw * news_100 + vw * vol_100, 1)
    signal = map_signal(overall, settings)
    out = dict(analysis)
    out["news"] = news
    out["articles"] = articles[:6]
    out["overall"] = overall
    out["signal"] = signal
    out["strength"] = strength_for(overall, signal)
    out["confidence"] = max(20, min(92, int(round(abs(overall - 50) * 1.6 + 20))))
    out["factors"] = [
        f if f["name"] != "News Sentiment"
        else {**f, "component": round(news_100, 1), "note": f"{news['label']} ({news['score']:+.2f}) news"}
        for f in analysis["factors"]
    ]
    out["news_loaded"] = True
    _spawn_persist(out)
    return out


def load_all_analyses(_settings_key: str) -> dict:
    """Parallel light price load — UI stays usable; news deferred."""
    market = get_market_provider()
    stocks = market.list_stocks()
    out: dict = {}
    if not stocks:
        return out

    def _one(stock):
        return stock.ticker, analyze_ticker_light(stock.ticker, stock.name, _settings_key)

    with ThreadPoolExecutor(max_workers=min(4, len(stocks))) as pool:
        futures = [pool.submit(_one, s) for s in stocks]
        for fut in as_completed(futures):
            try:
                ticker, analysis = fut.result()
                out[ticker] = analysis
                _spawn_persist(analysis)
            except Exception:
                continue
    return out


def price_map(analyses: dict) -> dict[str, float]:
    return {t: a["metrics"]["price"] for t, a in analyses.items()}


def names_map(analyses: dict) -> dict[str, str]:
    return {t: a["name"] for t, a in analyses.items()}


def signal_counts(analyses: dict) -> dict[str, int]:
    c = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for a in analyses.values():
        c[a["signal"]] = c.get(a["signal"], 0) + 1
    return c


def portfolio_day_change(rows: list[dict], analyses: dict) -> float:
    chg = 0.0
    for r in rows:
        snap = analyses.get(r["ticker"], {}).get("snapshot", {})
        chg += r["quantity"] * float(snap.get("daily_change") or 0)
    return chg


def kpi(label: str, value: str) -> None:
    st.markdown(f'<div class="kpi"><h3>{label}</h3><p>{value}</p></div>', unsafe_allow_html=True)


def signal_card(signal: str, score: float, strength: str, confidence: int) -> None:
    cls = {"BUY": "signal-buy", "SELL": "signal-sell", "HOLD": "signal-hold"}.get(signal, "signal-hold")
    st.markdown(
        f"""
        <div class="{cls}" style="border-radius:16px;padding:22px 24px;text-align:center;margin-bottom:12px;">
          <div style="font-size:0.8rem;letter-spacing:0.12em;">MODEL SIGNAL</div>
          <div style="font-size:2.6rem;font-weight:800;line-height:1.1;">{signal}</div>
          <div style="margin-top:8px;">Score: {score:.0f}/100 · Strength: {strength}</div>
          <div style="font-size:0.9rem;margin-top:6px;">Confidence: {confidence}% (not a win probability)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def price_chart(hist: pd.DataFrame, period: str, ticker: str) -> go.Figure:
    market = get_market_provider()
    sl = market.slice_range(ticker, period)
    sl = add_indicators(sl)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=sl["date"],
            open=sl["open"],
            high=sl["high"],
            low=sl["low"],
            close=sl["close"],
            name="OHLC",
        )
    )
    fig.add_trace(go.Scatter(x=sl["date"], y=sl["sma20"], name="SMA20", line=dict(width=1.4)))
    fig.add_trace(go.Scatter(x=sl["date"], y=sl["sma50"], name="SMA50", line=dict(width=1.4)))
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark" if load_settings().get("theme", "light") == "dark" else "plotly_white",
        legend=dict(orientation="h"),
        yaxis_title="Price (₹)",
    )
    return fig


def run_startup_alerts(analyses: dict, broker: SimulatedBroker) -> None:
    settings = load_settings()
    rows, _ = holdings_table(broker, price_map(analyses))
    day_pnl = portfolio_day_change(rows, analyses)
    equity = sum(r["current_value"] for r in rows) + float(broker.load()["cash"])
    # Approximate today's % vs equity using holding daily moves.
    pct = (day_pnl / (equity - day_pnl) * 100.0) if equity - day_pnl else 0.0
    evaluate_rules(
        {t: a["signal"] for t, a in analyses.items()},
        names_map(analyses),
        pct,
        settings,
        price_map(analyses),
    )


def page_dashboard(analyses: dict, broker: SimulatedBroker) -> None:
    st.title("India Stocks")
    st.caption("NSE watchlist · live prices · paper portfolio")
    st.info(DEMO_BANNER)

    status = cached_db_status()
    if status.get("ok"):
        st.caption(
            f"Neon connected · stocks {status.get('stocks')} · "
            f"prices {status.get('prices')} · news {status.get('news')} · "
            f"signals {status.get('signals')}"
        )
    else:
        st.caption(f"Neon: {status.get('message')}")

    rows, summary = holdings_table(broker, price_map(analyses))
    day = portfolio_day_change(rows, analyses)
    counts = signal_counts(analyses)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Portfolio Value", inr(summary["portfolio_value"]))
    with c2:
        kpi("Cash", inr(summary["cash"]))
    with c3:
        kpi("Invested", inr(summary["invested"]))
    with c4:
        kpi("Today's Change", signed_inr(day))
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        kpi("Holdings", str(summary["holdings_count"]))
    with c6:
        kpi("BUY Signals", str(counts["BUY"]))
    with c7:
        kpi("SELL Signals", str(counts["SELL"]))
    with c8:
        kpi("HOLD Signals", str(counts["HOLD"]))

    st.subheader("NSE watchlist")
    table = []
    for t, a in analyses.items():
        s = a["snapshot"]
        pct = float(s.get("daily_change_pct") or 0)
        table.append(
            {
                "Ticker": t,
                "Name": a["name"],
                "Sector": s.get("sector"),
                "Price": round(float(s.get("current_price") or 0), 2),
                "Day %": round(pct, 2),
                "Direction": direction_from_pct(pct),
                "Signal": a["signal"],
                "Score": a["overall"],
            }
        )
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    st.subheader("Recent alerts")
    alerts = load_alerts()[:6]
    if not alerts:
        st.write("No alerts yet.")
    else:
        for a in alerts:
            st.write(f"{a.get('timestamp')} — {a.get('message')}")


def page_stocks(analyses: dict) -> None:
    st.title("Stocks")
    st.caption("One stock at a time — price, chart, and headlines.")
    market = get_market_provider()
    options = {f"{s.ticker} · {analyses.get(s.ticker, {}).get('name', s.name)}": s.ticker for s in market.list_stocks()}
    choice = st.selectbox("Select NSE stock", list(options.keys()))
    ticker = options[choice]
    with st.spinner("Loading headlines for this stock…"):
        a = enrich_analysis_with_news(analyses[ticker])
        analyses[ticker] = a
    s = a["snapshot"]
    pct = float(s.get("daily_change_pct") or 0)
    direction = direction_from_pct(pct)

    direction_card(direction, pct, float(s.get("current_price") or 0))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Price", inr(s["current_price"], 2), signed_inr(s["daily_change"]) + f" ({pct:+.2f}%)")
    m2.metric("Previous close", inr(s["previous_close"], 2))
    m3.metric("Volume", f"{s['volume']:,}")
    m4.metric("Signal", a["signal"], f"Score {a['overall']:.0f}")

    st.markdown("### Why")
    st.markdown(
        f"<div class='mentor-box'>{get_mentor().generate_explanation(a).replace(chr(10), '<br>')}</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.write(f"**1-week:** {s['week_change_pct']:+.2f}%" if s["week_change_pct"] is not None else "**1-week:** —")
    c2.write(f"**1-month:** {s['month_change_pct']:+.2f}%" if s["month_change_pct"] is not None else "**1-month:** —")
    c3.write(f"**3-month:** {s['three_month_change_pct']:+.2f}%" if s["three_month_change_pct"] is not None else "**3-month:** —")
    c4.write(f"**52-week high / low:** {inr(s['week_52_high'], 2)} / {inr(s['week_52_low'], 2)}")

    period = st.radio("Chart range", ["1W", "1M", "3M", "6M", "1Y"], horizontal=True, index=1)
    st.plotly_chart(price_chart(a["history"], period, ticker), use_container_width=True)

    news = a["articles"]
    st.subheader("Latest news")
    if not news:
        st.write("No headlines found for this ticker right now.")
    else:
        for n in news:
            link = f" [open]({n['url']})" if n.get("url") else ""
            st.markdown(
                f"**{n['date']} · {n['headline']}**{link}  \n"
                f"{n.get('summary') or ''}  \n"
                f"_{n.get('source')} · {n.get('sentiment')} · {n.get('importance')}_"
            )


def page_analysis(analyses: dict) -> None:
    st.title("UP / DOWN analysis")
    st.caption("Pick one stock. See direction first, then likely reasons from news and technicals.")
    market = get_market_provider()
    options = {f"{s.ticker} · {analyses.get(s.ticker, {}).get('name', s.name)}": s.ticker for s in market.list_stocks()}
    choice = st.selectbox("Stock", list(options.keys()), key="an_sel")
    ticker = options[choice]
    with st.spinner("Loading headlines for this stock…"):
        a = enrich_analysis_with_news(analyses[ticker])
        analyses[ticker] = a
    mentor = get_mentor()
    s = a["snapshot"]
    pct = float(s.get("daily_change_pct") or 0)
    direction = direction_from_pct(pct)

    left, right = st.columns([1, 1.15])
    with left:
        direction_card(direction, pct, float(s.get("current_price") or 0))
        signal_card(a["signal"], a["overall"], a["strength"], a["confidence"])
        st.caption(a["disclaimer"])

        st.markdown("**Likely reasons (news)**")
        ns = a["news"]
        st.write(f"Tone: **{ns['label']}** ({ns['score']:+.2f}) · {ns['count']} articles")
        if a.get("articles"):
            for n in a["articles"][:4]:
                st.write(f"- {n.get('date')}: {n.get('headline')}")
        else:
            st.write("No recent headlines available.")

        st.markdown("**Technical notes**")
        m = a["metrics"]
        st.write(
            f"SMA20 {m['sma20']:.2f} · SMA50 {m['sma50']:.2f} · RSI {m['rsi14']:.1f}  \n"
            f"Momentum {m['momentum']:.2f}% · Vol trend {m['volume_trend']:+.1f}%"
        )
    with right:
        st.markdown("### Plain explanation")
        st.markdown(
            f"<div class='mentor-box'>{mentor.generate_explanation(a).replace(chr(10), '<br>')}</div>",
            unsafe_allow_html=True,
        )
        period = st.radio("Chart", ["1M", "3M", "6M", "1Y"], horizontal=True, key="an_ch")
        st.plotly_chart(price_chart(a["history"], period, ticker), use_container_width=True)

        with st.expander("Score breakdown"):
            for f in a["factors"]:
                st.write(
                    f"- {f['name']} ({f['weight']*100:.0f}%): {f['component']:.1f}/100 — {f['note']}"
                )
            for item in a["checklist"]:
                mark = "✓" if item["ok"] else "✗"
                st.write(f"{mark} {item['text']}")


def page_compare(analyses: dict) -> None:
    st.title("Stock comparison")
    st.caption("Side-by-side NSE metrics — not a ranking of best investments.")
    market = get_market_provider()
    labels = {f"{s.ticker} · {analyses.get(s.ticker, {}).get('name', s.name)}": s.ticker for s in market.list_stocks()}
    picked = st.multiselect("Select 2–3 stocks", list(labels.keys()), default=list(labels.keys())[:3])
    if len(picked) < 2:
        st.info("Pick at least two stocks to compare.")
        return
    if len(picked) > 3:
        st.warning("Showing the first three selections.")
        picked = picked[:3]
    cols = st.columns(len(picked))
    for col, lab in zip(cols, picked):
        t = labels[lab]
        a = analyses[t]
        m = a["metrics"]
        with col:
            st.subheader(a["name"])
            st.write(f"Signal **{a['signal']}** · score {a['overall']:.0f}")
            st.write(f"Price momentum (10d): {m['momentum']:.2f}%")
            st.write(f"RSI14: {m['rsi14']:.1f}")
            st.write("SMA trend: " + ("SMA20 > SMA50" if m["sma20_gt_sma50"] else "SMA20 ≤ SMA50"))
            st.write(f"MACD vs signal: {m['macd'] - m['macd_signal']:+.3f}")
            st.write(f"Volatility: {m['volatility']:.1f}%")
            st.write(f"News sentiment: {a['news']['label']} ({a['news']['score']:+.2f})")
            st.write(f"Overall demo score: {a['overall']:.1f}")


def page_portfolio(analyses: dict, broker: SimulatedBroker) -> None:
    st.title("Simulated portfolio")
    st.error("SIMULATED ORDER workspace — Demo only — no real money or broker account is connected.")
    rows, summary = holdings_table(broker, price_map(analyses))
    day = portfolio_day_change(rows, analyses)
    a, b, c, d = st.columns(4)
    a.metric("Portfolio value", inr(summary["portfolio_value"]))
    b.metric("Cash", inr(summary["cash"]))
    c.metric("Invested", inr(summary["invested"]))
    d.metric("Today's demo P&L", signed_inr(day))

    st.subheader("Holdings")
    if not rows:
        st.write("No holdings yet. Place a simulated buy below.")
    else:
        df = pd.DataFrame(rows)
        show = df.rename(
            columns={
                "stock": "Stock",
                "quantity": "Quantity",
                "average_price": "Average Price",
                "current_demo_price": "Current Demo Price",
                "invested_value": "Invested Value",
                "current_value": "Current Value",
                "pnl": "P&L",
                "pnl_pct": "P&L %",
            }
        )[["Stock", "Quantity", "Average Price", "Current Demo Price", "Invested Value", "Current Value", "P&L", "P&L %"]]
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption("Green/red in the mentor view: P&L > 0 is a demo profit; P&L < 0 is a demo loss.")
        losers = [r for r in rows if r["pnl"] < 0]
        winners = [r for r in rows if r["pnl"] > 0]
        if winners:
            st.success("In profit (demo): " + ", ".join(f"{r['stock']} ({r['pnl_pct']:+.1f}%)" for r in winners))
        if losers:
            st.error("In loss (demo): " + ", ".join(f"{r['stock']} ({r['pnl_pct']:+.1f}%)" for r in losers))

    st.subheader("Place a simulated order")
    st.caption("Signal = what the model calculates · Explanation = why · Simulation = paper fill only.")
    market = get_market_provider()
    options = {f"{s.ticker} · {s.name}": s.ticker for s in market.list_stocks()}
    lab = st.selectbox("Stock", list(options.keys()), key="ord_stk")
    ticker = options[lab]
    a = analyses[ticker]
    px = a["metrics"]["price"]
    side = st.radio("Side", ["BUY", "SELL"], horizontal=True)
    qty = st.number_input("Quantity", min_value=1, value=10, step=1)
    preview = broker.preview_order(side, ticker, a["name"], int(qty), px)
    st.info(
        f"**{preview['label']}**  \n"
        f"{preview['side']} {preview['name']} · {preview['quantity']} shares · {inr(preview['price'], 2)}/share  \n"
        f"Transaction value: {inr(preview['total'])}  \n"
        f"{preview['warning']}"
    )
    st.write(f"Current demo signal at order time: **{a['signal']}** (score {a['overall']:.0f})")
    if st.button("Confirm simulated transaction"):
        result = broker.execute(side, ticker, a["name"], int(qty), px, signal=a["signal"], score=a["overall"])
        if result["ok"]:
            st.success("Portfolio updated. This was a SIMULATED ORDER only.")
            st.toast("Simulated order filled locally")
            st.rerun()
        else:
            st.error(result.get("error"))

    st.subheader("Risk information (demo portfolio)")
    equity = summary["portfolio_value"]
    if rows:
        top = max(rows, key=lambda r: r["weight"])
        if top["weight"] >= 30:
            st.warning(
                f"Your simulated portfolio has {top['weight']:.0f}% allocated to {top['stock']}. "
                "This represents high concentration in this demo portfolio."
            )
        for r in rows:
            hist = analyses[r["ticker"]]["history"]
            dd = max_drawdown(hist["close"])
            vol = analyses[r["ticker"]]["metrics"]["volatility"]
            pos_pct = (r["current_value"] / equity * 100) if equity else 0
            st.write(
                f"**{r['stock']}** — position {pos_pct:.1f}% of demo equity · "
                f"vol {vol:.1f}% · max sample drawdown {dd:.1f}%"
            )
    else:
        st.write("Add a simulated holding to see concentration and volatility notes.")
    st.caption("These figures describe the demo dataset and paper portfolio. They are not personalised financial advice.")

    if st.button("Reset simulated portfolio to initial cash"):
        broker.reset()
        st.success("Portfolio reset.")
        st.rerun()


def page_watchlist(analyses: dict) -> None:
    st.title("Watchlist")
    settings = load_settings()
    market = get_market_provider()
    all_t = [s.ticker for s in market.list_stocks()]
    labels = {s.ticker: s.name for s in market.list_stocks()}
    current = [t for t in settings.get("watchlist", []) if t in all_t]
    selected = st.multiselect(
        "My Watchlist",
        all_t,
        default=current,
        format_func=lambda t: f"{t} · {labels.get(t, t)}",
    )
    if selected != current:
        settings["watchlist"] = selected
        save_settings(settings)
        st.toast("Watchlist saved locally")
    if not selected:
        st.write("Add demo tickers to track prices, signals, and sample news sentiment.")
        return
    for t in selected:
        a = analyses[t]
        s = a["snapshot"]
        st.markdown(
            f"**{a['name']}** · {inr(s['current_price'], 2)} · "
            f"{s['daily_change_pct']:+.2f}% · **{a['signal']}** · score {a['overall']:.0f} · "
            f"news {a['news']['label']}"
        )


def page_alerts() -> None:
    st.title("Alerts")
    st.caption("Local notification centre. FUTURE: email / WhatsApp / Telegram adapters can hook create_alert().")
    items = load_alerts()
    st.write(f"Unread: **{unread_count(items)}**")
    if st.button("Mark all as read"):
        mark_all_read()
        st.rerun()
    if not items:
        st.write("No notifications stored yet.")
        return
    for a in items:
        flag = "🔵" if not a.get("read") else "⚪"
        st.write(f"{flag} {a.get('timestamp')} — {a.get('message')}")


def page_transactions(broker: SimulatedBroker) -> None:
    st.title("Transaction history")
    st.caption("Every row is a SIMULATED ORDER stored in data/transactions.json.")
    txs = broker.transactions()
    if not txs:
        st.write("No simulated trades yet.")
        return
    df = pd.DataFrame(txs)
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_bot(analyses: dict) -> None:
    st.title("NSE Coach Bot")
    st.caption("Chat about stocks — live news + free chatbot API. Educational only, not financial advice.")

    provider = active_llm_provider()
    if provider == "groq":
        st.success("Chat brain: **Groq** (free Llama API)")
    elif provider == "gemini":
        st.success("Chat brain: **Google Gemini** (free API)")
    else:
        st.warning(
            "No chatbot API key yet — using the built-in coach. "
            "Add a free **GROQ_API_KEY** (recommended) or **GEMINI_API_KEY** to `.env` for livelier replies."
        )

    with st.expander("Free bot APIs you can use", expanded=(provider == "rules")):
        st.markdown(
            """
| API | Cost | Get key |
|-----|------|---------|
| **Groq** (best easy pick) | Free, no card | [console.groq.com](https://console.groq.com) → API Keys |
| **Google Gemini** | Free tier, no card | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| OpenRouter `:free` models | Free daily limit | openrouter.ai |

Put one of these in `.env` / `.env.local`:
```
GROQ_API_KEY=your_key_here
```
or
```
GEMINI_API_KEY=your_key_here
```
Then restart Streamlit.
            """
        )

    style = st.selectbox(
        "Bot personality",
        ["Friendly coach", "Concise", "News hunter"],
        index=0,
        key="bot_style",
    )

    st.markdown("**Quick actions**")
    tickers = list(analyses.keys()) or ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    qa_cols = st.columns(min(4, max(1, len(tickers) + 1)))
    quick_prompts = [f"How is {t} today?" for t in tickers[:3]]
    quick_prompts.append("What are today's market headlines?")
    clicked = None
    for i, qp in enumerate(quick_prompts):
        with qa_cols[i % len(qa_cols)]:
            if st.button(qp, key=f"bot_qa_{i}", use_container_width=True):
                clicked = qp

    st.subheader("Market pulse")
    headlines = finnhub_market_news(4)
    if not headlines:
        st.write("No Finnhub headlines right now.")
    else:
        for h in headlines:
            url = h.get("url")
            title = h.get("headline")
            if url:
                st.markdown(f"- [{title}]({url}) _{h.get('source')}_")
            else:
                st.markdown(f"- {title} _{h.get('source')}_")

    if "bot_chat" not in st.session_state:
        st.session_state.bot_chat = [
            {
                "role": "assistant",
                "content": (
                    "Hey! I'm your **NSE Coach**. Ask me anything like:\n"
                    "- How is RELIANCE.NS today?\n"
                    "- News on TCS — should I be cautious?\n"
                    "- Give me a simple read on INFY\n\n"
                    "Tap a quick action above, or type below. I'll use live prices/news"
                    + (" + a free AI chat API." if provider != "rules" else " (add Groq for richer chat).")
                ),
            }
        ]
    if "bot_followups" not in st.session_state:
        st.session_state.bot_followups = []

    for msg in st.session_state.bot_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Follow-up chips from last reply
    if st.session_state.bot_followups:
        st.markdown("**Suggested follow-ups**")
        fcols = st.columns(min(3, len(st.session_state.bot_followups)))
        for i, fu in enumerate(st.session_state.bot_followups[:3]):
            with fcols[i]:
                if st.button(fu, key=f"bot_fu_{i}", use_container_width=True):
                    clicked = fu

    prompt = clicked or st.chat_input("Ask me about a stock, news, or recommendation…")
    if prompt:
        st.session_state.bot_chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking with live market data…" + (" and AI…" if provider != "rules" else "")):
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.bot_chat[:-1]
                    if m.get("role") in {"user", "assistant"}
                ]
                result = chat_with_bot(prompt, analyses, history=history, style=style)
            reply = result["reply"]
            meta = f"_Brain: **{result.get('provider')}**_"
            src = ", ".join(result.get("sources") or [])
            if src:
                meta += f" · _Sources: {src}_"
            full = f"{reply}\n\n{meta}"
            st.markdown(full)
            st.session_state.bot_chat.append({"role": "assistant", "content": full})
            st.session_state.bot_followups = result.get("followups") or []
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear chat", use_container_width=True):
            st.session_state.bot_chat = []
            st.session_state.bot_followups = []
            st.rerun()
    with c2:
        if st.button("Say hello again", use_container_width=True):
            st.session_state.bot_chat = []
            st.session_state.bot_followups = []
            st.rerun()


def page_settings() -> None:
    st.title("Settings")
    st.caption("Stored locally in data/settings.json. Weights should roughly sum to 1.0; they are normalised at runtime.")
    s = load_settings()
    theme = st.selectbox("Theme", ["dark", "light"], index=0 if s.get("theme") == "dark" else 1)
    cash = st.number_input("Initial portfolio cash (₹)", min_value=10000, value=int(s.get("initial_cash", 1_000_000)), step=10000)
    buy_t = st.slider("BUY threshold (overall score)", 50, 90, int(s.get("buy_threshold", 70)))
    hold_l = st.slider("HOLD lower bound", 20, 69, int(s.get("hold_low", 45)))
    st.write("Overall scores below the HOLD lower bound map to SELL.")
    tw = st.slider("Technical weight", 0.0, 1.0, float(s.get("technical_weight", 0.5)), 0.05)
    mw = st.slider("Momentum weight", 0.0, 1.0, float(s.get("momentum_weight", 0.2)), 0.05)
    nw = st.slider("News weight", 0.0, 1.0, float(s.get("news_weight", 0.2)), 0.05)
    vw = st.slider("Volume weight", 0.0, 1.0, float(s.get("volume_weight", 0.1)), 0.05)
    tech_buy = st.number_input("Technical points for BUY", value=int(s.get("tech_score_buy", 4)), min_value=1, max_value=8)
    tech_hold = st.number_input("Technical points HOLD minimum", value=int(s.get("tech_score_hold_low", 1)), min_value=0, max_value=7)
    alert_pct = st.number_input("Portfolio drop alert (%)", value=float(s.get("alert_percentage", 2.0)), min_value=0.5, max_value=20.0, step=0.5)
    st.markdown("**Price alerts** (demo last close ≥ level)")
    market = get_market_provider()
    pa = dict(s.get("price_alerts") or {})
    ticker_opts = [x.ticker for x in market.list_stocks()]
    pa_t = st.selectbox("Alert ticker", ticker_opts)
    pa_px = st.number_input("Alert price (₹)", min_value=0.0, value=float(pa.get(pa_t, 0) or 0), step=10.0)
    if st.button("Save settings"):
        if pa_px > 0:
            pa[pa_t] = pa_px
        s.update(
            {
                "theme": theme,
                "initial_cash": cash,
                "buy_threshold": buy_t,
                "hold_low": hold_l,
                "sell_threshold": hold_l - 1,
                "technical_weight": tw,
                "momentum_weight": mw,
                "news_weight": nw,
                "volume_weight": vw,
                "tech_score_buy": tech_buy,
                "tech_score_hold_low": tech_hold,
                "alert_percentage": alert_pct,
                "price_alerts": pa,
            }
        )
        save_settings(s)
        st.success("Saved. Reload the dashboard to recompute signals with new weights.")
        st.cache_data.clear()
        st.rerun()


def render_login_page() -> None:
    """Full-bleed login gate before any market data loads."""
    apply_theme("light")
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stHeader"] { background: transparent; }
        .stApp {
          background:
            radial-gradient(circle at 12% 18%, #d9ebe3 0%, transparent 42%),
            radial-gradient(circle at 88% 10%, #d6e0ef 0%, transparent 36%),
            linear-gradient(160deg, #eef2f5 0%, #e7ece9 55%, #dfe7e2 100%) !important;
        }
        .login-shell {
          max-width: 440px;
          margin: 4.5rem auto 2rem;
          background: #ffffff;
          border: 1px solid #cfd6d2;
          border-radius: 18px;
          padding: 2rem 1.75rem 1.5rem;
          box-shadow: 0 18px 40px rgba(20, 32, 51, 0.08);
        }
        .login-brand {
          font-size: 0.78rem;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: #1f5f4a;
          font-weight: 700;
          margin-bottom: 0.35rem;
        }
        .login-title {
          font-size: 1.9rem;
          line-height: 1.15;
          font-weight: 800;
          color: #142033;
          margin: 0 0 0.4rem;
        }
        .login-sub {
          color: #4b5b70;
          margin: 0 0 1.2rem;
          font-size: 0.98rem;
        }
        .login-hint {
          margin-top: 1rem;
          padding: 0.85rem 0.95rem;
          background: #f3f7f5;
          border: 1px solid #cfe0d7;
          border-radius: 10px;
          color: #243247;
          font-size: 0.86rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Ensure Neon users exist (idempotent).
    db_ok = db_configured()
    seeded = 0
    seed_error = None
    if db_ok:
        try:
            seeded = seed_default_users()
        except Exception as exc:
            seed_error = f"{type(exc).__name__}: {exc}"

    left, center, right = st.columns([1, 1.25, 1])
    with center:
        st.markdown(
            """
            <div class="login-shell">
              <div class="login-brand">India NSE · Mentor</div>
              <h1 class="login-title">Sign in</h1>
              <p class="login-sub">Use your username and password to open the live NSE workspace.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Continue", use_container_width=True, type="primary")

        if not db_ok:
            st.error("DATABASE_URL is missing — add it in Streamlit Cloud → App settings → Secrets.")
            st.code(
                'DATABASE_URL = "postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"\n'
                'FINNHUB_API_KEY = "your_key"\n'
                'GROQ_API_KEY = "your_key"',
                language="toml",
            )
            return
        if seed_error:
            st.error(f"Could not prepare users table: {seed_error}")
            return
        if seeded:
            st.info("Demo users were created in Neon.")

        if submitted:
            user = authenticate(username, password)
            if user:
                st.session_state["auth_user"] = user
                st.success(f"Welcome, {user['display_name']}")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.markdown(
            """
            <div class="login-hint">
              <b>Demo logins</b><br/>
              admin / Admin@123<br/>
              sagar / Sagar@123<br/>
              demo / Demo@123
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    settings = load_settings()

    if "auth_user" not in st.session_state or not st.session_state.get("auth_user"):
        render_login_page()
        return

    apply_theme(settings.get("theme", "light"))
    settings_key = str(sorted(settings.items()))
    user = st.session_state["auth_user"]

    # Sidebar first so navigation is available immediately on each run.
    unread = unread_count()
    with st.sidebar:
        st.markdown("## India Stocks")
        st.caption(f"Signed in as **{user.get('display_name') or user.get('username')}**")
        st.caption("NSE live data · paper trading")
        st.caption(f"Alerts unread: {unread}")
        page = st.radio(
            "Navigate",
            [
                "Dashboard",
                "Stocks",
                "Analysis",
                "Bot",
                "Compare",
                "Portfolio",
                "Watchlist",
                "Alerts",
                "Transactions",
                "Settings",
            ],
        )
        st.markdown("---")
        st.caption("Prices: Yahoo Finance (NSE)")
        st.caption("News: on demand (Stocks/Analysis/Bot)")
        st.caption("Bot: Groq + Finnhub")
        st.caption("Storage: Neon (background)")
        st.caption("Orders: simulated only")
        if st.button("Refresh prices", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if st.button("Log out", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.rerun()

    # Light parallel price load (no news) — cached after first fetch.
    with st.spinner("Refreshing NSE prices…"):
        analyses = load_all_analyses(settings_key)
    if not analyses:
        st.error("No stock data loaded. Check internet, then click **Refresh prices**.")
        return

    broker = get_broker()
    if page == "Dashboard":
        # Alerts only when landing on dashboard (avoid extra work elsewhere).
        run_startup_alerts(analyses, broker)
        page_dashboard(analyses, broker)
    elif page == "Stocks":
        page_stocks(analyses)
    elif page == "Analysis":
        page_analysis(analyses)
    elif page == "Bot":
        page_bot(analyses)
    elif page == "Compare":
        page_compare(analyses)
    elif page == "Portfolio":
        page_portfolio(analyses, broker)
    elif page == "Watchlist":
        page_watchlist(analyses)
    elif page == "Alerts":
        page_alerts()
    elif page == "Transactions":
        page_transactions(broker)
    else:
        page_settings()


if __name__ == "__main__":
    main()
