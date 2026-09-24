# Portfyl — Portfolio Analytics & Investment Tracker

**Portfyl** (formerly Snowball Analytics) is a self-hosted portfolio management
application that lets you track investments across multiple portfolios and
**platforms** — Trading 212, Interactive Brokers (IBKR), and Polymarket — compute
performance and risk metrics, handle tax reports (Czech §4 exemption rules), track
options positions, dive into deep stock fundamentals, screen for ideas, project
forward dividend income, and ask an AI assistant about your portfolio — all
without sending your data to a third party.

Each portfolio belongs to a **platform**. The active platform tailors the UI: a
Trading 212 portfolio surfaces broker sync + the full stock research suite, an
IBKR portfolio adds options tracking, and a Polymarket portfolio shows prediction-
market positions. A landing page lets you pick the platform on entry.

**Live data via Yahoo Finance** (yfinance). **No API key required** for
market data — just start the backend and go.

---

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Set a stable `PORTFYL_ACCOUNT_FINGERPRINT_KEY` of at least 32 characters in the
root `.env` before connecting Trading 212. Do not rotate it while account
bindings exist; Portfyl deliberately fails closed when it cannot verify the
upstream account identity.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. The backend runs on
`http://localhost:8000` — the frontend dev server proxies `/api` requests
to it automatically.

### API docs

Once the backend is running: **http://localhost:8000/docs** (Swagger UI)

---

## Architecture

```
portfyl/
├── backend/                          # FastAPI + SQLAlchemy + SQLite + yfinance
│   ├── main.py                       # App entry, startup migrations, CORS, router wiring
│   ├── database.py                   # SQLAlchemy engine & session, DB migration (snowball.db → portfyl.db)
│   ├── models.py                     # ORM: Portfolio, Transaction, Watchlist, WatchlistItem,
│   │                                 #   Benchmark, BenchmarkComponent, BrokerConnection,
│   │                                 #   OptionsTrade, PolymarketPosition, TradeNote, DiscordWebhook,
│   │                                 #   BrokerBalance, AppSetting
│   ├── schemas.py                    # Pydantic request/response schemas
│   ├── cache.py                      # Thread-safe in-process TTL cache for yfinance responses
│   ├── fx.py                         # Historical FX rate snapshots (currency → CZK per txn date)
│   ├── ticker_map.py                 # Yahoo Finance ticker fallback remapping
│   ├── requirements.txt
│   ├── routers/
│   │   ├── portfolio.py              # Transaction CRUD, CSV import (T212 + native),
│   │   │                             #   holdings engine (FIFO avg-cost), portfolio summary
│   │   ├── portfolios.py             # Multi-portfolio CRUD, require_portfolio dependency
│   │   ├── market.py                 # Stock search, quotes, history, fundamentals (5y financials,
│   │   │                             #   18+ ratios, DCF with WACC sensitivity, analyst estimates,
│   │   │                             #   ownership, insider txns), **stock screener**
│   │   ├── analytics.py              # Time-weighted return (Modified-Dietz), XIRR, risk metrics
│   │   │                             #   (Sharpe, Sortino, max drawdown, VaR, beta, alpha),
│   │   │                             #   tax report (Czech §4: time test, value test, 40M cap),
│   │   │                             #   sector/country/asset-type breakdown, correlation matrix
│   │   ├── benchmarks.py             # Benchmark CRUD + portfolio-vs-benchmark comparison
│   │   │                             #   (active return, tracking error, info ratio, capture ratios)
│   │   ├── broker.py                 # Trading 212 sync (orders, dividends, split adjustment,
│   │   │                             #   corporate-action pair cleanup, ticker normalization)
│   │   ├── watchlists.py             # Watchlist CRUD with live quotes (parallel fetch)
│   │   ├── ibkr.py                    # Interactive Brokers Flex Query import + sync
│   │   ├── options.py                 # Options positions, greeks, expiry tracking
│   │   ├── polymarket.py             # Polymarket prediction-market positions
│   │   ├── discord.py                # Discord webhook notifications
│   │   ├── notes.py                   # Per-trade / per-ticker notes
│   │   └── assistant.py               # AI portfolio assistant (LLM chat over your data)
│   └── tests/                        # 54 tests across 7 modules (holdings, FIFO, tax,
│                                     #   broker, cache, FX, screener)
├── frontend/                         # React 18 + Vite + Tailwind CSS + Recharts + React Query
│   ├── src/
│   │   ├── App.jsx                   # Routes, theme/palette/portfolio/currency providers, AutoLoad
│   │   ├── api.js                    # Axios client with portfolio-scoped interceptor
│   │   ├── components/
│   │   │   ├── Sidebar.jsx           # Nav, theme picker, accent palette, currency toggle
│   │   │   ├── PortfolioSwitcher.jsx # Multi-portfolio dropdown
│   │   │   ├── MetricCard.jsx        # Reusable stat card
│   │   │   ├── StockDetail.jsx       # Full-stock detail modal (fundamentals, valuation, insider txns)
│   │   │   ├── BreakdownChart.jsx    # Donut / pie chart for allocation
│   │   │   ├── AutoLoad.jsx          # Background prefetcher for instant navigation
│   │   │   └── ui/                   # Toast, SegmentedControl, ErrorState, ConfirmDialog
│   │   └── pages/
│   │       ├── PlatformLanding.jsx   # Entry screen — pick platform (T212 / IBKR / Polymarket)
│   │       ├── Dashboard.jsx         # Summary cards, holdings table, performance sparkline
│   │       ├── Allocation.jsx        # Sector/country/asset-type breakdown pie charts
│   │       ├── Transactions.jsx      # Transaction list + add/delete
│   │       ├── Import.jsx            # CSV upload (T212 + native), drag-and-drop
│   │       ├── Dividends.jsx         # Historical dividend calendar + YTD forecast chart
│   │       ├── Analytics.jsx         # Performance charts, risk metrics, benchmark comparison
│   │       ├── Options.jsx           # Options positions (IBKR platform)
│   │       ├── Polymarket.jsx        # Prediction-market positions (Polymarket platform)
│   │       ├── TaxReport.jsx         # Czech tax report with per-year breakdown
│   │       ├── Search.jsx            # Stock search autocomplete
│   │       ├── Stock.jsx             # Full stock detail page (fundamentals, TTM charts, valuation)
│   │       ├── Watchlists.jsx        # Watchlist management with live quotes
│   │       ├── Screener.jsx          # **Stock screener with filters + sortable table**
│   │       ├── Assistant.jsx         # AI portfolio assistant chat
│   │       └── Settings.jsx          # Broker connection, theme, data management
│   └── package.json
├── sample_portfolio.csv              # Example CSV for testing imports
└── start.bat                         # Windows launcher
```

