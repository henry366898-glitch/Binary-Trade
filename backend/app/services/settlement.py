"""
Trade settlement engine.

Runs on a 1-second tick. Finds all OPEN trades past their expires_at, fetches the
current MT5 price, determines win/loss, updates the user's balance, and marks
the trade settled.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Trade, TradeStatus, TradeDirection, User
from app.services.mt5_feed import price_feed
from app.services.db import async_session

logger = logging.getLogger(__name__)


async def settle_trade(session: AsyncSession, trade: Trade) -> None:
    exit_price = price_feed.get_price(trade.symbol)
    if exit_price is None:
        logger.warning(f"No price for {trade.symbol}, deferring trade {trade.id}")
        return

    trade.exit_price = exit_price
    trade.settled_at = datetime.utcnow()

    # determine outcome
    if abs(exit_price - trade.entry_price) < 1e-9:
        # exact tie — refund stake
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
            refund = trade.amount + trade.profit  # return stake + profit
        else:
            trade.status = TradeStatus.LOST
            trade.profit = -trade.amount
            refund = 0.0  # stake already deducted on placement

    # credit user
    user = await session.get(User, trade.user_id)
    if user:
        user.balance += refund

    await session.commit()
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
            async with async_session() as session:
                now = datetime.utcnow()
                result = await session.execute(
                    select(Trade).where(
                        Trade.status == TradeStatus.OPEN,
                        Trade.expires_at <= now,
                    )
                )
                expired = result.scalars().all()
                for trade in expired:
                    await settle_trade(session, trade)
        except Exception as e:
            logger.exception(f"Settlement error: {e}")
        await asyncio.sleep(1.0)
