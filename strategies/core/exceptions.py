"""
Exceptions used by the AQE strategy framework.

These exceptions describe strategy-layer failures.

They should not be used for:
    - broker errors
    - order execution errors
    - risk-engine rejection
    - database errors

Those belong to their respective layers.
"""


class StrategyError(Exception):
    """
    Base exception for all strategy-related errors.
    """

    def __init__(
        self,
        message: str,
        *,
        strategy_id: str | None = None,
    ) -> None:
        self.message = message
        self.strategy_id = strategy_id

        super().__init__(message)

    def __str__(self) -> str:
        if self.strategy_id:
            return f"[{self.strategy_id}] {self.message}"

        return self.message


class StrategyConfigurationError(StrategyError):
    """
    Raised when a strategy has invalid configuration.
    """

    pass


class StrategyContextError(StrategyError):
    """
    Raised when a strategy receives invalid or incomplete context.
    """

    pass


class StrategySignalError(StrategyError):
    """
    Raised when a strategy produces an invalid signal.
    """

    pass


class StrategyInitializationError(StrategyError):
    """
    Raised when a strategy cannot be initialized.
    """

    pass


class StrategyExecutionError(StrategyError):
    """
    Raised when strategy evaluation fails unexpectedly.
    """

    pass


class StrategyNotFoundError(StrategyError):
    """
    Raised when a requested strategy is not registered.
    """

    pass


class StrategyAlreadyRegisteredError(StrategyError):
    """
    Raised when attempting to register a duplicate strategy ID.
    """

    pass


class StrategyDisabledError(StrategyError):
    """
    Raised when an operation requires an enabled strategy but the
    strategy is disabled.
    """

    pass
