"""
MT5 market data feed service.

Connects to the MT5 bridge (bridge.py) over WebSocket and ingests live ticks.
Falls back to a deterministic random-walk mock if MT5_BRIDGE_URL is not set or
the bridge is unreachable — useful for local development on any OS.

The bridge handles all MT5-specific code (Windows-only). This service is
platform-agnostic.
"""
import asyncio
import hashlib
import json
import logging
import math
import random
import time
from typing import Callable

import websockets

from app.config import settings

logger = logging.getLogger(__name__)


class PriceFeed:
    """Async price feed. Holds latest tick per symbol and notifies WebSocket subscribers."""

    def __init__(self):
        self.latest: dict[str, dict] = {}
        self.history: dict[str, list[dict]] = {s: [] for s in settings.SYMBOLS}
        self.subscribers: list[Callable] = []
        self._running = False
        self._use_mock = False
        # Historical OHLCV from MT5 bridge: {symbol: {timeframe_min: [candles]}}
        self._hist_cache: dict[str, dict[int, list[dict]]] = {}

    # ----- subscriber pattern (used by market WebSocket router) -----

    def subscribe(self, callback: Callable):
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    async def _broadcast(self, tick: dict):
        for cb in list(self.subscribers):
            try:
                await cb(tick)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

    # ----- tick ingestion (shared by bridge + mock paths) -----

    def _ingest(self, tick: dict):
        sym = tick.get("symbol")
        if sym not in settings.SYMBOLS:
            return
        self.latest[sym] = tick
        hist = self.history.setdefault(sym, [])
        hist.append(tick)
        if len(hist) > 500:
            del hist[:-500]

    # ----- bridge client loop -----

    async def _request_history(self, ws, symbol: str, timeframe: int, count: int = 500):
        """Ask the bridge for historical OHLCV candles for one symbol/timeframe."""
        try:
            await ws.send(json.dumps({
                "type":      "history_request",
                "symbol":    symbol,
                "timeframe": timeframe,
                "count":     count,
            }))
        except Exception as e:
            logger.warning(f"Failed to request history for {symbol}/{timeframe}m: {e}")

    def _store_history(self, symbol: str, timeframe: int, candles: list[dict]):
        """Cache MT5 historical candles for use in get_candles()."""
        if symbol not in self._hist_cache:
            self._hist_cache[symbol] = {}
        self._hist_cache[symbol][timeframe] = candles
        logger.info(f"Cached {len(candles)} MT5 candles for {symbol}/{timeframe}m")

    async def _bridge_loop(self):
        """Connect to MT5 bridge, request history, then stream live ticks."""
        url = settings.MT5_BRIDGE_URL
        backoff = 1.0

        while self._running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=10,
                ) as ws:
                    logger.info(f"Connected to MT5 bridge at {url}")
                    backoff = 1.0

                    # Request historical candles for every symbol × timeframe
                    # Stagger slightly so we don't flood the bridge
                    for sym in settings.SYMBOLS:
                        for tf in [1, 5, 15, 60]:
                            await self._request_history(ws, sym, tf, 500)
                            await asyncio.sleep(0.05)

                    async for raw in ws:
                        if not self._running:
                            return
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type")

                        if msg_type == "tick":
                            self._ingest(msg)
                            await self._broadcast(msg)

                        elif msg_type == "history":
                            sym      = msg.get("symbol", "")
                            tf       = int(msg.get("timeframe", 1))
                            candles  = msg.get("candles", [])
                            if sym and candles:
                                self._store_history(sym, tf, candles)

            except (OSError, websockets.exceptions.WebSocketException) as e:
                if not self._running:
                    return
                logger.warning(
                    f"Bridge connection lost ({type(e).__name__}: {e}). "
                    f"Retrying in {backoff:.0f}s…"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

            except asyncio.CancelledError:
                return

    # ----- mock feed (random walk, runs when bridge is not configured) -----

    _mock_prices: dict[str, float] = {
        "EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 149.50,
        "XAUUSD": 2350.0, "BTCUSD": 67000.0, "ETHUSD": 3200.0,
    }

    def _get_tick_mock(self, symbol: str) -> dict:
        base = self._mock_prices.get(symbol, 1.0)
        vol = 0.0008 if symbol in ("BTCUSD", "ETHUSD") else 0.0001
        drift = (random.random() - 0.5) * vol * base
        wave = math.sin(time.time() / 30) * 0.0002 * base
        new = base + drift + wave
        self._mock_prices[symbol] = new
        spread = new * 0.00005
        return {
            "symbol": symbol,
            "bid": round(new - spread / 2, 5),
            "ask": round(new + spread / 2, 5),
            "time": time.time(),
        }

    async def _mock_loop(self):
        interval = settings.TICK_POLL_MS / 1000.0
        while self._running:
            for sym in settings.SYMBOLS:
                tick = self._get_tick_mock(sym)
                self._ingest(tick)
                await self._broadcast(tick)
            await asyncio.sleep(interval)

    # ----- lifecycle -----

    async def start(self):
        if self._running:
            return
        self._running = True

        if settings.MT5_BRIDGE_URL:
            logger.info(f"MT5 bridge mode: {settings.MT5_BRIDGE_URL}")
            await self._bridge_loop()
        else:
            logger.warning("MT5_BRIDGE_URL not configured — using MOCK data feed")
            self._use_mock = True
            await self._mock_loop()

    async def stop(self):
        self._running = False

    # ----- public API (used by routers + settlement) -----

    def get_price(self, symbol: str) -> float | None:
        """Mid-price used for trade entry and settlement."""
        t = self.latest.get(symbol)
        if not t:
            return None
        return (t["bid"] + t["ask"]) / 2

    # decimal places per symbol category for synthetic candle rounding
    _DIGITS: dict[str, int] = {
        "USDJPY": 3,
        "XAUUSD": 2, "XAGUSD": 2,
        "BTCUSD": 2, "BTCUSDT": 2,
        "ETHUSD": 2, "ETHUSDT": 2,
    }

    @staticmethod
    def _sym_digits(symbol: str) -> int:
        for k, v in PriceFeed._DIGITS.items():
            if symbol.startswith(k[:3]):
                return v
        return 5

    @staticmethod
    def _make_rng(symbol: str, anchor_time: int) -> random.Random:
        """Deterministic RNG seeded by symbol + anchor so chart is stable between loads."""
        seed_bytes = f"{symbol}:{anchor_time}".encode()
        seed_int = int(hashlib.md5(seed_bytes).hexdigest(), 16) & 0xFFFF_FFFF
        return random.Random(seed_int)

    def get_candles(self, symbol: str, timeframe_min: int = 1, count: int = 100) -> list[dict]:
        """
        Build OHLCV candles, in priority order:
          1. Real MT5 historical candles from bridge (most accurate)
          2. Candles built from in-memory live ticks (since server started)
          3. Deterministic synthetic backfill (fallback when no bridge history)
        """
        bucket = timeframe_min * 60

        # ── Priority 1: MT5 real history from bridge ─────────────────────────
        mt5_hist = self._hist_cache.get(symbol, {}).get(timeframe_min)
        if mt5_hist:
            # Merge with any newer live-tick candles we've built
            ticks = self.history.get(symbol, [])
            live_candles: dict[int, dict] = {}
            for t in ticks:
                mid  = (t["bid"] + t["ask"]) / 2
                slot = int(t["time"] // bucket) * bucket
                c    = live_candles.get(slot)
                if c is None:
                    live_candles[slot] = {"time": slot, "open": mid, "high": mid, "low": mid, "close": mid}
                else:
                    c["high"]  = max(c["high"], mid)
                    c["low"]   = min(c["low"],  mid)
                    c["close"] = mid

            # Build combined list: MT5 history as base, live ticks override recent slots
            combined: dict[int, dict] = {c["time"]: c for c in mt5_hist}
            combined.update(live_candles)
            result = sorted(combined.values(), key=lambda x: x["time"])
            return result[-count:]

        # ── Priority 2: Build from in-memory live ticks ──────────────────────
        ticks = self.history.get(symbol, [])
        candles: dict[int, dict] = {}

        for t in ticks:
            mid = (t["bid"] + t["ask"]) / 2
            slot = int(t["time"] // bucket) * bucket
            c = candles.get(slot)
            if c is None:
                candles[slot] = {"time": slot, "open": mid, "high": mid, "low": mid, "close": mid}
            else:
                c["high"] = max(c["high"], mid)
                c["low"]  = min(c["low"],  mid)
                c["close"] = mid

        real = sorted(candles.values(), key=lambda x: x["time"])

        if len(real) >= count:
            return real[-count:]

        needed = count - len(real)

        if real:
            anchor_time = real[0]["time"]
            base        = real[0]["open"]
        else:
            latest = self.latest.get(symbol)
            if not latest:
                return []
            base        = (latest["bid"] + latest["ask"]) / 2
            now         = int(latest["time"])
            anchor_time = (now // bucket) * bucket

        digits = self._sym_digits(symbol)
        # volatility per candle: crypto/gold higher than forex
        vol = 0.0015 if symbol in ("BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT") else \
              0.0005 if symbol in ("XAUUSD", "XAGUSD") else 0.0002

        rng = self._make_rng(symbol, anchor_time)

        # ── Generate a backwards random walk ending exactly at `base` ────────
        # Walk backwards (needed+1 price points), then reverse so the final
        # point == base, guaranteeing the last synthetic candle closes at the
        # same price as the first real candle opens — no visible gap.
        pts = [base]
        for _ in range(needed):
            drift = (rng.random() - 0.5) * vol * pts[-1]
            pts.append(max(0.0001, pts[-1] + drift))
        pts.reverse()   # pts[0]=oldest, pts[needed]=base

        synth: list[dict] = []
        for i in range(needed):
            slot    = anchor_time - (needed - i) * bucket
            open_p  = pts[i]
            close_p = pts[i + 1]
            wick    = abs(rng.random()) * vol * open_p * 0.5
            hi      = max(open_p, close_p) + wick
            lo      = min(open_p, close_p) - wick
            synth.append({
                "time":  slot,
                "open":  round(open_p,  digits),
                "high":  round(hi,      digits),
                "low":   round(lo,      digits),
                "close": round(close_p, digits),
            })

        return synth + real


# global singleton
price_feed = PriceFeed()
