"""
Binance public WebSocket feed for BTCUSD and ETHUSD.

Connects to Binance's free combined stream (no API key required) and injects
ticks directly into the shared PriceFeed instance so the rest of the backend
treats them identically to MT5 ticks.

Symbol mapping:
  Binance BTCUSDT  →  internal BTCUSD
  Binance ETHUSDT  →  internal ETHUSD
"""
import asyncio
import json
import logging
import time

import websockets

logger = logging.getLogger(__name__)

# Binance combined stream — individual ticker (best bid/ask + last price)
_BINANCE_WS = (
    "wss://stream.binance.com:9443/stream"
    "?streams=btcusdt@bookTicker/ethusdt@bookTicker"
)

# Map Binance symbol → our internal symbol
_SYM_MAP = {
    "BTCUSDT": "BTCUSD",
    "ETHUSDT": "ETHUSD",
}


async def binance_feed_loop(price_feed) -> None:
    """
    Continuously connect to Binance and push BTCUSD/ETHUSD ticks into
    price_feed. Auto-reconnects with exponential backoff. Designed to run as
    a background asyncio task alongside the MT5 bridge loop.
    """
    backoff = 2.0

    while True:
        try:
            async with websockets.connect(
                _BINANCE_WS,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=15,
            ) as ws:
                logger.info("Binance feed connected (BTCUSDT / ETHUSDT)")
                backoff = 2.0  # reset on successful connect

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Combined stream wraps each event: {"stream":"...","data":{...}}
                    data = msg.get("data", msg)
                    binance_sym = data.get("s", "")  # e.g. "BTCUSDT"
                    internal_sym = _SYM_MAP.get(binance_sym)
                    if not internal_sym:
                        continue

                    bid = float(data.get("b", 0) or data.get("B", 0))
                    ask = float(data.get("a", 0) or data.get("A", 0))

                    if bid <= 0 or ask <= 0:
                        continue

                    tick = {
                        "symbol": internal_sym,
                        "bid":    round(bid, 2),
                        "ask":    round(ask, 2),
                        "time":   time.time(),
                    }
                    price_feed._ingest(tick)
                    await price_feed._broadcast(tick)

        except (OSError, websockets.exceptions.WebSocketException) as e:
            logger.warning(
                f"Binance feed lost ({type(e).__name__}: {e}). "
                f"Retrying in {backoff:.0f}s…"
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        except asyncio.CancelledError:
            logger.info("Binance feed task cancelled")
            return

        except Exception as e:
            logger.exception(f"Binance feed unexpected error: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
