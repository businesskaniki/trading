from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_RECOVERY_TARGET_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "mt5_recovery_target.json"
)


class Settings(BaseSettings):
    """Runtime configuration for the MT5 Bridge application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 9000
    LOG_LEVEL: str = "INFO"

    # Authentication shared with the AQE backend.
    # This is a service-to-service token, not an MT5 password.
    MT5_BRIDGE_TOKEN: str = ""

    # MT5 recovery monitoring
    MT5_RECONNECT_INTERVAL: float = 5.0
    MT5_RECOVERY_TARGET_FILE: str = str(_DEFAULT_RECOVERY_TARGET_FILE)

    # AQE credential recovery endpoint.
    # Change the host, port, or API prefix if your deployment differs.
    AQE_CREDENTIAL_RECOVERY_URL: str = (
        "http://127.0.0.1:8000/api/v1/internal/bridge/mt5-credentials"
    )
    AQE_CREDENTIAL_RECOVERY_TIMEOUT: float = 5.0

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if not self.MT5_BRIDGE_TOKEN:
            raise ValueError(
                "MT5_BRIDGE_TOKEN must be configured. Use the same "
                "random secret as AQE's BRIDGE_API_KEY."
            )

        if not self.AQE_CREDENTIAL_RECOVERY_URL.startswith(("http://", "https://")):
            raise ValueError("AQE_CREDENTIAL_RECOVERY_URL must be an HTTP(S) URL.")

        if self.AQE_CREDENTIAL_RECOVERY_TIMEOUT <= 0:
            raise ValueError("AQE_CREDENTIAL_RECOVERY_TIMEOUT must be positive.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
