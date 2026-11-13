# India NSE Stocks — UP / DOWN

Educational Streamlit app: **live India NSE prices**, headlines, chat bot, rule-based signals, and a **paper portfolio**.  
Snapshots and logins are stored in **Neon Postgres**.

**Not a brokerage. Not financial advice.** UP/DOWN “why” text is best-effort from news + indicators.

## Login (Neon)

On first run the app creates an `app_users` table and seeds 3 demo accounts (passwords hashed):

| Username | Password |
|----------|----------|
| `admin` | `Admin@123` |
| `sagar` | `Sagar@123` |
| `demo` | `Demo@123` |

## What it uses

| Piece | Source |
|-------|--------|
| Prices / charts | Yahoo Finance via `yfinance` (`RELIANCE.NS`, …) |
| News | Finnhub → yfinance fallback |
| Chat bot | Groq (optional) + Finnhub context |
| Auth / snapshots | Neon Postgres |
| Portfolio | Local simulated JSON only |

## Setup

```powershell
.\.venv_new\Scripts\Activate.ps1
pip install -r requirements.txt
```

Secrets in `.env` / `.env.local` (gitignored):

- `DATABASE_URL`
- `FINNHUB_API_KEY`
- `GROQ_API_KEY` (optional)
- `GEMINI_API_KEY` (optional)

## Run

```powershell
.\.venv_new\Scripts\Activate.ps1
python -m streamlit run app.py
```

Open `http://localhost:8501`, sign in, then use the app.

**Note:** Streamlit is not a natural fit for Vercel (serverless). Prefer Streamlit Community Cloud, Railway, or Render for hosting; we can still keep the code on GitHub.

## Pages

- **Dashboard** — NSE table with Direction (UP/DOWN/FLAT) + Neon status  
- **Stocks** — one ticker: direction, why, chart, news  
- **Analysis** — direction + model signal breakdown  
- **Portfolio / Transactions** — simulated orders only  

## Project layout

```
app.py
requirements.txt
.env / .env.local          # secrets (not committed)
data/stocks.json           # NSE watchlist
modules/
  config.py                # load env
  live_market.py           # India NSE via yfinance
  live_news.py             # Finnhub / yfinance news
  db.py                    # Neon schema + persistence
  signal_engine.py
  mentor.py
  ...
```

## Safety

- No real-money trading  
- Neon stores analysis snapshots for demo/history — not brokerage orders  
- Rotate API keys if they were ever pasted into chat  
