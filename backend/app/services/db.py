"""Async database session setup."""
import logging
import random
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from app.models.db import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# columns we expect to exist that older databases may be missing.
# (table, column, sqlite_type, default_sql)
_REQUIRED_COLUMNS = [
    ("users", "account_number", "VARCHAR(16)", "NULL"),
    ("users", "disabled_at", "DATETIME", "NULL"),
    ("balance_adjustments", "proof_image_path", "VARCHAR(255)", "NULL"),
    ("balance_adjustments", "bank_details", "TEXT", "NULL"),
    ("balance_adjustments", "reject_reason", "VARCHAR(255)", "NULL"),
    ("balance_adjustments", "payment_type_id", "INTEGER", "NULL"),
    ("payment_types", "fields", "TEXT", "NULL"),
]


async def _migrate_sqlite(conn):
    """Idempotent column-add migration for SQLite. Safe to run on every startup."""
    for table, col, sqltype, default in _REQUIRED_COLUMNS:
        # check whether the table exists at all (it'll be created by create_all if not)
        exists = (await conn.execute(text(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        ))).first()
        if not exists:
            continue
        cols = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
        existing = {row[1] for row in cols}
        if col not in existing:
            logger.info(f"Migrating: ADD COLUMN {table}.{col}")
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sqltype} DEFAULT {default}"))


async def _backfill_account_numbers():
    """Generate unique 6-digit account numbers for any users missing one."""
    from app.models.db import User
    from sqlalchemy import select
    async with async_session() as s:
        users = (await s.execute(select(User).where(User.account_number.is_(None)))).scalars().all()
        if not users:
            return
        existing = {a for (a,) in (await s.execute(select(User.account_number).where(User.account_number.is_not(None)))).all()}
        for u in users:
            while True:
                candidate = f"{random.randint(100_000, 999_999)}"
                if candidate not in existing:
                    existing.add(candidate)
                    u.account_number = candidate
                    break
            logger.info(f"Assigned account_number {u.account_number} to user {u.id}")
        await s.commit()


async def init_db():
    async with engine.begin() as conn:
        await _migrate_sqlite(conn)
        await conn.run_sync(Base.metadata.create_all)
    await _backfill_account_numbers()


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
