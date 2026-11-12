from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.broker.broker_manager import BrokerManager
from app.broker.exceptions import (
    BrokerOrderError,
    BrokerPositionError,
    MT5BridgeUnavailableError
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
        - Route MARKET orders to the broker market-order path.
        - Route LIMIT/STOP orders to the broker pending-order path.
        - Normalize broker responses into ExecutionResult.
        - Expose broker position operations.
        - Expose broker trading-history operations.

    Broker-specific behavior belongs inside BrokerAdapter
    implementations.

    This service does not:
        - calculate risk;
        - generate signals;
        - communicate directly with MT5;
        - persist AQE orders.
    """

    def __init__(
        self,
        broker: BrokerManager,
        account_id: UUID | str | None = None,
    ) -> None:
        self.broker = broker
        self.account_id = str(account_id) if account_id is not None else None

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
            BrokerManager.place_order()

        LIMIT / STOP:
            BrokerManager.create_pending_order()

        The ExecutionOrder object is passed directly to BrokerManager.
        BrokerManager and the underlying BrokerAdapter own the
        broker-specific translation.
        """

        if not isinstance(order, ExecutionOrder):
            raise BrokerOrderError(
                "ExecutionService requires an ExecutionOrder instance."
            )

        self._validate_account_binding(
            order,
        )

        try:
            if order.order_type is OrderType.MARKET:
                result = await self.broker.place_order(
                    order,
                )

            elif order.order_type in {
                OrderType.LIMIT,
                OrderType.STOP,
            }:
                result = await self.broker.create_pending_order(
                    order,
                )

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
    # ACCOUNT BINDING
    # ==========================================================

    def _validate_account_binding(
        self,
        order: ExecutionOrder,
    ) -> None:
        """
        Prevent a runtime bound to one trading account from
        executing an order belonging to another account.

        A generic ExecutionService may have no account binding.
        Validation is enforced when an account-scoped runtime
        supplies ``account_id``.
        """

        if self.account_id is None:
            return

        if order.account_id is None:
            raise BrokerOrderError("Execution order does not contain an account_id.")

        if str(order.account_id) != self.account_id:
            raise BrokerOrderError(
                "Execution order account does not match "
                "the active AQE runtime account."
            )

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

        status = self._normalize_status(
            result,
        )

        broker_order_id = self._first_present(
            result,
            "broker_order_id",
            "order_id",
            "ticket",
        )

        broker_deal_id = self._first_present(
            result,
            "broker_deal_id",
            "deal_id",
            "deal",
        )

        broker_position_id = self._first_present(
            result,
            "broker_position_id",
            "position_id",
            "position",
        )

        volume = result.get("volume")

        if volume is None:
            volume = result.get("volume_executed")

        if volume is None:
            volume = order.volume

        price = result.get("price")

        if price is None:
            price = result.get("price_open")

        message = result.get("message")

        if message is None:
            message = result.get("comment")

        return ExecutionResult(
            status=status,
            broker=self._broker_name(),
            broker_order_id=self._optional_int(
                broker_order_id,
            ),
            broker_deal_id=self._optional_int(
                broker_deal_id,
            ),
            broker_position_id=self._optional_int(
                broker_position_id,
            ),
            symbol=str(
                result.get(
                    "symbol",
                    order.symbol,
                )
            ).strip(),
            volume=volume,
            price=price,
            message=(str(message) if message is not None else None),
            raw_response=result,
        )

    # ==========================================================
    # STATUS NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_status(
        result: dict[str, Any],
    ) -> ExecutionStatus:
        """
        Normalize broker status or MT5 retcode into ExecutionStatus.
        """

        raw_status = result.get("status")

        if isinstance(
            raw_status,
            ExecutionStatus,
        ):
            return raw_status

        if isinstance(
            raw_status,
            str,
        ):
            try:
                return ExecutionStatus(
                    raw_status.upper(),
                )
            except ValueError:
                pass

        retcode = result.get(
            "retcode",
            result.get("state"),
        )

        if retcode in {
            10008,
            10009,
            10010,
        }:
            return ExecutionStatus.SUCCESS

        if retcode in {
            10006,
            10007,
            10011,
            10012,
            10013,
            10014,
            10015,
            10016,
            10017,
            10018,
            10019,
            10020,
            10021,
            10022,
            10023,
            10024,
            10025,
            10026,
            10027,
            10028,
            10029,
            10030,
            10031,
            10032,
            10033,
            10034,
            10035,
            10036,
            10038,
            10039,
            10040,
            10041,
            10042,
            10043,
            10044,
            10045,
            10046,
        }:
            return ExecutionStatus.REJECTED

        return ExecutionStatus.FAILED

    # ==========================================================
    # POSITIONS
    # ==========================================================

    async def get_positions(self):
        """
        Retrieve current broker positions.
        """

        try:
            return await self.broker.get_positions()

        except MT5BridgeUnavailableError:
            raise

        except BrokerPositionError:
            raise

        except Exception as exc:
            raise BrokerPositionError(
                f"Failed to retrieve positions: {exc}"
            ) from exc

    async def get_position(
        self,
        position_id: int,
    ):
        """
        Retrieve a single broker position.
        """

        try:
            return await self.broker.get_position(
                position_id,
            )

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
        """
        Close an existing broker position.
        """

        try:
            return await self.broker.close_position(
                position_id,
            )

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
        """
        Modify stop-loss and/or take-profit.
        """

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
        """
        Retrieve broker order history.
        """

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
        """
        Retrieve broker deal history.
        """

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
            return await self.broker.get_deals_by_position(
                position_id,
            )

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

        broker_name = getattr(
            adapter,
            "BROKER_NAME",
            None,
        )

        if broker_name:
            return str(broker_name)

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
        """
        Safely normalize an optional broker identifier.
        """

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _first_present(
        result: dict[str, Any],
        *keys: str,
    ) -> Any:
        """
        Return the first non-None value from the supplied keys.
        """

        for key in keys:
            value = result.get(key)

            if value is not None:
                return value

        return None
