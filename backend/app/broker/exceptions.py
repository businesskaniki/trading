class BrokerError(Exception):
    """
    Base exception for all broker-related errors.
    """

    pass


class BrokerConnectionError(BrokerError):
    """
    Raised when a connection to a broker fails.
    """

    pass


class BrokerAuthenticationError(BrokerError):
    """
    Raised when broker credentials are invalid.
    """

    pass


class BrokerOrderError(BrokerError):
    """
    Raised when an order cannot be submitted or processed.
    """

    pass


class BrokerPositionError(BrokerError):
    """
    Raised when a position operation fails.
    """

    pass


class BrokerSymbolError(BrokerError):
    """
    Raised when a symbol operation fails.
    """

    pass


class BrokerTimeoutError(BrokerError):
    """
    Raised when communication with the broker times out.
    """

    pass