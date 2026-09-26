from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.constants import (
    PositionDirection,
    PositionStatus,
    TradeResult,
)
from app.repositories.order_repository import OrderRepository
from app.repositories.position_repository import PositionRepository
from app.schemas.position import PositionCreate, PositionUpdate
from app.schemas.trade import TradeCreate
from app.services.execution_service import ExecutionService
from app.services.position_service import PositionService
from app.services.trade_service import TradeService


class PositionSyncService:
    """
    Synchronizes broker positions with AQE Position records.

    Broker identity is kept explicit:

        MT5 position.ticket
            -> AQE Position.ticket

        MT5 position.identifier
            -> AQE Position.broker_position_id

        MT5 opening deal.order
            -> AQE Order.broker_order_id

        MT5 opening deal.ticket
            -> AQE Order.broker_deal_id

        MT5 closing deal.ticket
            -> AQE Trade.ticket

    A broker position ticket is never treated as an order ticket.

    Historical deal lookups use the broker position identifier
    because MT5 history_deals_get(position=...) is keyed by the
    position identifier, not the position ticket.
    """

    def __init__(
        self,
        execution_service: ExecutionService,
        position_repository: PositionRepository,
        position_service: PositionService,
        order_repository: OrderRepository,
        trade_service: TradeService,
    ):
        self.execution_service = execution_service
        self.position_repository = position_repository
        self.position_service = position_service
        self.order_repository = order_repository
        self.trade_service = trade_service

    # ==========================================================
    # PUBLIC SYNC
    # ==========================================================

    async def sync_positions(
        self,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Synchronize AQE positions against the current broker state.

        The synchronization is intentionally one-way:

            broker -> AQE

        Broker positions are authoritative for live position state.
        """

        broker_positions = await self.execution_service.get_positions()
        broker_positions = broker_positions or []

        broker_tickets: set[int] = set()

        created = 0
        updated = 0
        ignored = 0

        for broker_position in broker_positions:
            ticket = self._extract_ticket(broker_position)

            if ticket is None:
                ignored += 1
                continue

            broker_tickets.add(ticket)

            existing = await self.position_repository.get_by_ticket(ticket)

            if existing is not None:
                if user_id is not None and existing.account.user_id != user_id:
                    ignored += 1
                    continue

                await self._update_existing_position(
                    existing,
                    broker_position,
                )

                updated += 1
                continue

            position = await self._create_position(
                broker_position,
                user_id=user_id,
            )

            if position is None:
                ignored += 1
            else:
                created += 1

        closed_positions = await self._reconcile_closed_positions(
            broker_tickets=broker_tickets,
            user_id=user_id,
        )

        return {
            "broker_positions": len(broker_positions),
            "created": created,
            "updated": updated,
            "closed": len(closed_positions),
            "ignored": ignored,
        }

    # ==========================================================
    # CREATE
    # ==========================================================

    async def _create_position(
        self,
        broker_position: dict[str, Any],
        user_id: UUID | None = None,
    ):
        """
        Create an AQE Position for a broker position.

        Positions are only imported when they can be correlated
        with an AQE Order.

        Manually opened or externally managed broker positions
        are intentionally ignored.
        """

        ticket = self._extract_ticket(broker_position)

        if ticket is None:
            raise ValueError("Broker position does not contain a valid ticket.")

        symbol = broker_position.get("symbol")

        if not symbol:
            raise ValueError(f"Broker position {ticket} does not contain a symbol.")

        broker_position_id = self._extract_broker_position_id(broker_position)

        order = await self._resolve_originating_order(
            broker_position=broker_position,
            broker_position_id=broker_position_id,
        )

        if order is None:
            return None

        if user_id is not None and order.account.user_id != user_id:
            return None

        direction = self._map_direction(broker_position.get("type"))

        now = datetime.now(timezone.utc)

        volume = self._decimal(
            broker_position.get("volume"),
            default=Decimal("0"),
        )

        if volume <= 0:
            raise ValueError(f"Broker position {ticket} has invalid volume.")

        entry_price = self._decimal(
            broker_position.get("price_open"),
            default=Decimal("0"),
        )

        current_price = self._decimal(
            broker_position.get("price_current"),
            default=Decimal("0"),
        )

        if entry_price <= 0:
            raise ValueError(f"Broker position {ticket} has invalid entry price.")

        if current_price <= 0:
            current_price = entry_price

        opened_at = self._parse_broker_time(
            broker_position.get("time"),
            fallback=now,
        )

        stop_loss = self._decimal_or_none(broker_position.get("sl"))

        take_profit = self._decimal_or_none(broker_position.get("tp"))

        position_data = PositionCreate(
            ticket=ticket,
            broker_position_id=broker_position_id,
            strategy=order.strategy,
            account_id=order.account_id,
            symbol_id=order.symbol_id,
            order_id=order.id,
            direction=direction,
            volume=volume,
            current_volume=volume,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            floating_profit=self._decimal(
                broker_position.get("profit"),
                default=Decimal("0"),
            ),
            swap=self._decimal(
                broker_position.get("swap"),
                default=Decimal("0"),
            ),
            commission=self._decimal(
                broker_position.get("commission"),
                default=Decimal("0"),
            ),
            initial_risk=None,
            opened_at=opened_at,
            last_updated_price_at=now,
            comment=(broker_position.get("comment") or order.comment),
        )

        position = await self.position_service.create_position(position_data)

        # Order.broker_position_id stores MT5's numeric
        # position identifier.
        #
        # Position.broker_position_id stores the same value
        # as a string.
        broker_position_numeric_id = self._extract_int(
            broker_position.get("identifier")
        )

        if order.broker_position_id is None and broker_position_numeric_id is not None:
            order.broker_position_id = broker_position_numeric_id
            await self.order_repository.db.flush()

        return position

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def _update_existing_position(
        self,
        position,
        broker_position: dict[str, Any],
    ):
        """
        Update an existing AQE Position from current broker state.

        The broker remains authoritative for live position values.
        """

        now = datetime.now(timezone.utc)

        current_volume = self._decimal(
            broker_position.get("volume"),
            default=position.current_volume,
        )

        if current_volume < 0:
            raise ValueError(f"Broker position {position.ticket} has invalid volume.")

        current_price = self._decimal(
            broker_position.get("price_current"),
            default=position.current_price,
        )

        broker_position_id = self._extract_broker_position_id(broker_position)

        update_data = PositionUpdate(
            broker_position_id=(broker_position_id or position.broker_position_id),
            current_volume=current_volume,
            current_price=current_price,
            stop_loss=self._decimal_or_none(broker_position.get("sl")),
            take_profit=self._decimal_or_none(broker_position.get("tp")),
            floating_profit=self._decimal(
                broker_position.get("profit"),
                default=position.floating_profit,
            ),
            swap=self._decimal(
                broker_position.get("swap"),
                default=position.swap,
            ),
            commission=self._decimal(
                broker_position.get("commission"),
                default=position.commission,
            ),
            last_updated_price_at=now,
            comment=(broker_position.get("comment") or position.comment),
        )

        return await self.position_service.update_position(
            position.id,
            update_data,
        )

    # ==========================================================
    # ORDER CORRELATION
    # ==========================================================

    async def _resolve_originating_order(
        self,
        broker_position: dict[str, Any],
        broker_position_id: str | None,
    ):
        """
        Resolve the AQE Order that created the broker position.

        Resolution order:

        1. Existing AQE correlation by broker position identifier.
        2. Broker opening deal -> broker order ID.
        3. Broker opening deal -> broker deal ID.

        The position ticket itself is never queried as an
        AQE broker order ID.
        """

        # ------------------------------------------------------
        # 1. Existing broker-position correlation
        # ------------------------------------------------------

        numeric_position_id = self._extract_int(broker_position_id)

        if numeric_position_id is not None:
            order = await self.order_repository.get_by_broker_position_id(
                numeric_position_id
            )

            if order is not None:
                return order

        # ------------------------------------------------------
        # 2. Resolve through broker deal history
        # ------------------------------------------------------

        position_identifier = self._extract_int(broker_position.get("identifier"))

        if position_identifier is None:
            return None

        try:
            deals = await self.execution_service.get_deals_by_position(
                position_identifier
            )
        except Exception:
            return None

        opening_deal = self._find_opening_deal(deals)

        if opening_deal is None:
            return None

        # ------------------------------------------------------
        # 2a. Opening deal -> broker order
        # ------------------------------------------------------

        broker_order_id = self._extract_int(opening_deal.get("order"))

        if broker_order_id is not None:
            order = await self.order_repository.get_by_broker_order_id(broker_order_id)

            if order is not None:
                return order

        # ------------------------------------------------------
        # 2b. Opening deal -> broker deal
        # ------------------------------------------------------

        broker_deal_id = self._extract_int(opening_deal.get("ticket"))

        if broker_deal_id is not None:
            order = await self.order_repository.get_by_broker_deal_id(broker_deal_id)

            if order is not None:
                return order

        return None

    # ==========================================================
    # CLOSED POSITION RECONCILIATION
    # ==========================================================

    async def _reconcile_closed_positions(
        self,
        broker_tickets: set[int],
        user_id: UUID | None = None,
    ) -> list:
        """
        Detect AQE positions that remain OPEN in AQE but no longer
        exist at the broker.

        A missing broker position is only closed in AQE when a
        valid closing deal can be resolved.
        """

        open_positions = await self.position_repository.get_open_positions()

        closed_positions = []

        for position in open_positions:
            if user_id is not None and position.account.user_id != user_id:
                continue

            if position.ticket in broker_tickets:
                continue

            closed_position = await self._close_position_and_create_trade(position)

            if closed_position is not None:
                closed_positions.append(closed_position)

        return closed_positions

    # ==========================================================
    # CLOSE + TRADE
    # ==========================================================

    async def _close_position_and_create_trade(
        self,
        position,
    ):
        """
        Resolve the closing broker deal, close the AQE Position,
        create the immutable Trade, and commit both atomically.

        Current implementation intentionally handles the normal
        full-close case.

        Partial-close aggregation is deferred until AQE supports
        multi-deal position accounting.
        """

        db = self.position_repository.db

        try:
            position_identifier = self._extract_int(position.broker_position_id)

            if position_identifier is None:
                return None

            deals = await self.execution_service.get_deals_by_position(
                position_identifier
            )

            if not deals:
                return None

            close_deal = self._find_closing_deal(deals)

            if close_deal is None:
                return None

            exit_price = self._decimal(
                close_deal.get("price"),
                default=Decimal("0"),
            )

            if exit_price <= 0:
                raise ValueError(
                    f"Closing deal for position {position.ticket} "
                    "has an invalid price."
                )

            close_volume = self._decimal(
                close_deal.get("volume"),
                default=position.current_volume,
            )

            gross_profit = self._decimal(
                close_deal.get("profit"),
                default=Decimal("0"),
            )

            commission = self._decimal(
                close_deal.get("commission"),
                default=Decimal("0"),
            )

            swap = self._decimal(
                close_deal.get("swap"),
                default=Decimal("0"),
            )

            fees = self._decimal(
                close_deal.get("fees"),
                default=Decimal("0"),
            )

            net_profit = gross_profit + commission + swap + fees

            closed_at = self._parse_broker_time(
                close_deal.get("time"),
                fallback=datetime.now(timezone.utc),
            )

            duration_seconds = max(
                int((closed_at - position.opened_at).total_seconds()),
                0,
            )

            profit_percent = self._calculate_profit_percent(
                position,
                net_profit,
            )

            trade_result = self._calculate_trade_result(net_profit)

            close_ticket = self._extract_int(close_deal.get("ticket"))

            if close_ticket is None:
                raise ValueError(
                    f"Closing deal for position {position.ticket} "
                    "does not contain a deal ticket."
                )

            # --------------------------------------------------
            # Idempotency
            # --------------------------------------------------

            existing_trade = await self.trade_service.get_trade_by_position(position.id)

            if existing_trade is not None:
                if position.status != PositionStatus.CLOSED:
                    await self._mark_position_closed(
                        position=position,
                        closed_at=closed_at,
                        exit_price=exit_price,
                        commit=False,
                    )

                    await db.commit()

                return position

            # --------------------------------------------------
            # Build immutable trade
            # --------------------------------------------------

            trade_data = TradeCreate(
                ticket=close_ticket,
                strategy=position.strategy,
                position_id=position.id,
                account_id=position.account_id,
                symbol_id=position.symbol_id,
                direction=position.direction,
                volume=close_volume,
                entry_price=position.entry_price,
                exit_price=exit_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                gross_profit=gross_profit,
                commission=commission,
                swap=swap,
                fees=fees,
                net_profit=net_profit,
                profit_percent=profit_percent,
                initial_risk=position.initial_risk,
                reward_risk_ratio=position.risk_reward_ratio,
                mfe=None,
                mae=None,
                result=trade_result,
                opened_at=position.opened_at,
                closed_at=closed_at,
                duration_seconds=duration_seconds,
                comment=position.comment,
            )

            # --------------------------------------------------
            # Close position without committing
            # --------------------------------------------------

            closed_position = await self._mark_position_closed(
                position=position,
                closed_at=closed_at,
                exit_price=exit_price,
                commit=False,
            )

            # --------------------------------------------------
            # Create trade in the same transaction
            # --------------------------------------------------

            await self.trade_service.create_trade(
                trade_data,
                commit=False,
            )

            # --------------------------------------------------
            # Atomic commit
            # --------------------------------------------------

            await db.commit()

            return closed_position

        except Exception:
            await db.rollback()
            raise

    # ==========================================================
    # DEAL HELPERS
    # ==========================================================

    @staticmethod
    def _find_opening_deal(
        deals: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        """
        Find the broker deal that opened the position.

        MT5 deal entry values:

            0 = IN
            1 = OUT
            2 = INOUT
            3 = OUT_BY
        """

        if not deals:
            return None

        opening_deals = [
            deal
            for deal in deals
            if PositionSyncService._extract_int(deal.get("entry")) == 0
        ]

        if not opening_deals:
            return None

        return max(
            opening_deals,
            key=lambda deal: (
                PositionSyncService._broker_time_sort_key(deal.get("time"))
            ),
        )

    @staticmethod
    def _find_closing_deal(
        deals: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        """
        Find the latest closing deal.

        This handles the normal full-close case.

        Partial-close aggregation is intentionally deferred.
        """

        if not deals:
            return None

        closing_deals = [
            deal
            for deal in deals
            if PositionSyncService._extract_int(deal.get("entry")) in {1, 2, 3}
        ]

        if not closing_deals:
            return None

        return max(
            closing_deals,
            key=lambda deal: (
                PositionSyncService._broker_time_sort_key(deal.get("time"))
            ),
        )

    # ==========================================================
    # POSITION CLOSE
    # ==========================================================

    async def _mark_position_closed(
        self,
        position,
        closed_at: datetime,
        exit_price: Decimal,
        commit: bool = True,
    ):
        """
        Mark an AQE Position as closed.
        """

        return await self.position_service.update_position(
            position.id,
            PositionUpdate(
                current_volume=Decimal("0"),
                current_price=exit_price,
                status=PositionStatus.CLOSED,
                closed_at=closed_at,
                last_updated_price_at=closed_at,
            ),
            commit=commit,
        )

    # ==========================================================
    # MAPPERS
    # ==========================================================

    @staticmethod
    def _map_direction(
        broker_type: Any,
    ) -> PositionDirection:
        """
        MT5 position type:

            0 = BUY
            1 = SELL
        """

        position_type = PositionSyncService._extract_int(broker_type)

        if position_type == 0:
            return PositionDirection.LONG

        if position_type == 1:
            return PositionDirection.SHORT

        raise ValueError(f"Unsupported broker position type: {broker_type!r}")

    # ==========================================================
    # VALUE HELPERS
    # ==========================================================

    @staticmethod
    def _extract_ticket(
        broker_position: dict[str, Any],
    ) -> int | None:
        return PositionSyncService._extract_int(broker_position.get("ticket"))

    @staticmethod
    def _extract_broker_position_id(
        broker_position: dict[str, Any],
    ) -> str | None:
        """
        Position.broker_position_id stores MT5's identifier.

        This is deliberately distinct from ticket.
        """

        identifier = broker_position.get("identifier")

        if identifier is not None:
            value = PositionSyncService._extract_int(identifier)

            if value is not None:
                return str(value)

        return None

    @staticmethod
    def _extract_int(
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal(
        value: Any,
        default: Decimal,
    ) -> Decimal:
        if value is None:
            return default

        try:
            return Decimal(str(value))
        except Exception:
            return default

    @staticmethod
    def _decimal_or_none(
        value: Any,
    ) -> Decimal | None:
        if value is None:
            return None

        try:
            decimal_value = Decimal(str(value))
        except Exception:
            return None

        if decimal_value <= 0:
            return None

        return decimal_value

    @staticmethod
    def _parse_broker_time(
        value: Any,
        fallback: datetime,
    ) -> datetime:
        if value is None:
            return fallback

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)

            return value.astimezone(timezone.utc)

        try:
            return datetime.fromtimestamp(
                float(value),
                tz=timezone.utc,
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return fallback

    @staticmethod
    def _broker_time_sort_key(
        value: Any,
    ) -> float:
        if value is None:
            return 0.0

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            return value.timestamp()

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # ==========================================================
    # PROFIT / RESULT
    # ==========================================================

    @staticmethod
    def _calculate_profit_percent(
        position,
        net_profit: Decimal,
    ) -> Decimal | None:
        if position.entry_price <= 0:
            return None

        return net_profit / position.entry_price * Decimal("100")

    @staticmethod
    def _calculate_trade_result(
        net_profit: Decimal,
    ) -> TradeResult:
        if net_profit > 0:
            return TradeResult.WIN

        if net_profit < 0:
            return TradeResult.LOSS

        return TradeResult.BREAKEVEN
