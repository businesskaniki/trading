from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration for the MT5 Bridge application server.

    Loaded from environment variables / a .env file. This is separate
    from RedisConfig (app/infrastructure/redis/config.py), which
    handles Redis-specific settings on its own.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # ==========================
    # Server
    # ==========================

    HOST: str = "0.0.0.0"
    PORT: int = 9000

    LOG_LEVEL: str = "INFO"

    # ==========================
    # Security
    # ==========================

    # Shared secret the backend must send as the X-Bridge-Key header
    # on every request. This is what lets the bridge tell "a request
    # from our backend" apart from "a request from anyone who can
    # reach this port." Required - the bridge refuses to start
    # without it rather than silently accepting unauthenticated
    # requests.
    MT5_BRIDGE_TOKEN: str = ""

    # ==========================
    # MT5 connection
    # ==========================

    MT5_RECONNECT_INTERVAL: float = 5.0

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if not self.MT5_BRIDGE_TOKEN:
            raise ValueError(
                "MT5_BRIDGE_TOKEN must be configured. Generate one "
                "with `openssl rand -hex 32` and set the SAME value "
                "as BRIDGE_API_KEY in the backend's .env - the names "
                "differ but both must hold the identical secret."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()