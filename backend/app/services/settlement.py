"""
Trade settlement engine.

Runs on a 1-second tick. Finds all OPEN trades past their expires_at, fetches the
current MT5 price, determines win/loss, updates the user's balance, and marks
the trade settled.
"""
import asyncio
import logging
from datetime import datetime

from beanie.operators import Inc

from app.models.db import Trade, TradeStatus, TradeDirection, User
from app.services.mt5_feed import price_feed

logger = logging.getLogger(__name__)


async def settle_trade(trade: Trade) -> None:
    exit_price = price_feed.get_price(trade.symbol)
    if exit_price is None:
        logger.warning(f"No price for {trade.symbol}, deferring trade {trade.id}")
        return

    trade.exit_price = exit_price
    trade.settled_at = datetime.utcnow()

    if abs(exit_price - trade.entry_price) < 1e-9:
        trade.status = TradeStatus.TIE
        trade.profit = 0.0
        refund = trade.amount
    else:
        moved_up = exit_price > trade.entry_price
        won = (trade.direction == TradeDirection.UP and moved_up) or \
              (trade.direction == TradeDirection.DOWN and not moved_up)
        if won:
            trade.status = TradeStatus.WON
            trade.profit = trade.amount * trade.payout_rate
            refund = trade.amount + trade.profit
        else:
            trade.status = TradeStatus.LOST
            trade.profit = -trade.amount
            refund = 0.0

    await trade.save()

    # Atomic balance credit — avoids read-modify-write races if ever concurrent
    if refund > 0:
        await User.find_one(User.id == trade.user_id).update(Inc({User.balance: refund}))

    logger.info(
        f"Settled trade {trade.id} {trade.symbol} {trade.direction} "
        f"entry={trade.entry_price:.5f} exit={exit_price:.5f} "
        f"status={trade.status} profit={trade.profit:.2f}"
    )


async def settlement_loop():
    """Continuously settles expired trades."""
    logger.info("Settlement loop started")
    while True:
        try:
            now = datetime.utcnow()
            expired = await Trade.find(
                Trade.status == TradeStatus.OPEN,
                Trade.expires_at <= now,
            ).to_list()
            for trade in expired:
                await settle_trade(trade)
        except Exception as e:
            logger.exception(f"Settlement error: {e}")
        await asyncio.sleep(1.0)
