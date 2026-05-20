"""Market data endpoints + WebSocket price stream."""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from app.config import settings
from app.services.mt5_feed import price_feed

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/symbols")
async def list_symbols():
    return {
        "symbols": settings.SYMBOLS,
        "expiry_options": settings.EXPIRY_OPTIONS_SECONDS,
        "payout_rate": settings.DEFAULT_PAYOUT,
    }



@router.get("/price/{symbol}")
async def get_price(symbol: str):
    tick = price_feed.latest.get(symbol)
    if not tick:
        raise HTTPException(404, "Symbol not found or no data")
    return tick


@router.get("/candles/{symbol}")
async def get_candles(symbol: str, timeframe: int = 1, count: int = 100):
    if symbol not in settings.SYMBOLS:
        raise HTTPException(404, "Symbol not configured")
    return {"symbol": symbol, "candles": price_feed.get_candles(symbol, timeframe, count)}


@router.websocket("/stream")
async def price_stream(ws: WebSocket):
    """Streams tick data for all symbols to connected clients."""
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    async def on_tick(tick: dict):
        try:
            queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass  # drop ticks if client is slow

    price_feed.subscribe(on_tick)

    # send initial snapshot
    try:
        for sym, tick in price_feed.latest.items():
            await ws.send_text(json.dumps({"type": "tick", **tick}))

        while True:
            tick = await queue.get()
            await ws.send_text(json.dumps({"type": "tick", **tick}))
    except WebSocketDisconnect:
        pass
    finally:
        price_feed.unsubscribe(on_tick)
