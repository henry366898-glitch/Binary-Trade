"""
MT5 Bridge — run this on the Windows machine where MetaTrader 5 is installed.

It connects to the MT5 terminal, polls ticks for configured symbols, and pushes
each tick as JSON to every connected WebSocket client.

Your FastAPI server (mt5_feed.py) connects to this bridge instead of importing
MetaTrader5 directly — so the FastAPI app can run on any OS.

Usage:
    python bridge.py

Config via environment variables (or a .env file in this directory):
    MT5_LOGIN         broker account number (optional)
    MT5_PASSWORD      broker password (optional)
    MT5_SERVER        broker server name (optional)
    MT5_PATH          path to terminal64.exe (optional)
    SYMBOLS           comma-separated list  (default: EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD,ETHUSD)
    TICK_POLL_MS      polling interval in ms (default: 250)
    BRIDGE_HOST       bind host (default: 0.0.0.0)
    BRIDGE_PORT       bind port (default: 9000)
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

# ---------- Config ----------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional

SYMBOLS     = os.getenv("SYMBOLS", "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD,ETHUSD").split(",")
POLL_MS     = int(os.getenv("TICK_POLL_MS", "250"))
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "9000"))
MT5_LOGIN   = int(os.getenv("MT5_LOGIN", "0") or "0")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER  = os.getenv("MT5_SERVER", "")
MT5_PATH    = os.getenv("MT5_PATH", "")

# ---------- MT5 init ----------
try:
    import MetaTrader5 as mt5
except ImportError:
    logger.critical("MetaTrader5 package not found. Install it: pip install MetaTrader5")
    sys.exit(1)


def connect_mt5() -> bool:
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
            logger.warning(f"Could not select symbol {sym}")
    info = mt5.account_info()
    logger.info(f"MT5 connected. Account: {info.login if info else 'unknown'}")
    return True


# ---------- WebSocket server ----------
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    logger.critical("websockets package not found. Install it: pip install websockets")
    sys.exit(1)

_clients: set["WebSocketServerProtocol"] = set()


async def _client_handler(ws: "WebSocketServerProtocol"):
    """Accept a client, hold the connection open, remove on disconnect."""
    _clients.add(ws)
    addr = ws.remote_address
    logger.info(f"Client connected: {addr}  (total: {len(_clients)})")
    try:
        await ws.wait_closed()
    finally:
        _clients.discard(ws)
        logger.info(f"Client disconnected: {addr}  (total: {len(_clients)})")


async def _tick_loop():
    """Poll MT5 every POLL_MS ms and broadcast ticks to all connected clients."""
    interval = POLL_MS / 1000.0
    consecutive_failures = 0

    while True:
        for sym in SYMBOLS:
            tick = mt5.symbol_info_tick(sym)
            if tick is None:
                consecutive_failures += 1
                if consecutive_failures > len(SYMBOLS) * 10:
                    logger.error("Too many MT5 failures — check terminal connection")
                    consecutive_failures = 0
                continue
            consecutive_failures = 0

            payload = json.dumps({
                "symbol": sym,
                "bid": tick.bid,
                "ask": tick.ask,
                "time": tick.time_msc / 1000.0 if tick.time_msc else float(tick.time),
            })

            if _clients:
                # broadcast returns a set of (client, exception) for failed sends
                results = await asyncio.gather(
                    *[_send(client, payload) for client in set(_clients)],
                    return_exceptions=True,
                )

        await asyncio.sleep(interval)


async def _send(ws: "WebSocketServerProtocol", payload: str):
    try:
        await ws.send(payload)
    except Exception:
        _clients.discard(ws)


async def main():
    if not connect_mt5():
        sys.exit(1)

    logger.info(f"Bridge listening on ws://{BRIDGE_HOST}:{BRIDGE_PORT}")
    logger.info(f"Streaming symbols: {SYMBOLS}  poll: {POLL_MS}ms")

    async with websockets.serve(_client_handler, BRIDGE_HOST, BRIDGE_PORT):
        await _tick_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bridge stopped.")
        mt5.shutdown()
