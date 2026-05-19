# Build Order & Learning Notes

If you're using this as a learning project, here's the order I'd suggest building things in. Each step is a checkpoint where you can run, test, and demo something working.

## Phase 1 — Core data plumbing (Days 1–3)

1. **Set up the backend skeleton** (`config.py`, `main.py`, FastAPI hello world)
2. **Mock price feed** (`mt5_feed.py` with only the mock branch) — get random walks broadcasting on a 250ms interval
3. **WebSocket stream endpoint** — connect a browser, see ticks in DevTools
4. **Frontend skeleton** (Vite + React, single page that connects WebSocket and prints ticks)

✓ **Checkpoint:** prices flowing end-to-end.

## Phase 2 — Real MT5 integration (Days 3–5)

5. Install MT5 + open a demo account at any broker (XM, IC Markets, Exness — all free)
6. Wire up the real MT5 branch in `mt5_feed.py`
7. Verify ticks match what you see in the MT5 terminal
8. Add the `/api/market/candles` endpoint and verify with curl

✓ **Checkpoint:** real broker data streaming through your backend.

## Phase 3 — Chart UI (Days 5–7)

9. Install `lightweight-charts`, render an empty chart
10. Load historical candles on mount
11. Update the live candle on each tick
12. Add the symbol list sidebar — clicking switches the chart

✓ **Checkpoint:** professional-looking chart with live ticks.

## Phase 4 — Auth & persistence (Days 7–9)

13. Add SQLAlchemy + Alembic (or just `Base.metadata.create_all`)
14. Build register/login endpoints with JWT
15. Add the AuthScreen on the frontend
16. Protect trade endpoints with `Depends(get_current_user)`

✓ **Checkpoint:** users can sign up, log in, and see their balance.

## Phase 5 — Trading engine (Days 9–12)

17. `POST /api/trades` — validate, lock entry price, deduct stake
18. Settlement loop — settle expired trades against current price
19. `GET /api/trades` and `/api/trades/stats`
20. Frontend trade ticket + countdown + trades list

✓ **Checkpoint:** a complete round trip: place trade → wait → see win or loss.

## Phase 6 — Polish (Days 12–14)

21. Price flash animations on tick direction
22. Toast notifications on trade placement
23. Better mobile responsive layout
24. The educational disclaimer / "why this doesn't work" page

## Things I learned building this

**Decimal precision matters.** Forex prices have 5 decimal places, JPY pairs have 3, gold has 2. Your comparison logic must handle that. I use `abs(exit - entry) < 1e-9` for the tie case.

**Timestamps are the silent killer.** MT5 returns server time in UTC, but server time differs from broker to broker (most use GMT+2/+3). Always store UTC server-side, convert at the edge.

**WebSocket backpressure.** If a client is slow, the queue fills and you have to drop ticks. The pattern in `market.py` uses a bounded `asyncio.Queue` and drops on full — for ticks this is correct (latest matters more than completeness).

**Settlement should be idempotent.** If your worker crashes mid-settlement, restart should not double-credit. Use a state machine (`OPEN` → `WON`/`LOST`) and only credit when transitioning from `OPEN`.

**The MetaTrader5 library is synchronous.** It blocks the asyncio loop if you're not careful. For a school project the poll-and-broadcast pattern is fine, but production-scale you'd want `run_in_executor` or a separate process.

## What to write in your project report

If you're submitting this for coursework, the most interesting things to write about are:

1. **The architecture decision matrix** — why FastAPI + async over Django? Why SQLite over Postgres? Why WebSocket over Server-Sent Events?
2. **The settlement engine** — explain the state transitions, idempotency, and why you used a separate loop vs settling on price tick.
3. **The mathematics of the payout asymmetry** — with 85% payout, break-even win rate is 1/(1+0.85) ≈ 54.05%. Plot what happens over 1,000 random trades.
4. **What you intentionally left out** — KYC, payment processing, regulatory compliance. This shows you understand the real complexity.
5. **The ethical framing** — a great talking point for your viva is *why you would not build this for real*.
