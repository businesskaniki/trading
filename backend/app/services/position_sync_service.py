from __future__ import annotations

import logging

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.constants import (
    PositionDirection,
    PositionStatus,
    TradeResult,
)
from app.database.models.account_symbol import AccountSymbol
from app.database.models.trading_account import TradingAccount
from app.repositories.order_repository import OrderRepository
from app.repositories.position_repository import PositionRepository
from app.schemas.position import PositionCreate, PositionUpdate
from app.schemas.trade import TradeCreate
from app.services.execution_service import ExecutionService
from app.services.position_service import PositionService
from app.services.trade_service import TradeService

logger = logging.getLogger(__name__)


class PositionSyncService:
    """
    Synchronize live broker positions into AQE's position ledger.

    A position can be associated with an AQE Order or imported as an
    external position. Every imported position must still resolve to
    an AQE trading account and an account-specific canonical symbol.

    MT5 identifiers remain distinct:

        position.ticket     -> AQE Position.ticket
        position.identifier -> AQE Position.broker_position_id
        opening deal.order  -> AQE Order.broker_order_id
        opening deal.ticket -> AQE Order.broker_deal_id
        closing deal.ticket -> AQE Trade.ticket

    Historical deal lookups use the MT5 position identifier.
    """

    EXTERNAL_STRATEGY = "EXTERNAL"

    def __init__(
        self,
        execution_service: ExecutionService,
        position_repository: PositionRepository,
        position_service: PositionService,
        order_repository: OrderRepository,
        trade_service: TradeService,
    ) -> None:
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
        Synchronize positions from the currently connected broker account.

        The connected account is resolved before reconciliation so a
        snapshot for one account cannot close positions belonging to
        another account.
        """

        account = await self._resolve_connected_account(user_id=user_id)

        broker_positions = await self.execution_service.get_positions()
        broker_positions = broker_positions or []

        logger.info(
            "Position sync started. account_id=%s broker_positions=%s",
            account.id,
            len(broker_positions),
        )

        broker_tickets: set[int] = set()
        created = 0
        updated = 0
        ignored = 0

        for broker_position in broker_positions:
            ticket = self._extract_ticket(broker_position)

            if ticket is None:
                logger.warning(
                    "Ignoring broker position without a valid ticket: %s",
                    broker_position,
                )
                ignored += 1
                continue

            broker_tickets.add(ticket)

            existing = await self.position_repository.get_by_ticket(ticket)

            if existing is not None:
                if existing.account_id != account.id:
                    logger.error(
                        "Broker ticket collision across accounts. "
                        "ticket=%s existing_account=%s connected_account=%s",
                        ticket,
                        existing.account_id,
                        account.id,
                    )
                    ignored += 1
                    continue

                await self._update_existing_position(
                    existing,
                    broker_position,
                )
                updated += 1
                continue

            try:
                position = await self._create_position(
                    broker_position=broker_position,
                    account=account,
                    user_id=user_id,
                )
            except ValueError as exc:
                logger.warning(
                    "Position not imported. ticket=%s account_id=%s reason=%s",
                    ticket,
                    account.id,
                    exc,
                )
                ignored += 1
                continue

            if position is None:
                ignored += 1
            else:
                created += 1

        closed_positions = await self._reconcile_closed_positions(
            broker_tickets=broker_tickets,
            account_id=account.id,
        )

        result = {
            "account_id": str(account.id),
            "broker_positions": len(broker_positions),
            "created": created,
            "updated": updated,
            "closed": len(closed_positions),
            "ignored": ignored,
        }

        logger.info("Position sync completed: %s", result)

        return result

    # ==========================================================
    # CONNECTED ACCOUNT
    # ==========================================================

    async def _resolve_connected_account(
        self,
        user_id: UUID | None,
    ):
        """
        Resolve the local account from the explicitly scoped execution
        service or the connected broker's login/server identity.

        This fails closed when the connected account cannot be uniquely
        matched. It never assigns an external position to an arbitrary
        account owned by the user.
        """

        db = self.position_repository.db

        configured_account_id = getattr(
            self.execution_service,
            "account_id",
            None,
        )

        if configured_account_id is not None:
            try:
                account_uuid = UUID(str(configured_account_id))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Execution service has an invalid account_id."
                ) from exc

            statement = select(TradingAccount).where(
                TradingAccount.id == account_uuid,
            )

            if user_id is not None:
                statement = statement.where(
                    TradingAccount.user_id == user_id,
                )

            result = await db.execute(statement)
            account = result.scalar_one_or_none()

            if account is None:
                raise ValueError(
                    "The execution service account does not belong to "
                    "the authenticated user or does not exist."
                )

            return account

        get_account = getattr(self.execution_service, "get_account", None)

        if not callable(get_account):
            raise ValueError(
                "Cannot identify the connected broker account: "
                "ExecutionService.get_account() is unavailable."
            )

        try:
            broker_account = await get_account()
        except Exception as exc:
            raise ValueError(
                f"Unable to retrieve connected broker account: {exc}"
            ) from exc

        broker_account = self._to_mapping(broker_account)

        if not broker_account:
            raise ValueError(
                "Broker returned no account identity; refusing an "
                "unscoped position synchronization."
            )

        nested_account = broker_account.get("account")

        if isinstance(nested_account, dict):
            broker_account = {
                **broker_account,
                **nested_account,
            }

        login = self._extract_int(broker_account.get("login"))
        server = broker_account.get("server")

        if login is None:
            raise ValueError("Broker account response does not contain a valid login.")

        statement = select(TradingAccount).where(
            TradingAccount.login == login,
        )

        if server:
            statement = statement.where(
                TradingAccount.server == str(server).strip(),
            )

        if user_id is not None:
            statement = statement.where(
                TradingAccount.user_id == user_id,
            )

        result = await db.execute(statement)
        accounts = result.scalars().all()

        if len(accounts) != 1:
            raise ValueError(
                "Connected broker account could not be matched uniquely "
                "to a local trading account. Check the stored login and "
                "server, and ensure the broker account is connected."
            )

        return accounts[0]

    async def _resolve_account_symbol_id(
        self,
        account_id: UUID,
        broker_symbol: str,
    ) -> UUID:
        """
        Resolve the exact broker-native symbol to its canonical AQE symbol.

        Broker casing and suffixes are preserved. AccountSymbol.enabled
        is deliberately not checked: a currently open position must still
        be tracked if the symbol has since been disabled for new trading.
        """

        statement = select(AccountSymbol).where(
            AccountSymbol.account_id == account_id,
            AccountSymbol.broker_symbol == broker_symbol,
        )

        result = await self.position_repository.db.execute(statement)
        matches = result.scalars().all()

        if not matches:
            raise ValueError(
                f"No AccountSymbol mapping exists for broker symbol "
                f"{broker_symbol!r} on account {account_id}."
            )

        if len(matches) != 1:
            raise ValueError(
                f"Broker symbol {broker_symbol!r} resolves to multiple "
                f"account-symbol mappings on account {account_id}."
            )

        return matches[0].symbol_id

    # ==========================================================
    # CREATE
    # ==========================================================

    async def _create_position(
        self,
        broker_position: dict[str, Any],
        account,
        user_id: UUID | None = None,
    ):
        ticket = self._extract_ticket(broker_position)

        if ticket is None:
            raise ValueError("Broker position has no valid ticket.")

        broker_symbol_value = broker_position.get("symbol")

        if not broker_symbol_value:
            raise ValueError(f"Broker position {ticket} has no symbol.")

        broker_symbol = str(broker_symbol_value).strip()

        broker_position_id = self._extract_broker_position_id(
            broker_position,
        )

        order = await self._resolve_originating_order(
            broker_position=broker_position,
            broker_position_id=broker_position_id,
        )

        # Never associate a position with an order from another account.
        if order is not None and order.account_id != account.id:
            logger.warning(
                "Order correlation belongs to another account; importing "
                "as external. ticket=%s order_id=%s order_account=%s "
                "connected_account=%s",
                ticket,
                order.id,
                order.account_id,
                account.id,
            )
            order = None

        if order is not None and user_id is not None:
            if order.account.user_id != user_id:
                logger.warning(
                    "Order correlation belongs to another user. "
                    "ticket=%s order_id=%s",
                    ticket,
                    order.id,
                )
                order = None

        # For AQE-originated positions, preserve the original canonical
        # symbol. For external positions, resolve through AccountSymbol.
        if order is not None:
            symbol_id = order.symbol_id
            strategy = order.strategy
        else:
            symbol_id = await self._resolve_account_symbol_id(
                account_id=account.id,
                broker_symbol=broker_symbol,
            )
            strategy = self.EXTERNAL_STRATEGY

        direction = self._map_direction(
            broker_position.get("type"),
        )

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

        position_data = PositionCreate(
            ticket=ticket,
            broker_position_id=broker_position_id,
            strategy=strategy,
            account_id=account.id,
            symbol_id=symbol_id,
            order_id=order.id if order is not None else None,
            direction=direction,
            volume=volume,
            current_volume=volume,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=self._decimal_or_none(
                broker_position.get("sl"),
            ),
            take_profit=self._decimal_or_none(
                broker_position.get("tp"),
            ),
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
            comment=(
                broker_position.get("comment")
                or (order.comment if order is not None else None)
            ),
        )

        # Repair the AQE Order -> MT5 position correlation before creating
        # the position. Both changes use the same database session.
        if order is not None and order.broker_position_id is None:
            broker_position_numeric_id = self._extract_int(
                broker_position.get("identifier"),
            )

            if broker_position_numeric_id is not None:
                order.broker_position_id = broker_position_numeric_id

        position = await self.position_service.create_position(
            position_data,
            user_id=user_id,
        )

        logger.info(
            "Created position from broker state. position_id=%s "
            "ticket=%s broker_position_id=%s order_id=%s account_id=%s "
            "strategy=%s",
            position.id,
            position.ticket,
            position.broker_position_id,
            position.order_id,
            position.account_id,
            position.strategy,
        )

        return position

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def _update_existing_position(
        self,
        position,
        broker_position: dict[str, Any],
    ):
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

        broker_position_id = self._extract_broker_position_id(
            broker_position,
        )

        update_data = PositionUpdate(
            broker_position_id=(broker_position_id or position.broker_position_id),
            current_volume=current_volume,
            current_price=current_price,
            stop_loss=self._decimal_or_none(
                broker_position.get("sl"),
            ),
            take_profit=self._decimal_or_none(
                broker_position.get("tp"),
            ),
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
        Correlate the broker position to an AQE Order where possible.

        A missing correlation is not a reason to drop the position.
        The caller will import it as EXTERNAL if account/symbol resolution
        succeeds.
        """

        numeric_position_id = self._extract_int(
            broker_position_id,
        )

        if numeric_position_id is not None:
            order = await self.order_repository.get_by_broker_position_id(
                numeric_position_id,
            )

            if order is not None:
                return order

            # Retained as a fallback for accounts where the position
            # identifier can match the opening broker order ID.
            order = await self.order_repository.get_by_broker_order_id(
                numeric_position_id,
            )

            if order is not None:
                return order

        position_identifier = numeric_position_id or self._extract_ticket(
            broker_position
        )

        if position_identifier is None:
            return None

        try:
            deals = await self.execution_service.get_deals_by_position(
                position_identifier,
            )
        except Exception:
            logger.debug(
                "Unable to retrieve deals for position identifier %s",
                position_identifier,
                exc_info=True,
            )
            return None

        opening_deal = self._find_opening_deal(deals)

        if opening_deal is None:
            return None

        broker_order_id = self._extract_int(
            opening_deal.get("order"),
        )

        if broker_order_id is not None:
            order = await self.order_repository.get_by_broker_order_id(
                broker_order_id,
            )

            if order is not None:
                return order

        broker_deal_id = self._extract_int(
            opening_deal.get("ticket"),
        )

        if broker_deal_id is not None:
            order = await self.order_repository.get_by_broker_deal_id(
                broker_deal_id,
            )

            if order is not None:
                return order

        return None

    # ==========================================================
    # CLOSED POSITION RECONCILIATION
    # ==========================================================

    async def _reconcile_closed_positions(
        self,
        broker_tickets: set[int],
        account_id: UUID,
    ) -> list:
        open_positions = await self.position_repository.get_open_positions()

        closed_positions = []

        for position in open_positions:
            # Only reconcile positions belonging to the account represented
            # by this broker snapshot.
            if position.account_id != account_id:
                continue

            if position.ticket in broker_tickets:
                continue

            closed_position = await self._close_position_and_create_trade(
                position,
            )

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
        Close a missing broker position only when a closing deal can be
        established. Position closure and Trade creation share a transaction.
        """

        db = self.position_repository.db

        position_identifier = self._extract_int(
            position.broker_position_id,
        )

        if position_identifier is None:
            logger.warning(
                "Cannot reconcile closed position without broker identifier. "
                "position_id=%s ticket=%s",
                position.id,
                position.ticket,
            )
            return None

        try:
            deals = await self.execution_service.get_deals_by_position(
                position_identifier,
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

            close_ticket = self._extract_int(
                close_deal.get("ticket"),
            )

            if close_ticket is None:
                raise ValueError(
                    f"Closing deal for position {position.ticket} "
                    "does not contain a valid deal ticket."
                )

            existing_trade = await self.trade_service.get_trade_by_position(
                position.id,
            )

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

            duration_seconds = max(
                int((closed_at - position.opened_at).total_seconds()),
                0,
            )

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
                profit_percent=self._calculate_profit_percent(
                    position,
                    net_profit,
                ),
                initial_risk=position.initial_risk,
                reward_risk_ratio=position.risk_reward_ratio,
                mfe=None,
                mae=None,
                result=self._calculate_trade_result(net_profit),
                opened_at=position.opened_at,
                closed_at=closed_at,
                duration_seconds=duration_seconds,
                comment=position.comment,
            )

            closed_position = await self._mark_position_closed(
                position=position,
                closed_at=closed_at,
                exit_price=exit_price,
                commit=False,
            )

            await self.trade_service.create_trade(
                trade_data,
                commit=False,
            )

            await db.commit()

            return closed_position

        except Exception:
            await db.rollback()
            raise

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
                current_volume=Decimal("0"),
                current_price=exit_price,
                status=PositionStatus.CLOSED,
                closed_at=closed_at,
                last_updated_price_at=closed_at,
            ),
            commit=commit,
        )

    # ==========================================================
    # DEAL HELPERS
    # ==========================================================

    @staticmethod
    def _find_opening_deal(
        deals: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
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
            key=lambda deal: PositionSyncService._broker_time_sort_key(
                deal.get("time")
            ),
        )

    @staticmethod
    def _find_closing_deal(
        deals: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        """
        Current implementation handles the normal full-close case by
        selecting the latest closing deal. Partial-close deal aggregation
        requires separate accounting logic.
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
            key=lambda deal: PositionSyncService._broker_time_sort_key(
                deal.get("time")
            ),
        )

    # ==========================================================
    # MAPPERS AND VALUE HELPERS
    # ==========================================================

    @staticmethod
    def _map_direction(broker_type: Any) -> PositionDirection:
        """
        MT5 position type:
            0 = BUY
            1 = SELL
        """

        position_type = PositionSyncService._extract_int(broker_type)

        if position_type == 0:
            return PositionDirection.BUY

        if position_type == 1:
            return PositionDirection.SELL

        raise ValueError(f"Unsupported broker position type: {broker_type!r}")

    @staticmethod
    def _extract_ticket(
        broker_position: dict[str, Any],
    ) -> int | None:
        return PositionSyncService._extract_int(
            broker_position.get("ticket"),
        )

    @staticmethod
    def _extract_broker_position_id(
        broker_position: dict[str, Any],
    ) -> str | None:
        identifier = broker_position.get("identifier")

        if identifier is None:
            return None

        value = PositionSyncService._extract_int(identifier)

        return str(value) if value is not None else None

    @staticmethod
    def _extract_int(value: Any) -> int | None:
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
    def _decimal_or_none(value: Any) -> Decimal | None:
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
        except (TypeError, ValueError, OverflowError):
            return fallback

    @staticmethod
    def _broker_time_sort_key(value: Any) -> float:
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

    @staticmethod
    def _calculate_profit_percent(
        position,
        net_profit: Decimal,
    ) -> Decimal | None:
        if position.entry_price <= 0:
            return None

        return net_profit / position.entry_price * Decimal("100")

    @staticmethod
    def _calculate_trade_result(net_profit: Decimal) -> TradeResult:
        if net_profit > 0:
            return TradeResult.WIN

        if net_profit < 0:
            return TradeResult.LOSS

        return TradeResult.BREAKEVEN

    @staticmethod
    def _to_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            result = model_dump()
            return result if isinstance(result, dict) else {}

        if hasattr(value, "__dict__"):
            return vars(value)

        return {}
