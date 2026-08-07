from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loads configuration from environment variables and .env file.
    """

    # ==========================
    # Application
    # ==========================
    APP_NAME: str = "Athena Quant Engine"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = Field(default="development")

    DEBUG: bool = True

    SECRET_KEY: str

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
    # MT5
    # ==========================
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""

    SMTP_HOST: str
    SMTP_PORT: int = 587

    SMTP_USERNAME: str
    SMTP_PASSWORD: str

    SMTP_FROM_EMAIL: str

    SMTP_USE_TLS: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def DATABASE_URL(self):
        return (
            f"postgresql+psycopg://"
            f"{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self):
        return f"redis://" f"{self.REDIS_HOST}:" f"{self.REDIS_PORT}"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
