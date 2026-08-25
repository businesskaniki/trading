from datetime import datetime, timezone
from decimal import Decimal

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

    Responsibilities:
    1. Read live positions from the broker.
    2. Match broker positions using broker ticket.
    3. Create missing AQE positions when an AQE Order exists.
    4. Update existing AQE positions.
    5. Ignore unmanaged broker positions.
    6. Detect AQE positions that no longer exist at the broker.
    7. Resolve the closing broker deal.
    8. Create the immutable Trade.
    9. Mark the Position CLOSED.
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
    # SYNC ALL POSITIONS
    # ==========================================================

    async def sync_positions(self):
        """
        Synchronize broker positions with AQE positions.
        """

        broker_positions = (
            await self.execution_service.get_positions()
        )

        synchronized = []

        broker_tickets = {
            int(position["ticket"])
            for position in broker_positions
            if position.get("ticket") is not None
        }

        # ------------------------------------------------------
        # Create / update live positions
        # ------------------------------------------------------

        for broker_position in broker_positions:

            position = await self._sync_position(
                broker_position
            )

            if position is not None:
                synchronized.append(position)

        # ------------------------------------------------------
        # Reconcile positions that disappeared
        # ------------------------------------------------------

        closed_positions = (
            await self._reconcile_closed_positions(
                broker_tickets
            )
        )

        synchronized.extend(
            closed_positions
        )

        return synchronized

    # ==========================================================
    # SYNC SINGLE POSITION
    # ==========================================================

    async def _sync_position(
        self,
        broker_position: dict,
    ):
        ticket = broker_position.get("ticket")

        if ticket is None:
            raise ValueError(
                "Broker position does not contain a ticket"
            )

        ticket = int(ticket)

        existing = (
            await self.position_repository.get_by_ticket(
                ticket
            )
        )

        if existing:
            return await self._update_existing_position(
                existing,
                broker_position,
            )

        return await self._create_position(
            broker_position
        )

    # ==========================================================
    # CREATE POSITION
    # ==========================================================

    async def _create_position(
        self,
        broker_position: dict,
    ):
        """
        Create an AQE Position from a broker position.

        Unmanaged broker positions are ignored.
        """

        ticket = int(
            broker_position["ticket"]
        )

        symbol = broker_position.get("symbol")

        if not symbol:
            raise ValueError(
                f"Broker position {ticket} has no symbol"
            )

        # ------------------------------------------------------
        # Find originating AQE Order
        # ------------------------------------------------------

        order = (
            await self.order_repository.get_by_ticket(
                ticket
            )
        )

        if not order:
            return None

        # ------------------------------------------------------
        # Direction
        # ------------------------------------------------------

        direction = self._map_direction(
            broker_position.get("type")
        )

        now = datetime.now(
            timezone.utc
        )

        # ------------------------------------------------------
        # Build AQE Position
        # ------------------------------------------------------

        position_data = PositionCreate(
            ticket=ticket,
            broker_position_id=str(ticket),
            strategy=order.strategy,
            account_id=order.account_id,
            symbol_id=order.symbol_id,
            order_id=order.id,
            direction=direction,
            volume=Decimal(
                str(
                    broker_position["volume"]
                )
            ),
            current_volume=Decimal(
                str(
                    broker_position["volume"]
                )
            ),
            entry_price=Decimal(
                str(
                    broker_position["price_open"]
                )
            ),
            current_price=Decimal(
                str(
                    broker_position["price_current"]
                )
            ),
            stop_loss=self._decimal_or_none(
                broker_position.get("sl")
            ),
            take_profit=self._decimal_or_none(
                broker_position.get("tp")
            ),
            floating_profit=Decimal(
                str(
                    broker_position.get(
                        "profit",
                        0,
                    )
                )
            ),
            swap=Decimal(
                str(
                    broker_position.get(
                        "swap",
                        0,
                    )
                )
            ),
            commission=Decimal("0"),
            initial_risk=None,
            opened_at=now,
            last_updated_price_at=now,
            comment=broker_position.get(
                "comment"
            ),
        )

        return await self.position_service.create_position(
            position_data
        )

    # ==========================================================
    # UPDATE POSITION
    # ==========================================================

    async def _update_existing_position(
        self,
        position,
        broker_position: dict,
    ):
        now = datetime.now(
            timezone.utc
        )

        update_data = PositionUpdate(
            current_volume=Decimal(
                str(
                    broker_position.get(
                        "volume",
                        position.current_volume,
                    )
                )
            ),
            current_price=Decimal(
                str(
                    broker_position.get(
                        "price_current",
                        position.current_price,
                    )
                )
            ),
            stop_loss=self._decimal_or_none(
                broker_position.get("sl")
            ),
            take_profit=self._decimal_or_none(
                broker_position.get("tp")
            ),
            floating_profit=Decimal(
                str(
                    broker_position.get(
                        "profit",
                        position.floating_profit,
                    )
                )
            ),
            swap=Decimal(
                str(
                    broker_position.get(
                        "swap",
                        position.swap,
                    )
                )
            ),
            last_updated_price_at=now,
            comment=broker_position.get(
                "comment",
                position.comment,
            ),
        )

        return await self.position_service.update_position(
            position.id,
            update_data,
        )

    # ==========================================================
    # RECONCILE CLOSED POSITIONS
    # ==========================================================

    async def _reconcile_closed_positions(
        self,
        broker_tickets: set[int],
    ):
        """
        Find AQE positions that are OPEN in PostgreSQL but no longer
        exist in the broker's live position list.

        For each missing broker position:
            1. Find the closing deal.
            2. Mark the AQE Position CLOSED.
            3. Create the corresponding immutable Trade.
        """

        open_positions = (
            await self.position_repository.get_open_positions()
        )

        closed_positions = []

        for position in open_positions:

            # ------------------------------------------------------
            # Position is still open at the broker
            # ------------------------------------------------------

            if position.ticket in broker_tickets:
                continue

            # ------------------------------------------------------
            # Position disappeared from broker.
            # Reconcile its closing transaction.
            # ------------------------------------------------------

            closed_position = (
                await self._close_position_and_create_trade(
                    position
                )
            )

            closed_positions.append(
                closed_position
            )

        return closed_positions
    # ==========================================================
    # CLOSE POSITION + CREATE TRADE
    # ==========================================================

    async def _close_position_and_create_trade(
        self,
        position,
    ):
        """
        Reconcile a broker position that has disappeared from the
        live broker position list.

        Workflow:
            1. Retrieve deals for this exact broker position.
            2. Find the closing deal.
            3. Calculate final trade values.
            4. Mark the AQE Position CLOSED without committing.
            5. Create the immutable Trade without committing.
            6. Commit Position + Trade atomically.
            7. Roll back both if anything fails.
        """

        db = self.position_repository.db

        try:
            # ======================================================
            # 1. GET DEALS FOR THIS POSITION
            # ======================================================

            deals = (
                await self.execution_service.get_deals_by_position(
                    position.ticket
                )
            )

            if not deals:
                raise ValueError(
                    f"No deal history found for position "
                    f"{position.ticket}"
                )

            # ======================================================
            # 2. FIND CLOSING DEAL
            # ======================================================

            close_deal = self._find_closing_deal(
                deals
            )

            if close_deal is None:
                raise ValueError(
                    f"Could not find closing deal for position "
                    f"{position.ticket}"
                )

            # ======================================================
            # 3. EXTRACT CLOSE DATA
            # ======================================================

            exit_price = Decimal(
                str(
                    close_deal["price"]
                )
            )

            close_volume = Decimal(
                str(
                    close_deal.get(
                        "volume",
                        position.current_volume,
                    )
                )
            )

            gross_profit = Decimal(
                str(
                    close_deal.get(
                        "profit",
                        0,
                    )
                )
            )

            commission = Decimal(
                str(
                    close_deal.get(
                        "commission",
                        0,
                    )
                )
            )

            swap = Decimal(
                str(
                    close_deal.get(
                        "swap",
                        0,
                    )
                )
            )

            # The Bridge currently does not expose a separate fee field.
            fees = Decimal("0")

            # MT5 already provides the broker-level signed values.
            net_profit = (
                gross_profit
                + commission
                + swap
                + fees
            )

            closed_at = self._parse_broker_time(
                close_deal.get("time"),
                fallback=datetime.now(timezone.utc),
            )

            duration_seconds = max(
                int(
                    (
                        closed_at
                        - position.opened_at
                    ).total_seconds()
                ),
                0,
            )

            profit_percent = None

            if position.entry_price > 0:
                profit_percent = (
                    net_profit
                    / position.entry_price
                ) * Decimal("100")

            trade_result = (
                self._calculate_trade_result(
                    net_profit
                )
            )

            close_ticket = int(
                close_deal["ticket"]
            )

            # ======================================================
            # 4. CHECK FOR EXISTING TRADE
            # ======================================================

            try:
                existing_trade = (
                    await self.trade_service.get_trade_by_position(
                        position.id
                    )
                )

            except ValueError:
                existing_trade = None

            # ======================================================
            # 5. IF TRADE ALREADY EXISTS
            # ======================================================

            if existing_trade:

                # Position may have remained OPEN if a previous
                # synchronization failed after creating the Trade.
                if position.status != PositionStatus.CLOSED:

                    await self._mark_position_closed(
                        position=position,
                        closed_at=closed_at,
                        exit_price=exit_price,
                        commit=False,
                    )

                    await db.commit()

                return position

            # ======================================================
            # 6. BUILD TRADE
            # ======================================================

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
                max_favorable_excursion=None,
                max_adverse_excursion=None,
                result=trade_result,
                opened_at=position.opened_at,
                closed_at=closed_at,
                duration_seconds=duration_seconds,
                comment=close_deal.get(
                    "comment",
                    position.comment,
                ),
            )

            # ======================================================
            # 7. MARK POSITION CLOSED
            # ======================================================
            #
            # IMPORTANT:
            # commit=False keeps this operation inside the
            # current SQLAlchemy transaction.
            #

            closed_position = (
                await self._mark_position_closed(
                    position=position,
                    closed_at=closed_at,
                    exit_price=exit_price,
                    commit=False,
                )
            )

            # ======================================================
            # 8. CREATE TRADE
            # ======================================================
            #
            # TradeService sees the in-memory/flushed Position as
            # CLOSED and therefore passes its validation.
            #

            await self.trade_service.create_trade(
                trade_data,
                commit=False,
            )

            # ======================================================
            # 9. ATOMIC COMMIT
            # ======================================================

            await db.commit()

            return closed_position

        except Exception:
            # ======================================================
            # ROLLBACK
            # ======================================================

            await db.rollback()

            raise

        #=========================================================
        # MARK POSITION CLOSED
        # ==========================================================

        async def _mark_position_closed(
            self,
            position,
            closed_at: datetime,
            exit_price: Decimal,
        ):
            return await self.position_service.update_position(
                position.id,
                PositionUpdate(
                    status=PositionStatus.CLOSED,
                    current_volume=Decimal("0"),
                    current_price=exit_price,
                    closed_at=closed_at,
                    last_updated_price_at=closed_at,
                ),
            )

    # ==========================================================
    # FIND CLOSING DEAL
    # ==========================================================

    @staticmethod
    def _find_closing_deal(
        deals,
    ):
        """
        Find the closing deal from the deals belonging to
        a specific position.

        MT5:
            entry=0 → IN
            entry=1 → OUT
            entry=2 → INOUT
            entry=3 → OUT_BY
        """

        candidates = [
            deal
            for deal in deals
            if deal.get("entry") in (1, 2, 3)
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda deal: deal.get(
                "time",
                0,
            )
        )

        return candidates[-1]
    # ==========================================================
    # PROFIT PERCENT
    # ==========================================================

    @staticmethod
    def _calculate_profit_percent(
        position,
        net_profit: Decimal,
    ) -> Decimal | None:

        if position.entry_price <= 0:
            return None

        return (
            net_profit
            / position.entry_price
        ) * Decimal("100")

    # ==========================================================
    # TRADE RESULT
    # ==========================================================

    @staticmethod
    def _calculate_trade_result(
        net_profit: Decimal,
    ) -> TradeResult:

        if net_profit > 0:
            return TradeResult.WIN

        if net_profit < 0:
            return TradeResult.LOSS

        return TradeResult.BREAKEVEN

    # ==========================================================
    # DIRECTION
    # ==========================================================

    @staticmethod
    def _map_direction(
        broker_type,
    ) -> PositionDirection:

        if broker_type == 0:
            return PositionDirection.BUY

        if broker_type == 1:
            return PositionDirection.SELL

        raise ValueError(
            f"Unsupported broker position type: {broker_type}"
        )

    # ==========================================================
    # DECIMAL HELPER
    # ==========================================================

    @staticmethod
    def _decimal_or_none(
        value,
    ) -> Decimal | None:

        if value is None:
            return None

        value = Decimal(
            str(value)
        )

        if value == 0:
            return None

        return value

    # ==========================================================
    # BROKER TIME
    # ==========================================================

    @staticmethod
    def _parse_broker_time(
        value,
        fallback: datetime,
    ) -> datetime:

        if value is None:
            return fallback

        if isinstance(
            value,
            datetime,
        ):
            if value.tzinfo is None:
                return value.replace(
                    tzinfo=timezone.utc
                )

            return value

        if isinstance(
            value,
            (int, float),
        ):
            return datetime.fromtimestamp(
                value,
                tz=timezone.utc,
            )

        return fallback



    async def _mark_position_closed(
        self,
        position,
        closed_at: datetime,
        exit_price: Decimal,
        commit: bool = True,
    ):
        return await self.position_service.update_position(
            position.id,
            PositionUpdate(
                status=PositionStatus.CLOSED,
                current_volume=Decimal("0"),
                current_price=exit_price,
                closed_at=closed_at,
                last_updated_price_at=closed_at,
            ),
            commit=commit,
        )