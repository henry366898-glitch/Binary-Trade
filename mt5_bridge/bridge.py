"""
MT5 Bridge — run this on the Windows machine where MetaTrader 5 is installed.

Connects to the MT5 terminal, polls ticks for configured symbols, and pushes
each tick as JSON to every connected WebSocket client.

Behaviour:
  • Waits for MT5 terminal to open — keeps retrying instead of crashing.
  • Reconnects automatically if MT5 becomes unavailable mid-run.
  • WebSocket server stays up even while MT5 is reconnecting.

Config (env vars or .env file):
    MT5_LOGIN       broker account number (optional if already logged in)
    MT5_PASSWORD    broker password       (optional)
    MT5_SERVER      broker server name    (optional)
    MT5_PATH        full path to terminal64.exe (optional)
    SYMBOLS         comma-separated list  (default: EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD,ETHUSD)
    TICK_POLL_MS    polling interval ms   (default: 250)
    BRIDGE_HOST     bind host             (default: 0.0.0.0)
    BRIDGE_PORT     bind port             (default: 9000)
"""

import asyncio
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SYMBOLS      = [s.strip() for s in os.getenv("SYMBOLS", "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD,ETHUSD").split(",")]
POLL_MS      = int(os.getenv("TICK_POLL_MS", "250"))
BRIDGE_HOST  = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT  = int(os.getenv("BRIDGE_PORT", "9000"))
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0") or "0")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
MT5_PATH     = os.getenv("MT5_PATH", "")

# ── MT5 import ─────────────────────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
except ImportError:
    logger.critical("MetaTrader5 package not found. Run: pip install MetaTrader5")
    sys.exit(1)

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    logger.critical("websockets package not found. Run: pip install websockets")
    sys.exit(1)

# ── Shared state ───────────────────────────────────────────────────────────────
_clients: set["WebSocketServerProtocol"] = set()
_mt5_ready = False  # True while MT5 is connected and ticking


# ── MT5 helpers ────────────────────────────────────────────────────────────────
def _try_connect_mt5() -> bool:
    """Single connection attempt. Returns True on success."""
    kwargs: dict = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if MT5_LOGIN:
        kwargs.update({"login": MT5_LOGIN, "password": MT5_PASSWORD, "server": MT5_SERVER})

    if not mt5.initialize(**kwargs):
        logger.error(f"MT5 init failed: {mt5.last_error()}")
        return False

    for sym in SYMBOLS:
        if not mt5.symbol_select(sym, True):
            logger.warning(f"Could not select symbol {sym} — check broker symbol name")

    info = mt5.account_info()
    logger.info(f"MT5 connected ✓  account={info.login if info else 'unknown'}")
    _fill_tf_map()
    return True


async def _wait_for_mt5() -> None:
    """
    Block until MT5 terminal is open and accepting connections.
    Retries with increasing backoff (5 s → 60 s).
    The WebSocket server is already running during this wait.
    """
    global _mt5_ready
    backoff = 5
    while True:
        logger.info("Waiting for MT5 terminal to open…")
        if _try_connect_mt5():
            _mt5_ready = True
            return
        logger.info(f"MT5 not ready — retrying in {backoff}s  "
                    f"(make sure MetaTrader 5 is open and logged in)")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


# ── Timeframe map ──────────────────────────────────────────────────────────────
_TF_MAP = {
    1:  None,   # filled after mt5 import
    5:  None,
    15: None,
    60: None,
}


def _fill_tf_map():
    _TF_MAP[1]  = mt5.TIMEFRAME_M1
    _TF_MAP[5]  = mt5.TIMEFRAME_M5
    _TF_MAP[15] = mt5.TIMEFRAME_M15
    _TF_MAP[60] = mt5.TIMEFRAME_H1


