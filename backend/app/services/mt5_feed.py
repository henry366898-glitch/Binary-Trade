"""
MT5 market data feed service.

Connects to a running MetaTrader 5 terminal and polls tick data for configured
symbols. Falls back to a deterministic random-walk simulator if MT5 is not
available — useful for development on macOS/Linux where MT5 doesn't run.
"""
import asyncio
import logging
import math
import random
import time
from typing import Callable

from app.config import settings

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not installed — using mock data feed")


class PriceFeed:
    """Async price feed. Holds latest tick per symbol and notifies subscribers."""

    def __init__(self):
        self.latest: dict[str, dict] = {}
        self.history: dict[str, list[dict]] = {s: [] for s in settings.SYMBOLS}
        self.subscribers: list[Callable] = []
        self._running = False
        self._use_mock = False

    # ----- subscriber pattern -----
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

    # ----- MT5 connection -----
    def _connect_mt5(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        try:
            kwargs = {}
            if settings.MT5_PATH:
                kwargs["path"] = settings.MT5_PATH
            if settings.MT5_LOGIN:
                kwargs.update({
                    "login": settings.MT5_LOGIN,
                    "password": settings.MT5_PASSWORD,
                    "server": settings.MT5_SERVER,
                })
            if not mt5.initialize(**kwargs):
                logger.error(f"MT5 init failed: {mt5.last_error()}")
                return False

            for sym in settings.SYMBOLS:
                if not mt5.symbol_select(sym, True):
                    logger.warning(f"Could not select symbol {sym}")
            logger.info(f"MT5 connected. Account: {mt5.account_info()}")
            return True
        except Exception as e:
            logger.error(f"MT5 connect error: {e}")
            return False

    # ----- price retrieval -----
    def _get_tick_mt5(self, symbol: str) -> dict | None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "time": tick.time_msc / 1000.0 if tick.time_msc else tick.time,
        }

    # ----- mock feed (random walk) -----
    _mock_prices: dict[str, float] = {
        "EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 149.50,
        "XAUUSD": 2350.0, "BTCUSD": 67000.0, "ETHUSD": 3200.0,
    }

    def _get_tick_mock(self, symbol: str) -> dict:
        base = self._mock_prices.get(symbol, 1.0)
        # geometric brownian motion-ish step
        vol = 0.0008 if symbol in ("BTCUSD", "ETHUSD") else 0.0001
        drift = (random.random() - 0.5) * vol * base
        # add a slight sine wave for visual interest
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

    # ----- main loop -----
    async def start(self):
        if self._running:
            return
        self._running = True

        if not self._connect_mt5():
            logger.warning("Running with MOCK data feed (MT5 unavailable)")
            self._use_mock = True

        logger.info(f"Price feed started. Symbols: {settings.SYMBOLS}")
        interval = settings.TICK_POLL_MS / 1000.0

        while self._running:
            for sym in settings.SYMBOLS:
                if self._use_mock:
                    tick = self._get_tick_mock(sym)
                else:
                    tick = self._get_tick_mt5(sym)
                    # per-symbol fallback: if MT5 doesn't expose this symbol
                    # (common for crypto on forex brokers), use the mock feed
                    # for that symbol only — keeps the demo populated.
                    if tick is None:
                        tick = self._get_tick_mock(sym)
                if tick is None:
                    continue
                self.latest[sym] = tick
                # keep last 500 ticks per symbol
                hist = self.history.setdefault(sym, [])
                hist.append(tick)
                if len(hist) > 500:
                    del hist[:-500]
                await self._broadcast(tick)
            await asyncio.sleep(interval)

    async def stop(self):
        self._running = False
        if not self._use_mock and MT5_AVAILABLE:
            mt5.shutdown()

    def get_price(self, symbol: str) -> float | None:
        """Mid-price for trade settlement."""
        t = self.latest.get(symbol)
        if not t:
            return None
        return (t["bid"] + t["ask"]) / 2

    def get_candles(self, symbol: str, timeframe_min: int = 1, count: int = 100) -> list[dict]:
        """Historical candles. From MT5 if available, else synthesized from tick history."""
        if not self._use_mock and MT5_AVAILABLE:
            tf_map = {1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15, 60: mt5.TIMEFRAME_H1}
            tf = tf_map.get(timeframe_min, mt5.TIMEFRAME_M1)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is not None:
                return [
                    {"time": int(r["time"]), "open": float(r["open"]),
                     "high": float(r["high"]), "low": float(r["low"]),
                     "close": float(r["close"])}
                    for r in rates
                ]
        # synthesize from tick history
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

        # If tick history doesn't cover enough buckets (very common at larger timeframes for
        # mock-fallback symbols), backfill synthetic candles so the chart isn't blank.
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
            anchor_time = (now // bucket) * bucket + bucket  # one bucket ahead so the loop fills up to now
        vol = 0.0015 if symbol in ("BTCUSD", "ETHUSD") else 0.0003
        synth: list[dict] = []
        cursor = base
        for i in range(needed, 0, -1):
            slot = anchor_time - i * bucket
            # small random walk; close of bucket i is open of bucket i+1
            drift = (random.random() - 0.5) * vol * cursor
            open_p = cursor
            close_p = max(0.0, cursor + drift)
            hi = max(open_p, close_p) + abs(random.random() * vol * cursor / 2)
            lo = min(open_p, close_p) - abs(random.random() * vol * cursor / 2)
            synth.append({"time": slot, "open": round(open_p, 5), "high": round(hi, 5), "low": round(lo, 5), "close": round(close_p, 5)})
            cursor = close_p
        return synth + real


# global singleton
price_feed = PriceFeed()
