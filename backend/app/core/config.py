from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env.

    MT5 account credentials are intentionally not used from this settings
    object by the execution runtime. They are resolved from the selected
    TradingAccount at runtime.

    The bridge itself is authenticated using BRIDGE_API_KEY.
    """

    # ==========================
    # Application
    # ==========================
    APP_NAME: str = "Athena Quant Engine"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = Field(default="development")

    DEBUG: bool = True

    SECRET_KEY: str
    ENCRYPTION_KEY: str | None = None

    BROKER: str = "paper"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    API_PREFIX: str = "/api/v1"

    # ==========================
    # Database
    # ==========================
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # ==========================
    # Redis
    # ==========================
    REDIS_HOST: str
    REDIS_PORT: int = 6379

    # ==========================
    # Legacy MT5 Configuration
    # ==========================
    #
    # These fields are retained for backward compatibility with older
    # components. The current runtime account architecture does NOT use
    # these values to authenticate the selected TradingAccount.
    #
    # Runtime MT5 credentials come from:
    #
    #     TradingAccount
    #         ↓
    #     RuntimeAccountResolver
    #         ↓
    #     BrokerManager
    #         ↓
    #     MT5Adapter
    #         ↓
    #     MT5BridgeService
    #
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""

    # ==========================
    # SMTP
    # ==========================
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_USE_TLS: bool = True

    # ==========================
    # MT5 Bridge
    # ==========================
    MT5_BRIDGE_URL: str = "http://host.docker.internal:9000"

    # Shared secret used by AQE when communicating with the MT5 bridge.
    #
    # The bridge must have the matching value configured as BRIDGE_API_KEY.
    BRIDGE_API_KEY: str

    # ==========================
    # Pydantic Settings
    # ==========================
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # ==========================
    # Bridge Compatibility Alias
    # ==========================
    @property
    def MT5_BRIDGE_TOKEN(self) -> str:
        """
        Compatibility alias for components that expect MT5_BRIDGE_TOKEN.

        BRIDGE_API_KEY remains the canonical configuration variable.
        """
        return self.BRIDGE_API_KEY

    # ==========================
    # Database URL
    # ==========================
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://"
            f"{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

    # ==========================
    # Redis URL
    # ==========================
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    # ==========================
    # Production Safety
    # ==========================
    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if (
            self.APP_ENV.lower() == "production"
            and self.BROKER.lower() == "paper"
        ):
            raise ValueError(
                "BROKER must be explicitly set to mt5 in production"
            )

        if self.APP_ENV.lower() == "production" and self.DEBUG:
            raise ValueError("DEBUG must be false in production")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()