---

## Key Features

### Portfolio Management
- **Multi-portfolio** — track separate accounts (taxable, IRA, joint) with independent transaction sets
- **Transaction CRUD** — buy/sell/dividend with manual entry or CSV import
- **CSV Import** — native format (date, ticker, type, shares, price) **and** Trading 212 export format
- **Trading 212 Sync** — connect via API key, auto-fetch orders and dividends, split-adjustment detection, corporate-action pair cleanup
- **Background auto-sync** — opt-in per broker connection (T212 + IBKR); syncs on a configurable schedule (daily at a set time — default 02:00 Europe/Prague — or every N hours; Settings → Auto-sync schedule) and announces imports on Discord
- **Holdings Engine** — FIFO avg-cost cost basis, realized/unrealized P&L, closed positions with "what if held" P&L

### Performance & Risk
- **Time-weighted return** (Modified-Dietz TWR) — daily returns robust to external cashflows
- **Money-weighted return** (XIRR) — lifetime internal rate of return
- **CAGR** — compound annual growth rate
- **Risk metrics** — Sharpe ratio, Sortino ratio, max drawdown (with recovery date), Value at Risk, win rate
- **Benchmark comparison** — preset indices (S&P 500, NASDAQ 100, Dow Jones, STOXX 50, MSCI World/ACWI, 60/40 basket) + custom baskets; beta, alpha, tracking error, up/down capture
- **Correlation matrix** — pairwise daily return correlations between held tickers
- **Sector/country/asset-type breakdown** — allocation pie charts

### Stock Research
- **Fundamentals** — 5 years of annual + quarterly revenue, net income, EPS, FCF, debt, cash with YoY growth and CAGR
- **Valuation ratios** — P/E, forward P/E, P/S, P/B, P/FCF, EV/EBITDA, EV/Revenue, D/E, current/quick ratio, ROE, ROA, margins, dividend yield, payout ratio
- **Sector averages** — median ratios across 10 representative large-cap constituents per GICS sector
- **Fair value** — P/E multiple (current + sector median), EV/EBITDA (current + sector median), 2-stage FCF DCF with WACC sensitivity grid
- **Analyst consensus** — buy/sell/hold counts, price targets, upside
- **Ownership** — institutional holders table, insider holdings %, insider transactions
- **Stock screener** — filter full index universes (S&P 500, NASDAQ-100, Dividend Aristocrats, tech mega-caps) by P/E, forward P/E, P/B, P/S, div yield, market cap, ROE, net margin, sector; sortable by any metric; rows cached for an hour so re-filtering is instant

