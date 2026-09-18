from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    HOST: str = "0.0.0.0"
    PORT: int = 9000

    LOG_LEVEL: str = "INFO"
    MT5_BRIDGE_TOKEN: str = ""
    MT5_RECONNECT_INTERVAL: float = 5.0

    @model_validator(mode="after")
    def validate_security(self):
        if not self.MT5_BRIDGE_TOKEN:
            raise ValueError("MT5_BRIDGE_TOKEN must be configured")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()