from __future__ import annotations

from datetime import datetime
from typing import Any

from app.broker.broker_manager import BrokerManager
from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
)
from app.schemas.execution import (
    ExecutionOrder,
    ExecutionResult,
    ExecutionStatus,
    OrderType,
)


class ExecutionService:
    """
    Application-level execution service.

    Responsibilities:
        - Route market orders to the broker market-order path.
        - Route LIMIT/STOP orders to the broker pending-order path.
        - Normalize broker responses into ExecutionResult.
        - Expose broker position operations.
        - Expose broker trading-history operations.

    Broker-specific behavior belongs inside BrokerAdapter
    implementations.
    """

    def __init__(self, broker: BrokerManager):
        self.broker = broker

    # ==========================================================
    # ORDER EXECUTION
    # ==========================================================

    async def execute_order(
        self,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Execute an order through the appropriate broker operation.

        MARKET:
            broker.place_order()

        LIMIT / STOP:
            broker.create_pending_order()
        """

        try:
            if order.order_type == OrderType.MARKET:
                result = await self.broker.place_order(order.model_dump())

            elif order.order_type in {
                OrderType.LIMIT,
                OrderType.STOP,
            }:
                result = await self.broker.create_pending_order(order.model_dump())

            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    broker=self._broker_name(),
                    symbol=order.symbol,
                    volume=order.volume,
                    message=(f"Unsupported order type: " f"{order.order_type.value}"),
                )

            return self._normalize_result(
                result=result,
                order=order,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to execute " f"{order.order_type.value} order: {exc}"
            ) from exc

    # ==========================================================
    # RESULT NORMALIZATION
    # ==========================================================

    def _normalize_result(
        self,
        result: Any,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """
        Convert broker output into the AQE execution contract.

        Broker adapters should ideally return ExecutionResult already,
        but dictionaries are also supported for compatibility.
        """

        if isinstance(result, ExecutionResult):
            return result

        if not isinstance(result, dict):
            raise BrokerOrderError("Broker returned an invalid execution response.")

        status = self._normalize_status(result)

        return ExecutionResult(
            status=status,
            broker=self._broker_name(),
            broker_order_id=self._optional_int(
                result.get(
                    "broker_order_id",
                    result.get("order_id"),
                )
            ),
            broker_deal_id=self._optional_int(
                result.get(
                    "broker_deal_id",
                    result.get("deal_id"),
                )
            ),
            broker_position_id=self._optional_int(
                result.get(
                    "broker_position_id",
                    result.get("position_id"),
                )
            ),
            symbol=result.get("symbol") or order.symbol,
            volume=result.get("volume") or order.volume,
            price=result.get("price") or result.get("price_open"),
            message=result.get("message") or result.get("comment"),
            raw_response=result,
        )

    @staticmethod
    def _normalize_status(
        result: dict[str, Any],
    ) -> ExecutionStatus:
        """
        Normalize broker status or MT5 retcode into ExecutionStatus.
        """

        status = result.get("status")

        if isinstance(status, ExecutionStatus):
            return status

        if isinstance(status, str):
            try:
                return ExecutionStatus(status.upper())
            except ValueError:
                pass

        retcode = result.get(
            "retcode",
            result.get("state"),
        )

        if retcode in {
            10008,  # TRADE_RETCODE_PLACED
            10009,  # TRADE_RETCODE_DONE
            10010,  # TRADE_RETCODE_DONE_PARTIAL
        }:
            return ExecutionStatus.SUCCESS

        if retcode in {
            10006,  # REJECT
            10007,  # CANCEL
            10011,  # ERROR
            10012,  # TIMEOUT
            10013,  # INVALID
            10014,  # INVALID_VOLUME
            10015,  # INVALID_PRICE
            10016,  # INVALID_STOPS
            10017,  # TRADE_DISABLED
            10018,  # MARKET_CLOSED
            10019,  # NO_MONEY
            10020,  # PRICE_CHANGED
            10021,  # PRICE_OFF
            10022,  # INVALID_EXPIRATION
            10023,  # ORDER_CHANGED
            10024,  # TOO_MANY_REQUESTS
            10025,  # NO_CHANGES
            10026,  # SERVER_DISABLES_AT
            10027,  # CLIENT_DISABLES_AT
            10028,  # LOCKED
            10029,  # FROZEN
            10030,  # INVALID_FILL
            10031,  # CONNECTION
            10032,  # ONLY_REAL
            10033,  # LIMIT_ORDERS
            10034,  # LIMIT_VOLUME
            10035,  # INVALID_ORDER
            10036,  # POSITION_CLOSED
            10038,  # INVALID_CLOSE_VOLUME
            10039,  # CLOSE_ORDER_EXIST
            10040,  # LIMIT_POSITIONS
            10041,  # REJECT_CANCEL
            10042,  # LONG_ONLY
            10043,  # SHORT_ONLY
            10044,  # CLOSE_ONLY
            10045,  # FIFO_CLOSE
            10046,  # HEDGE_PROHIBITED
        }:
            return ExecutionStatus.REJECTED

        return ExecutionStatus.FAILED

    # ==========================================================
    # POSITIONS
    # ==========================================================

    async def get_positions(self):
        """Retrieve current broker positions."""

        try:
            return await self.broker.get_positions()

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(f"Failed to retrieve positions: {exc}") from exc

    async def get_position(
        self,
        position_id: int,
    ):
        """Retrieve a single broker position."""

        try:
            return await self.broker.get_position(position_id)

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve position " f"{position_id}: {exc}"
            ) from exc

    async def close_position(
        self,
        position_id: int,
    ):
        """Close an existing broker position."""

        try:
            return await self.broker.close_position(position_id)

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to close position " f"{position_id}: {exc}"
            ) from exc

    async def modify_position(
        self,
        position_id: int,
        sl: float | None = None,
        tp: float | None = None,
    ):
        """Modify stop-loss and/or take-profit."""

        try:
            return await self.broker.modify_position(
                position_id=position_id,
                sl=sl,
                tp=tp,
            )

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to modify position " f"{position_id}: {exc}"
            ) from exc

    # ==========================================================
    # BROKER HISTORY
    # ==========================================================

    async def get_order_history(
        self,
        start: datetime,
        end: datetime,
    ):
        """Retrieve broker order history."""

        try:
            return await self.broker.get_order_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to retrieve order history: {exc}") from exc

    async def get_deal_history(
        self,
        start: datetime,
        end: datetime,
    ):
        """Retrieve broker deal history."""

        try:
            return await self.broker.get_deal_history(
                start=start,
                end=end,
            )

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(f"Failed to retrieve deal history: {exc}") from exc

    async def get_deals_by_position(
        self,
        position_id: int,
    ):
        """
        Retrieve all broker deals associated with a position.
        """

        try:
            return await self.broker.get_deals_by_position(position_id)

        except BrokerOrderError:
            raise

        except Exception as exc:
            raise BrokerOrderError(
                f"Failed to retrieve deals for position " f"{position_id}: {exc}"
            ) from exc

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _broker_name(self) -> str:
        """
        Return a stable broker identifier.
        """

        adapter = getattr(
            self.broker,
            "adapter",
            None,
        )

        if adapter is None:
            return "UNKNOWN"

        name = getattr(
            adapter,
            "name",
            None,
        )

        if name:
            return str(name)

        return adapter.__class__.__name__

    @staticmethod
    def _optional_int(
        value: Any,
    ) -> int | None:
        """Safely normalize an optional broker identifier."""

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
