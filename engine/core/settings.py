"""Configuration management for the Athena Quant Engine.

This module provides a single, typed configuration object for the engine.
Configuration can be supplied through environment variables and can be
overridden by application-level configuration when required.

Secrets should never be hard-coded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from engine.core.constants import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_MAX_ORDERS_PER_SECOND,
    DEFAULT_MAX_POSITIONS,
    DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    DEFAULT_TICK_INTERVAL_SECONDS,
    DEFAULT_TRADING_MODE,
    Environment,
    TradingMode,
)


class DatabaseSettings(BaseModel):
    """Database connection settings."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/aqe",
        description="SQLAlchemy database URL.",
    )

    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=1800, ge=0)
    echo: bool = False


class RedisSettings(BaseModel):
    """Redis connection settings."""

    model_config = ConfigDict(extra="ignore")

    url: str = "redis://localhost:6379/0"
    enabled: bool = True


class PaperBrokerSettings(BaseModel):
    """Paper-trading broker configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    initial_balance: float = Field(
        default=10_000.0,
        gt=0,
    )

    base_currency: str = "USD"

    commission_enabled: bool = True
    commission_rate: float = Field(
        default=0.0,
        ge=0,
    )

    slippage_enabled: bool = True
    slippage_bps: float = Field(
        default=0.0,
        ge=0,
    )


class MT5BrokerSettings(BaseModel):
    """MetaTrader 5 broker configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False

    login: int | None = None
    password: SecretStr | None = None
    server: str | None = None

    terminal_path: str | None = None

    timeout_seconds: float = Field(
        default=10.0,
        gt=0,
    )


class BinanceBrokerSettings(BaseModel):
    """Binance broker configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False

    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None

    testnet: bool = True


class FIXBrokerSettings(BaseModel):
    """FIX protocol broker configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False

    host: str | None = None
    port: int | None = None

    sender_comp_id: str | None = None
    target_comp_id: str | None = None

    username: str | None = None
    password: SecretStr | None = None


class BrokerSettings(BaseModel):
    """Broker and execution configuration."""

    model_config = ConfigDict(extra="ignore")

    default: str = "paper"

    paper: PaperBrokerSettings = Field(default_factory=PaperBrokerSettings)

    mt5: MT5BrokerSettings = Field(default_factory=MT5BrokerSettings)

    binance: BinanceBrokerSettings = Field(default_factory=BinanceBrokerSettings)

    fix: FIXBrokerSettings = Field(default_factory=FIXBrokerSettings)

    @field_validator("default")
    @classmethod
    def validate_default_broker(cls, value: str) -> str:
        """Ensure the default broker is one of the supported brokers."""

        supported = {"paper", "mt5", "binance", "fix"}

        value = value.lower().strip()

        if value not in supported:
            raise ValueError(
                f"Unsupported default broker '{value}'. "
                f"Supported brokers: {sorted(supported)}"
            )

        return value


class EngineRuntimeSettings(BaseModel):
    """Runtime behavior of the AQE engine."""

    model_config = ConfigDict(extra="ignore")

    trading_mode: TradingMode = DEFAULT_TRADING_MODE
    environment: Environment = DEFAULT_ENVIRONMENT

    tick_interval_seconds: float = Field(
        default=DEFAULT_TICK_INTERVAL_SECONDS,
        gt=0,
    )

    heartbeat_interval_seconds: float = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        gt=0,
    )

    shutdown_timeout_seconds: float = Field(
        default=DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
        gt=0,
    )

    max_positions: int = Field(
        default=DEFAULT_MAX_POSITIONS,
        ge=1,
    )

    max_orders_per_second: int = Field(
        default=DEFAULT_MAX_ORDERS_PER_SECOND,
        ge=1,
    )

    auto_start: bool = False


class RiskSettings(BaseModel):
    """Engine-level risk safety settings.

    The actual risk calculations and risk rules belong to the dedicated
    AQE risk subsystem. These settings only define runtime safety gates.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    live_trading_enabled: bool = False

    max_daily_loss_percent: float = Field(
        default=5.0,
        ge=0,
    )

    max_drawdown_percent: float = Field(
        default=20.0,
        ge=0,
    )

    max_open_positions: int = Field(
        default=DEFAULT_MAX_POSITIONS,
        ge=1,
    )


class MonitoringSettings(BaseModel):
    """Observability and health-monitoring configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    prometheus_enabled: bool = True
    prometheus_host: str = "0.0.0.0"
    prometheus_port: int = Field(default=9090, ge=1, le=65535)

    tracing_enabled: bool = False


