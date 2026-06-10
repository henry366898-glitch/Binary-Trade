"""MongoDB connection and Beanie initialisation."""
import logging

import motor.motor_asyncio
from beanie import init_beanie

from app.config import settings
from app.models.db import (
    AcademyClick, AdminUser, BalanceAdjustment, Bet, PaymentType, SportEvent, Trade, User,
)

logger = logging.getLogger(__name__)

_motor_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _motor_client
    _motor_client = motor.motor_asyncio.AsyncIOMotorClient(settings.DATABASE_URL)
    await init_beanie(
        database=_motor_client[settings.DATABASE_NAME],
        document_models=[
            User, Trade, AdminUser, BalanceAdjustment, PaymentType, AcademyClick,
            SportEvent, Bet,
        ],
    )
    logger.info("MongoDB connected — database: %s", settings.DATABASE_NAME)


def get_motor_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    assert _motor_client is not None, "init_db() not called"
    return _motor_client
