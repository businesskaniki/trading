from enum import Enum as PyEnum


class OrderType(str, PyEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderSide(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, PyEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AssetClass(str, PyEnum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    METALS = "METALS"
    INDICES = "INDICES"
    STOCKS = "STOCKS"
    COMMODITIES = "COMMODITIES"


class BrokerType(str, PyEnum):
    MT5 = "MT5"
    BINANCE = "BINANCE"
    FIX = "FIX"


class AccountStatus(str, PyEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    ARCHIVED = "ARCHIVED"


class PositionDirection(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, PyEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"


class TradeResult(str, PyEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


class StrategyRunType(str, PyEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class StrategyRunStatus(str, PyEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PerformancePeriod(str, PyEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    BACKTEST = "BACKTEST"
    LIVE = "LIVE"


class RiskLevel(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"