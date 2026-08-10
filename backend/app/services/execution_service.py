from app.broker.broker_manager import BrokerManager
from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
)
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
)


class ExecutionService:
    """
    Application service responsible for trade execution.

    This service does not know anything about MT5 specifically.
    It communicates only with BrokerManager.
    """

    def __init__(
        self,
        broker: BrokerManager,
    ):
        self.broker = broker

    # ==========================================================
    # ORDER EXECUTION
    # ==========================================================

    async def execute_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:

        try:
            result = await self.broker.place_order(
                order
            )

            return result

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to place order: {exc}"
            ) from exc

    # ==========================================================
    # OPEN POSITIONS
    # ==========================================================

    async def get_positions(self):

        try:
            return await self.broker.get_positions()

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve positions: {exc}"
            ) from exc

    # ==========================================================
    # CLOSE POSITION
    # ==========================================================

    async def close_position(
        self,
        position_id: int,
    ):

        try:
            return await self.broker.close_position(
                position_id
            )

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close position "
                f"{position_id}: {exc}"
            ) from exc