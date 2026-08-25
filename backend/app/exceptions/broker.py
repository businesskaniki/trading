class BrokerError(Exception):
    """Base exception for broker-related errors."""


class BrokerOrderError(BrokerError):
    """Raised when a broker order operation fails."""


class BrokerPositionError(BrokerError):
    """Raised when a broker position operation fails."""