class MarketSettings(BaseModel):
    """Market-data configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    default_timeframe: str = "M1"

    tick_buffer_size: int = Field(
        default=10_000,
        ge=100,
    )

    candle_buffer_size: int = Field(
        default=5_000,
        ge=100,
    )


class AnalyticsSettings(BaseModel):
    """Analytics subsystem configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    equity_curve_enabled: bool = True
    performance_metrics_enabled: bool = True

    calculate_sharpe: bool = True
    calculate_sortino: bool = True
    calculate_expectancy: bool = True


class BacktestingSettings(BaseModel):
    """Backtesting subsystem configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True

    initial_balance: float = Field(
        default=10_000.0,
        gt=0,
    )

    commission_enabled: bool = True
    slippage_enabled: bool = True
    latency_enabled: bool = True

    allow_optimization: bool = True
    allow_walk_forward: bool = True


class MLSettings(BaseModel):
    """Machine-learning configuration.

    ML is disabled by default. When enabled, ML components must still
    operate through the strategy/risk architecture and must not bypass
    risk controls.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False

    feature_engineering_enabled: bool = True
    regime_detection_enabled: bool = False
    signal_ranking_enabled: bool = False
    dynamic_sizing_enabled: bool = False

    model_directory: str = "engine/ml/models"


class AQESettings(BaseSettings):
    """Root configuration for the Athena Quant Engine."""

    model_config = SettingsConfigDict(
        env_prefix="AQE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Application identity
    app_name: str = "Athena Quant Engine"
    version: str = "0.1.0"

    # Runtime
    runtime: EngineRuntimeSettings = Field(default_factory=EngineRuntimeSettings)

    # Infrastructure
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    redis: RedisSettings = Field(default_factory=RedisSettings)

    # Trading
    brokers: BrokerSettings = Field(default_factory=BrokerSettings)

    risk: RiskSettings = Field(default_factory=RiskSettings)

    # Market and analytics
    market: MarketSettings = Field(default_factory=MarketSettings)

    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)

    # Backtesting and ML
    backtesting: BacktestingSettings = Field(default_factory=BacktestingSettings)

    ml: MLSettings = Field(default_factory=MLSettings)

    # Monitoring
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)

    # Debugging
    debug: bool = False

    def get_default_broker(self) -> str:
        """Return the configured default broker name."""

        return self.brokers.default

    def is_live_trading_allowed(self) -> bool:
        """Return whether live trading is explicitly permitted."""

        return (
            self.runtime.trading_mode == TradingMode.LIVE
            and self.risk.live_trading_enabled
            and self.brokers.mt5.enabled
        )

    def get_broker_settings(self, broker_name: str) -> BaseModel:
        """Return configuration for a named broker."""

        broker_name = broker_name.lower().strip()

        broker = getattr(self.brokers, broker_name, None)

        if broker is None:
            raise ValueError(f"Unknown broker '{broker_name}'.")

        return broker

    def validate_runtime_safety(self) -> None:
        """Validate dangerous runtime combinations.

        This deliberately fails closed for live trading.
        """

        if self.runtime.trading_mode == TradingMode.LIVE:
            if not self.risk.live_trading_enabled:
                raise RuntimeError(
                    "Live trading mode requested but "
                    "risk.live_trading_enabled is false."
                )

            if not self.brokers.mt5.enabled:
                raise RuntimeError(
                    "Live trading mode requested but " "the MT5 broker is disabled."
                )

            if self.brokers.default == "paper":
                raise RuntimeError(
                    "Live trading mode cannot use paper as the " "default broker."
                )

        if self.runtime.trading_mode == TradingMode.PAPER:
            if not self.brokers.paper.enabled:
                raise RuntimeError(
                    "Paper trading mode requested but " "the paper broker is disabled."
                )


@lru_cache(maxsize=1)
def get_settings() -> AQESettings:
    """Return the cached global AQE settings instance."""

    return AQESettings()


__all__ = [
    "AnalyticsSettings",
    "AQESettings",
    "BacktestingSettings",
    "BinanceBrokerSettings",
    "BrokerSettings",
    "DatabaseSettings",
    "EngineRuntimeSettings",
    "FIXBrokerSettings",
    "MarketSettings",
    "MLSettings",
    "MonitoringSettings",
    "MT5BrokerSettings",
    "PaperBrokerSettings",
    "RedisSettings",
    "RiskSettings",
    "get_settings",
]
