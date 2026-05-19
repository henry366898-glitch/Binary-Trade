"""Application configuration. Override via .env file."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MT5 connection — point to your broker's demo server
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""
    MT5_PATH: str = ""  # optional: path to terminal64.exe

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

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./platform.db"

    class Config:
        env_file = ".env"


settings = Settings()