### Tax (Czech Republic)
- **§4 time test** — 3-year holding period exemption, per-lot tracking
- **Value test** — 100,000 CZK gross proceeds threshold
- **40M cap** — 40,000,000 CZK annual cap on time-test exemption (effective 2024)
- **Per-year summary** — exempt vs. taxable gain breakdown
- **Unrealized gains** — lot-level view with days to exemption

### Dividends
- **Historical dividends** — past payments, annual income, yield per holding
- **Forward dividend calendar** — next ex-date, pay date, amount per share, frequency per holding
- **Monthly projection** — 12-month forward chart with estimated income per month
- **Annual estimate** — total projected dividend income for the next 12 months
- **Ex-date notifications** — Discord digest when a holding's ex-dividend date is within 3 days (each dividend announced once)

### FX & Multi-Currency
- Per-transaction FX snapshot (currency → CZK at txn date) for accurate CZK cost basis
- Live FX toggle (USD / CZK) — all holdings, performance, and metrics re-denominated
- Yahoo Finance real-time rates

### UI/UX
- **3 accent palettes** (green, blue, purple)
- **Dark / light / system** theme
- **Portfolio switching** with full cache invalidation
- **Background data prefetching** for instant page navigation
- **Stock detail modal** — click any ticker for deep-dive
- **Responsive** — sidebar nav with collapsible theme/currency controls

---

## Testing

The backend has **149 tests** across 14 modules:

| Module | Covers |
|---|---|
| `test_portfolio.py` | Holdings aggregation, FIFO P&L, closed positions, summary, native-currency prices |
| `test_analytics.py` | Capital gains (multi-lot FIFO, long/short term), Czech tax (value test, time test, 40M cap) |
| `test_broker.py` | T212 ticker normalization, sync dedup (CSV vs API, base-ticker, history cutoff), CZK settlement |
| `test_cash_ledger.py` / `test_cash_api.py` | Cash model: signed cash, balances, accrued interest, CRUD, guards |
| `test_alerts.py` | Price alerts: CRUD, crossing semantics, trigger/re-arm, no-data handling |
| `test_jobs.py` | Background jobs: broker auto-sync (opt-in, notifications, failure isolation), dividend ex-date digests (window, dedup, flags) |
| `test_currency_and_history.py` | FX exposure breakdown, cash history series |
| `test_t212_import.py` | CSV import legs, settlement cash, display-currency conversion, interest accrual |
| `test_cache.py` / `test_fx.py` | TTL cache semantics; ticker map and FX shortcuts |
| `test_day_change.py` | Day-change and movers calculations |
| `test_market.py` | Screener: `_in_range`, full preset universes, row cache, custom tickers |

```bash
cd backend
.venv\Scripts\python -m pytest tests/ -v
```

---

## Database

The project uses **SQLite** with SQLAlchemy. The database file starts as
`portfyl.db` (auto-migrated from `snowball.db` on first run). Startup
migrations handle:
- Adding `fx_to_czk` column to transactions
- Adding `portfolio_id` columns and indexes
- Creating the default portfolio
- Backfilling FX rates for legacy transactions
- Seeding preset benchmarks

---

## API Endpoints

All endpoints are documented live at **`/docs`** (Swagger) when the backend
is running. Key groups:

| Prefix | Router | Description |
|---|---|---|
| `/api/portfolios` | `portfolios.py` | List, create, update, delete portfolios |
| `/api/portfolio` | `portfolio.py` | Transactions, holdings, summary, CSV import |
| `/api/market` | `market.py` | Search, quotes, history, fundamentals, **screener** |
| `/api/analytics` | `analytics.py` | Performance, risk, tax report, sector breakdown, correlation |
| `/api/analytics/benchmarks` | `benchmarks.py` | Benchmark CRUD, comparison |
| `/api/alerts` | `alerts.py` | Price alerts (CRUD, manual check; background poller fires Discord notifications) |
| `/api/broker` | `broker.py` | Trading 212 connect/disconnect/sync |
| `/api/ibkr` | `ibkr.py` | Interactive Brokers Flex Query import/sync |
| `/api/options` | `options.py` | Options positions, greeks, expiry tracking |
| `/api/polymarket` | `polymarket.py` | Polymarket prediction-market positions |
| `/api/assistant` | `assistant.py` | AI portfolio assistant (LLM chat) |
| `/api/notes` | `notes.py` | Per-trade / per-ticker notes |
| `/api/discord` | `discord.py` | Discord webhook notifications |
| `/api/watchlists` | `watchlists.py` | Watchlist CRUD with live quotes |

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, yfinance, pandas, numpy, httpx
- **Frontend:** React 18, Vite 6, Tailwind CSS 3, Recharts, TanStack React Query 5, React Router 7, Axios, Lucide icons
- **Testing:** pytest, unittest.mock, in-memory SQLite

---

## License

MIT
