"""
Binary Options Platform — FastAPI entry point.

EDUCATIONAL USE ONLY. This platform is a learning project that simulates
binary options trading. Real binary options are statistically a losing
proposition for retail traders (>80% lose money) and are banned for retail
clients in many jurisdictions.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, auth, leads, market, trades
from app.services.db import init_db
from app.services.mt5_feed import price_feed
from app.services.settlement import settlement_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("Initializing database…")
    await init_db()

    logger.info("Starting MT5 price feed…")
    feed_task = asyncio.create_task(price_feed.start())

    logger.info("Starting trade settlement loop…")
    settle_task = asyncio.create_task(settlement_loop())

    yield

    # shutdown
    logger.info("Shutting down…")
    await price_feed.stop()
    feed_task.cancel()
    settle_task.cancel()
    for t in (feed_task, settle_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="Binary Options Platform (Educational)",
    description="Educational simulation of a binary options trading platform with MT5 data feed.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(trades.router)
app.include_router(leads.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {
        "name": "Binary Options Platform (Educational)",
        "warning": "FOR EDUCATIONAL USE ONLY. Real binary options trading is high-risk and banned for retail clients in many jurisdictions.",
        "docs": "/docs",
    }
