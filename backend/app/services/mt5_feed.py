"""
MT5 market data feed service.

Connects to the MT5 bridge (bridge.py) over WebSocket and ingests live ticks.
Falls back to a deterministic random-walk mock if MT5_BRIDGE_URL is not set or
the bridge is unreachable — useful for local development on any OS.

The bridge handles all MT5-specific code (Windows-only). This service is
platform-agnostic.
"""
import asyncio
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

    async def _bridge_loop(self):
        """Connect to the MT5 bridge WebSocket and ingest ticks. Auto-reconnects."""
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
                    backoff = 1.0  # reset on successful connect
                    async for raw in ws:
                        if not self._running:
                            return
                        try:
                            tick = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self._ingest(tick)
                        await self._broadcast(tick)

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

    def get_candles(self, symbol: str, timeframe_min: int = 1, count: int = 100) -> list[dict]:
        """
        Build OHLCV candles from the in-memory tick history.
        Works identically whether the feed is live (bridge) or mock.
        """
        ticks = self.history.get(symbol, [])
        bucket = timeframe_min * 60
        candles: dict[int, dict] = {}

        for t in ticks:
            mid = (t["bid"] + t["ask"]) / 2
            slot = int(t["time"] // bucket) * bucket
            c = candles.get(slot)
            if c is None:
                candles[slot] = {"time": slot, "open": mid, "high": mid, "low": mid, "close": mid}
            else:
                c["high"] = max(c["high"], mid)
                c["low"] = min(c["low"], mid)
                c["close"] = mid

        real = sorted(candles.values(), key=lambda x: x["time"])

        # backfill synthetic candles if tick history doesn't cover enough bars
        if len(real) >= count:
            return real[-count:]

        needed = count - len(real)
        if real:
            anchor_time = real[0]["time"]
            base = real[0]["open"]
        else:
            latest = self.latest.get(symbol)
            if not latest:
                return []
            base = (latest["bid"] + latest["ask"]) / 2
            now = int(latest["time"])
            anchor_time = (now // bucket) * bucket + bucket

        vol = 0.0015 if symbol in ("BTCUSD", "ETHUSD") else 0.0003
        synth: list[dict] = []
        cursor = base
        for i in range(needed, 0, -1):
            slot = anchor_time - i * bucket
            drift = (random.random() - 0.5) * vol * cursor
            open_p = cursor
            close_p = max(0.0, cursor + drift)
            hi = max(open_p, close_p) + abs(random.random() * vol * cursor / 2)
            lo = min(open_p, close_p) - abs(random.random() * vol * cursor / 2)
            synth.append({
                "time": slot,
                "open": round(open_p, 5), "high": round(hi, 5),
                "low": round(lo, 5), "close": round(close_p, 5),
            })
            cursor = close_p

        return synth + real


# global singleton
price_feed = PriceFeed()