async def _handle_history_request(ws: "WebSocketServerProtocol", data: dict):
    """Respond to a history_request message with real MT5 OHLCV data."""
    if not _mt5_ready:
        return
    symbol    = data.get("symbol", "EURUSD")
    tf_min    = int(data.get("timeframe", 1))
    count     = int(data.get("count", 300))
    tf        = _TF_MAP.get(tf_min, mt5.TIMEFRAME_M1)

    try:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    except Exception as e:
        logger.warning(f"History request failed for {symbol}/{tf_min}m: {e}")
        return

    if rates is None or len(rates) == 0:
        logger.warning(f"No history data for {symbol}/{tf_min}m")
        return

    candles = [
        {
            "time":  int(r["time"]),
            "open":  float(r["open"]),
            "high":  float(r["high"]),
            "low":   float(r["low"]),
            "close": float(r["close"]),
        }
        for r in rates
    ]
    payload = json.dumps({
        "type":      "history",
        "symbol":    symbol,
        "timeframe": tf_min,
        "candles":   candles,
    })
    try:
        await ws.send(payload)
        logger.info(f"Sent {len(candles)} candles for {symbol}/{tf_min}m")
    except Exception:
        pass


# ── WebSocket server ───────────────────────────────────────────────────────────
async def _client_handler(ws: "WebSocketServerProtocol"):
    _clients.add(ws)
    addr = ws.remote_address
    logger.info(f"Client connected: {addr}  (total: {len(_clients)})")
    try:
        # Handle incoming messages (history requests) while keeping connection open
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "history_request":
                asyncio.create_task(_handle_history_request(ws, data))
    except Exception:
        pass
    finally:
        _clients.discard(ws)
        logger.info(f"Client disconnected: {addr}  (total: {len(_clients)})")


async def _send(ws: "WebSocketServerProtocol", payload: str):
    try:
        await ws.send(payload)
    except Exception:
        _clients.discard(ws)


# ── Tick loop ──────────────────────────────────────────────────────────────────
async def _tick_loop():
    """
    Poll MT5 every POLL_MS ms and broadcast ticks.
    If MT5 drops mid-run, shuts down and waits for reconnect.
    """
    global _mt5_ready
    interval = POLL_MS / 1000.0
    consecutive_failures = 0
    MAX_FAILURES = len(SYMBOLS) * 20  # ~5 seconds of all-symbol failures

    while True:
        if not _mt5_ready:
            await asyncio.sleep(1)
            continue

        any_ok = False
        for sym in SYMBOLS:
            tick = mt5.symbol_info_tick(sym)
            if tick is None:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    logger.error("MT5 stopped responding — will reconnect")
                    _mt5_ready = False
                    mt5.shutdown()
                    consecutive_failures = 0
                    # Kick off reconnect without blocking the event loop
                    asyncio.create_task(_wait_for_mt5())
                    break
                continue

            consecutive_failures = 0
            any_ok = True

            payload = json.dumps({
                "type":   "tick",          # ← required by backend + test app
                "symbol": sym,
                "bid":    tick.bid,
                "ask":    tick.ask,
                "time":   tick.time_msc / 1000.0 if tick.time_msc else float(tick.time),
            })

            if _clients:
                await asyncio.gather(
                    *[_send(c, payload) for c in set(_clients)],
                    return_exceptions=True,
                )

        await asyncio.sleep(interval)


# ── Entry point ────────────────────────────────────────────────────────────────
async def main():
    logger.info(f"Bridge starting on ws://{BRIDGE_HOST}:{BRIDGE_PORT}")
    logger.info(f"Symbols: {SYMBOLS}   poll: {POLL_MS}ms")
    logger.info("MetaTrader 5 terminal must be open and logged in on this machine.")

    async with websockets.serve(_client_handler, BRIDGE_HOST, BRIDGE_PORT):
        logger.info(f"WebSocket server ready — clients can connect now")
        # Start MT5 connection in background (doesn't block the WS server)
        asyncio.create_task(_wait_for_mt5())
        # Run the tick loop forever
        await _tick_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bridge stopped.")
        if _mt5_ready:
            mt5.shutdown()
