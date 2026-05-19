# Quantum Trade — Educational Binary Options Platform

> ⚠️ **EDUCATIONAL PROJECT ONLY.** This is a simulation built for learning purposes. It uses virtual money. Real binary options trading is high-risk — regulators have documented that 74–89% of retail traders lose money, and it's banned for retail clients in the EU, UK, US, Australia, and other jurisdictions.

A full-stack binary options trading simulator with real-time MetaTrader 5 price integration. Built to demonstrate the architecture and engineering challenges of building a trading platform.

## What this project demonstrates

- **Real-time market data integration** with MetaTrader 5 via the official Python library
- **WebSocket price streaming** from backend to many concurrent clients
- **Async settlement engine** that processes expired trades against live prices
- **JWT authentication** with bcrypt password hashing
- **Async SQLAlchemy** with SQLite for persistence
- **Live candlestick charting** with TradingView's lightweight-charts library
- **React + Zustand** state management with optimistic UI updates
- **Mock data fallback** so you can develop without MT5 running

## Architecture

```
┌────────────────────┐
│  MT5 Terminal      │  (Windows or Wine, demo account)
│  (any broker)      │
└─────────┬──────────┘
          │ MetaTrader5 Python lib (polling)
          ▼
┌────────────────────────────────────────┐
│  FastAPI Backend                       │
│  ├── PriceFeed     (async polling)     │
│  ├── Settlement    (async loop, 1Hz)   │
│  ├── /api/auth     (register / login)  │
│  ├── /api/trades   (place / list)      │
│  ├── /api/market   (symbols / candles) │
│  └── /api/market/stream  (WebSocket)   │
└─────────┬──────────────────────────────┘
          │ REST + WebSocket
          ▼
┌────────────────────────────────────────┐
│  React Frontend (Vite)                 │
│  ├── Chart        (lightweight-charts) │
│  ├── SymbolList   (live prices)        │
│  ├── TradeTicket  (UP/DOWN, amount)    │
│  └── TradesList   (countdown + P&L)    │
└────────────────────────────────────────┘
```

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **MetaTrader 5** (optional — only needed for real data)
  - Windows: install from your broker, log in to a **demo** account (free, no real money)
  - macOS/Linux: either run MT5 under Wine, or skip it — the backend will fall back to a simulated price feed automatically

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in `backend/`:

```env
# Only needed if you have MT5 running. Leave blank to use mock feed.
MT5_LOGIN=12345678
MT5_PASSWORD=your_demo_password
MT5_SERVER=YourBroker-Demo
# Optional path to terminal:
# MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

JWT_SECRET=replace-with-a-long-random-string
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for the auto-generated API documentation.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173.

## How to use

1. Register a new account (you get $10,000 in virtual funds).
2. Pick a symbol from the left sidebar.
3. Set your trade amount and expiry time.
4. Click **UP** if you think the price will rise, **DOWN** if you think it will fall.
5. Wait for expiry. If you're right, you win 85% of your stake. If wrong, you lose your stake.
6. Watch your P&L, win rate, and balance update in real time.

## Project layout

```
binary-platform/
├── backend/
│   ├── app/
│   │   ├── config.py           # Settings (MT5 credentials, symbols, payout)
│   │   ├── main.py             # FastAPI app + lifespan
│   │   ├── models/
│   │   │   ├── db.py           # SQLAlchemy models
│   │   │   └── schemas.py      # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── auth.py         # /api/auth/register, /api/auth/login
│   │   │   ├── market.py       # /api/market/* + WebSocket
│   │   │   └── trades.py       # /api/trades/*
│   │   └── services/
│   │       ├── auth.py         # JWT + bcrypt helpers
│   │       ├── db.py           # Async SQLAlchemy session
│   │       ├── mt5_feed.py     # MT5 connector with mock fallback
│   │       └── settlement.py   # Trade settlement engine
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── main.jsx
    │   ├── styles.css
    │   ├── components/
    │   │   ├── AuthScreen.jsx
    │   │   ├── Chart.jsx
    │   │   ├── SymbolList.jsx
    │   │   ├── TradeTicket.jsx
    │   │   └── TradesList.jsx
    │   └── lib/
    │       ├── api.js          # REST + WebSocket client
    │       └── store.js        # Zustand store
    ├── index.html
    ├── package.json
    └── vite.config.js
```

## How the settlement engine works

When a user places a trade, the backend:

1. Validates the request and checks the user has sufficient balance.
2. Gets the **current mid-price** from MT5 as the entry price.
3. Deducts the stake from the user's balance immediately.
4. Creates a `Trade` record with status `OPEN` and an `expires_at` timestamp.

A separate **settlement loop** runs every 1 second:

1. Queries all `OPEN` trades where `expires_at <= now`.
2. For each trade, fetches the current MT5 price as the exit price.
3. Compares: if `direction == UP` and `exit > entry`, the user wins. Same for DOWN.
4. On a win: credits the user with stake + (stake × payout_rate). On a loss: stake is already gone.
5. Marks the trade as `WON` or `LOST` with the realized profit.

## What's intentionally NOT included (and why)

This is an educational simulator. A real platform would also need:

- **Regulatory licensing** (FCA, CySEC, etc.) — see notes in `docs/`
- **KYC/AML verification** — Onfido, Sumsub, etc.
- **Payment processing** — high-risk acquirers, crypto on-ramps
- **Risk management** — exposure limits, hedging with liquidity providers
- **Fraud detection** — bot detection, multi-account detection, geolocation
- **Customer support** — ticketing, live chat
- **Affiliate/IB system** — typical driver of new user acquisition
- **Mobile apps** — iOS and Android with native charting
- **Compliance reporting** — trade reporting, transaction monitoring
- **High availability** — multi-region, failover, disaster recovery

These are the parts where most binary options startups actually fail — not the technology.

## Educational extensions

Want to take this further as a learning project? Try adding:

1. **Strategy backtester** — let users replay historical candles and test rules
2. **Random vs informed simulation** — show that random trading converges to losing due to the 85% payout asymmetry (a 50% win rate produces a 7.5% loss per trade on average)
3. **Leaderboard** — top performers (often suspicious patterns emerge)
4. **Indicators** — RSI, MACD, Bollinger Bands on the chart
5. **Risk warnings** — UI nudges when users chase losses (loss-chasing detection)
6. **Trade journal** — let users tag and review trades
7. **Multi-timeframe charts** — 1m, 5m, 15m, 1h
8. **Educational mode** — pop-ups explaining why a strategy failed

## A note on responsibility

If you're using this as a coursework project, an excellent angle for your writeup or presentation is the **statistical inevitability of retail losses** in binary options. With an 85% payout, a trader needs a **>54% win rate just to break even** (because losses cost 100% and wins pay 85%). Real markets in short timeframes are essentially random, so 50% is the natural baseline. This is why regulators ban it.

Building this platform is a great way to internalize *why* the math doesn't work — not to build a real product.

## License

MIT, with the strong recommendation that you do not deploy this as a real-money platform.
