"""Application configuration. Override via .env file."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MT5 Bridge — WebSocket URL of the standalone bridge process (bridge.py).
    # Set this to connect to real MT5 data. Leave blank to use the mock feed.
    # Example: ws://192.168.1.10:9000  or  ws://localhost:9000
    MT5_BRIDGE_URL: str = ""

    # Symbols to stream (adjust to match your broker's naming)
    SYMBOLS: list[str] = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"]

    # Polling interval for MT5 ticks (milliseconds)
    TICK_POLL_MS: int = 250

    # Auth
    JWT_SECRET: str = "change-me-in-production-this-is-educational-only"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Admin export — set via .env to a long random string before exposing publicly
    ADMIN_SECRET: str = "change-me-admin-secret"

    # Trading rules (educational defaults)
    STARTING_BALANCE: float = 0.0
    DEFAULT_PAYOUT: float = 0.85  # 85% payout on win
    MIN_TRADE_AMOUNT: float = 1.0
    MAX_TRADE_AMOUNT: float = 1000.0
    EXPIRY_OPTIONS_SECONDS: list[int] = [30, 60, 120, 300, 600]

    # Sportsbook (educational, virtual money — uses the SAME balance as trading)
    SPORTSBOOK_ENABLED: bool = True
    MIN_BET_AMOUNT: float = 1.0
    MAX_BET_AMOUNT: float = 1000.0
    # Keep at least this many upcoming (scheduled) events live in the catalogue
    SPORTSBOOK_MIN_UPCOMING: int = 60
    # How long a simulated match "runs" before a result is produced (seconds).
    # Short by design so the educational sim settles quickly.
    SPORTSBOOK_LIVE_SECONDS: int = 90
    # How far ahead new fixtures are scheduled (seconds, randomised up to this).
    SPORTSBOOK_SCHEDULE_WINDOW: int = 1800

    # Database
    DATABASE_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "edgetrade"

    class Config:
        env_file = ".env"
        extra = "ignore"   # silently ignore unknown vars (e.g. PYTHONUNBUFFERED, NODE_ENV)


settings = Settings()
