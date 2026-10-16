
"""Reconcile AQE orders against authoritative broker order and deal history."""

from __future__ import annotations

import asyncio
import logging

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.broker_manager import BrokerManager
from app.core.constants import OrderStatus
from app.database.session import SessionLocal
from app.repositories.order_repository import OrderRepository

logger = logging.getLogger(__name__)


class OrderReconciliationError(Exception):
    """Base exception for order reconciliation failures."""


class OrderReconciliationService:
    """
    Reconcile AQE orders against broker order and deal history.

    Monitored AQE states:

        SUBMITTED
            Submission outcome is unresolved.

        PENDING
            Broker accepted an order awaiting execution.

        PARTIALLY_FILLED
            Some volume executed; the remaining order may still change.

    Reconciliation rules:

        - Never submit or retry a broker order.
        - Use broker deal history as the source of execution quantities.
        - Use broker order history to establish order lifecycle state.
        - Include currently active broker orders when matching pending orders.
        - Recompute cumulative execution from deduplicated deal snapshots.
        - Keep ambiguous outcomes unresolved.
        - Never infer a fill solely from an order state.
        - Use a fresh database session for each reconciliation cycle.
        - Use database savepoints to isolate individual order failures.
        - Never heuristically match a different broker ticket when an AQE
          order already has a known broker order ID.

    Important limitation:

        Snapshot-based cumulative reconciliation requires complete broker
        deal history for the requested time window. Missing or regressing
        deal history must not silently reduce a previously confirmed fill.
    """

    DEFAULT_INTERVAL_SECONDS = 10.0
    HISTORY_BUFFER = timedelta(minutes=10)
    VOLUME_TOLERANCE = Decimal("0.00000001")

    def __init__(
        self,
        *,
        broker: BrokerManager,
        session_factory=SessionLocal,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable.")

        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero.")

        self._broker = broker
        self._session_factory = session_factory
        self._interval_seconds = float(interval_seconds)

        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._account_id: UUID | None = None

        self._reconcile_lock = asyncio.Lock()

    # ==============================================================
    # STATE
    # ==============================================================

    @property
    def running(self) -> bool:
        """Return whether the background reconciliation loop is running."""
        return self._running

    @property
    def account_id(self) -> UUID | None:
        """Return the account currently being reconciled."""
        return self._account_id

    # ==============================================================
    # LIFECYCLE
    # ==============================================================

    async def start(
        self,
        account_id: UUID,
    ) -> None:
        """
        Reconcile immediately and start the periodic reconciliation loop.

        The broker must already be connected to the correct account.
        """

        if not isinstance(account_id, UUID):
            raise TypeError("account_id must be a UUID.")

        if self._running:
            if self._account_id == account_id:
                return

            raise OrderReconciliationError(
                "Order reconciliation is already running for another "
                f"account: {self._account_id}"
            )

        self._account_id = account_id

        logger.info(
            "Starting order reconciliation. account_id=%s",
            account_id,
        )

        try:
            await self.reconcile_account(account_id)

        except Exception:
            self._account_id = None

            logger.exception(
                "Initial order reconciliation failed. account_id=%s",
                account_id,
            )
            raise

        self._running = True

        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"aqe-order-reconciliation:{account_id}",
        )

        logger.info(
            "Order reconciliation loop started. "
            "account_id=%s interval_seconds=%s",
            account_id,
            self._interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the background reconciliation loop."""

        self._running = False

        task = self._task
        self._task = None

        if task is not None and task is not asyncio.current_task():
            task.cancel()

            try:
                await task

            except asyncio.CancelledError:
                pass

            except Exception:
                logger.exception(
                    "Order reconciliation loop exited with an error."
                )

        logger.info(
            "Order reconciliation stopped. account_id=%s",
            self._account_id,
        )

        self._account_id = None

    # ==============================================================
    # BACKGROUND LOOP
    # ==============================================================

    async def _run_loop(self) -> None:
        """Periodically reconcile active orders."""

        while self._running:
            try:
                account_id = self._account_id

                if account_id is not None:
                    await self.reconcile_account(account_id)

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Order reconciliation cycle failed. account_id=%s",
                    self._account_id,
                )

            try:
                await asyncio.sleep(self._interval_seconds)

            except asyncio.CancelledError:
                raise

    # ==============================================================
    # ACCOUNT RECONCILIATION
    # ==============================================================

    async def reconcile_account(
        self,
        account_id: UUID,
    ) -> dict[str, int]:
        """
        Reconcile SUBMITTED, PENDING and PARTIALLY_FILLED orders for
        one account.

        The service does not keep a database session between cycles.
        """

        async with self._reconcile_lock:
            async with self._session_factory() as db:
                repository = OrderRepository(db)

                orders = await repository.get_orders_requiring_reconciliation(
                    account_id,
                )

                stats = {
                    "submitted": len(orders),
                    "monitored": len(orders),
                    "reconciled": 0,
                    "unchanged": 0,
                    "ambiguous": 0,
                    "errors": 0,
                }

                if not orders:
                    return stats

                start = (
                    min(self._order_created_at(order) for order in orders)
                    - self.HISTORY_BUFFER
                )

                end = datetime.now(timezone.utc) + self.HISTORY_BUFFER

                logger.debug(
                    "Retrieving reconciliation evidence. "
                    "account_id=%s orders=%d start=%s end=%s",
                    account_id,
                    len(orders),
                    start,
                    end,
                )

                # These requests are read-only. Reconciliation never
                # submits another trading request.
                deals_response = await self._get_deals(
                    start=start,
                    end=end,
                )

                history_response = await self._get_orders(
                    start=start,
                    end=end,
                )

                active_response = await self._get_active_orders()

                normalized_deals = self._deduplicate_deals(
                    [
                        deal
                        for deal in self._normalize_history(deals_response)
                        if self._deal_belongs_to_window(
                            deal,
                            start,
                            end,
                        )
                    ]
                )

                normalized_history_orders = [
                    broker_order
                    for broker_order in self._normalize_history(
                        history_response,
                    )
                    if self._broker_order_belongs_to_window(
                        broker_order,
                        start,
                        end,
                    )
                ]

                active_orders = self._normalize_active_orders(
                    active_response,
                )

                normalized_broker_orders = self._merge_broker_orders(
                    normalized_history_orders,
                    active_orders,
                )

                for order in orders:
                    try:
                        # Isolate ORM updates for each individual order.
                        async with db.begin_nested():
                            result = await self._reconcile_one(
                                db=db,
                                order=order,
                                deals=normalized_deals,
                                broker_orders=normalized_broker_orders,
                            )

                        if result == "reconciled":
                            stats["reconciled"] += 1

                        elif result == "ambiguous":
                            stats["ambiguous"] += 1

                        else:
                            stats["unchanged"] += 1

                    except Exception:
                        stats["errors"] += 1

                        logger.exception(
                            "Failed to reconcile AQE order. "
                            "order_id=%s account_id=%s",
                            order.id,
                            account_id,
                        )

                await db.commit()

                logger.info(
                    "Order reconciliation completed. "
                    "account_id=%s monitored=%d reconciled=%d "
                    "unchanged=%d ambiguous=%d errors=%d",
                    account_id,
                    stats["monitored"],
                    stats["reconciled"],
                    stats["unchanged"],
                    stats["ambiguous"],
                    stats["errors"],
                )

                return stats

    # ==============================================================
    # SINGLE ORDER
    # ==============================================================

    async def _reconcile_one(
        self,
        *,
        db: AsyncSession,
        order,
        deals: list[dict[str, Any]],
        broker_orders: list[dict[str, Any]],
    ) -> str:
        """
        Reconcile one active AQE order.

        Execution deals establish executed quantity and price.
        Order records establish pending and terminal order states.
        """

        matched_broker_orders = self._match_broker_orders(
            order,
            broker_orders,
        )

        if matched_broker_orders is None:
            logger.warning(
                "Ambiguous broker-order match. order_id=%s",
                order.id,
            )
            return "ambiguous"

        matched_broker_order = (
            matched_broker_orders[0] if matched_broker_orders else None
        )

        broker_order_id_hint = self._optional_int(
            getattr(order, "broker_order_id", None)
        )

        if matched_broker_order is not None:
            candidate_id = self._broker_order_id(
                matched_broker_order,
            )

            if candidate_id is not None:
                broker_order_id_hint = candidate_id

        matched_deals = self._match_deals(
            order,
            deals,
            broker_order_id=broker_order_id_hint,
        )

        if matched_deals is None:
            logger.warning(
                "Ambiguous broker-deal match. order_id=%s",
                order.id,
            )
            return "ambiguous"

        if matched_deals:
            deal_result = await self._apply_deal_match(
                db=db,
                order=order,
                deals=matched_deals,
                broker_order_id_hint=broker_order_id_hint,
            )

            if deal_result == "ambiguous":
                return "ambiguous"

            # Deal-level proof of a complete fill is authoritative.
            if order.status == OrderStatus.FILLED:
                return deal_result

            # Preserve a partial execution while recording the final
            # state of the remaining broker order.
            if matched_broker_order is not None:
                broker_state = self._normalize_state(
                    matched_broker_order.get("state"),
                    matched_broker_order.get("status"),
                )

                if broker_state in {
                    "CANCELLED",
                    "EXPIRED",
                    "REJECTED",
                }:
                    order_result = await self._apply_broker_order_match(
                        db=db,
                        order=order,
                        broker_order=matched_broker_order,
                    )

                    if order_result == "ambiguous":
                        return "ambiguous"

                    if (
                        deal_result == "reconciled"
                        or order_result == "reconciled"
                    ):
                        return "reconciled"

                    return "unchanged"

            return deal_result

        # No deal has been matched. Order history may still establish
        # that the broker accepted, rejected, cancelled or expired it.
        if matched_broker_order is not None:
            return await self._apply_broker_order_match(
                db=db,
                order=order,
                broker_order=matched_broker_order,
            )

        # No attributable broker evidence is currently available.
        # Never infer rejection from a missing history match.
        return "unchanged"

    # ==============================================================
    # DEAL MATCHING
    # ==============================================================

    def _match_deals(
        self,
        order,
        deals: list[dict[str, Any]],
        *,
        broker_order_id: int | None = None,
    ) -> list[dict[str, Any]] | None:
        """
        Match broker deals to an AQE order.

        If an AQE order already has a broker order ID, only deals tied
        to that ticket are considered. When the ticket has no deals
        in the current snapshot, return an empty list and wait for
        authoritative history rather than using heuristic matching.

        When there is no known ticket, compatible symbol, direction,
        time and volume provide fallback evidence. Ambiguous attribution
        is refused.

        Returns:
            list: matched deal records.
            []: no matching evidence.
            None: attribution is ambiguous.
        """

        known_order_id = (
            broker_order_id
            or self._optional_int(
                getattr(order, "broker_order_id", None)
            )
        )

        if known_order_id is not None:
            direct_matches = [
                deal
                for deal in deals
                if self._deal_order_id(deal) == known_order_id
            ]

            if direct_matches:
                return sorted(
                    direct_matches,
                    key=self._deal_time,
                )

            # A known broker ticket is authoritative. Do not attribute
            # another order's deals to this AQE order by heuristics.
            return []

        candidates = [
            deal
            for deal in deals
            if self._deal_matches_order(order, deal)
        ]

        if not candidates:
            return []

        if len(candidates) == 1:
            return candidates

        # Partial fills for the same broker order may legitimately
        # appear as multiple deals. Preserve all of them.
        grouped: dict[int | None, list[dict[str, Any]]] = {}

        for deal in candidates:
            candidate_order_id = self._deal_order_id(deal)

            grouped.setdefault(
                candidate_order_id,
                [],
            ).append(deal)

        if len(grouped) == 1:
            group_order_id, grouped_deals = next(iter(grouped.items()))

            # Several anonymous deal records cannot be assumed to
            # belong to the same order merely because they share
            # symbol, direction, time and volume characteristics.
            if group_order_id is None:
                logger.warning(
                    "Multiple candidate deals lack broker order IDs. "
                    "order_id=%s candidate_count=%d",
                    order.id,
                    len(grouped_deals),
                )
                return None

            return sorted(
                grouped_deals,
                key=self._deal_time,
            )

        # A distinctive comment may help disambiguate different
        # candidate broker orders, but must not split multiple fills
        # belonging to the same broker order.
        expected_comment = self._matching_comment(
            getattr(order, "comment", None),
        )

        if expected_comment:
            exact_comment_matches = [
                deal
                for deal in candidates
                if self._comment_matches(
                    expected_comment,
                    deal.get("comment"),
                )
            ]

            if exact_comment_matches:
                candidates = exact_comment_matches

        if len(candidates) == 1:
            return candidates

        grouped = {}

        for deal in candidates:
            candidate_order_id = self._deal_order_id(deal)

            grouped.setdefault(
                candidate_order_id,
                [],
            ).append(deal)

        if len(grouped) == 1:
            group_order_id, grouped_deals = next(iter(grouped.items()))

            if group_order_id is not None:
                return sorted(
                    grouped_deals,
                    key=self._deal_time,
                )

        logger.warning(
            "Ambiguous deal match for AQE order. "
            "order_id=%s candidate_groups=%d",
            order.id,
            len(grouped),
        )

        return None

    async def _apply_deal_match(
        self,
        *,
        db: AsyncSession,
        order,
        deals: list[dict[str, Any]],
        broker_order_id_hint: int | None = None,
    ) -> str:
        """
        Recompute cumulative execution from the matched deal snapshot.

        Deal IDs are deduplicated. Existing confirmed volume cannot
        silently regress if the broker returns an incomplete snapshot.
        """

        unique_deals = self._deduplicate_deals(deals)

        if not unique_deals:
            return "unchanged"

        requested_volume = self._decimal_or_zero(
            getattr(order, "volume", None),
        )

        if requested_volume <= 0:
            logger.error(
                "Invalid requested volume. order_id=%s volume=%s",
                order.id,
                requested_volume,
            )
            return "ambiguous"

        executed_volume = Decimal("0")

        for deal in unique_deals:
            deal_volume = self._decimal_or_zero(
                deal.get("volume"),
            )

            deal_price = self._decimal_or_zero(
                deal.get("price"),
            )

            if deal_volume <= 0 or deal_price <= 0:
                logger.warning(
                    "Deal has invalid execution values. "
                    "order_id=%s deal_id=%s volume=%s price=%s",
                    order.id,
                    self._deal_id(deal),
                    deal_volume,
                    deal_price,
                )
                return "ambiguous"

            executed_volume += deal_volume

        if executed_volume > requested_volume:
            logger.error(
                "Cumulative broker volume exceeds requested volume. "
                "order_id=%s requested=%s executed=%s",
                order.id,
                requested_volume,
                executed_volume,
            )
            return "ambiguous"

        previous_volume = self._decimal_or_zero(
            getattr(order, "executed_volume", None),
        )

        if previous_volume > executed_volume + self.VOLUME_TOLERANCE:
            logger.error(
                "Broker-history volume regressed. "
                "order_id=%s previous=%s current=%s",
                order.id,
                previous_volume,
                executed_volume,
            )
            return "ambiguous"

        executed_price = self._weighted_average_price(unique_deals)

        if executed_price is None or executed_price <= 0:
            return "ambiguous"

        broker_order_ids = {
            broker_order_id
            for broker_order_id in (
                self._deal_order_id(deal)
                for deal in unique_deals
            )
            if broker_order_id is not None
        }

        if len(broker_order_ids) > 1:
            logger.warning(
                "Matched deals reference multiple broker orders. "
                "order_id=%s broker_order_ids=%s",
                order.id,
                sorted(broker_order_ids),
            )
            return "ambiguous"

        broker_order_id = (
            next(iter(broker_order_ids))
            if broker_order_ids
            else broker_order_id_hint
        )

        broker_position_ids = {
            position_id
            for position_id in (
                self._optional_int(
                    deal.get(
                        "position_id",
                        deal.get("position"),
                    )
                )
                for deal in unique_deals
            )
            if position_id is not None
        }

        representative_deal_id = self._deal_id(
            min(
                unique_deals,
                key=self._deal_time,
            )
        )

        if executed_volume + self.VOLUME_TOLERANCE >= requested_volume:
            new_status = OrderStatus.FILLED
        else:
            new_status = OrderStatus.PARTIALLY_FILLED

        updates: dict[str, Any] = {
            "status": new_status,
            "executed_volume": executed_volume,
            "executed_price": executed_price,
        }

        if broker_order_id is not None:
            updates["broker_order_id"] = broker_order_id

        if representative_deal_id is not None:
            updates["broker_deal_id"] = representative_deal_id

        if len(broker_position_ids) == 1:
            updates["broker_position_id"] = next(iter(broker_position_ids))

        self._apply_order_updates(
            order,
            **updates,
        )

        await db.flush()

        logger.info(
            "Reconciled broker execution from deal history. "
            "order_id=%s status=%s broker_order_id=%s "
            "representative_deal_id=%s executed_volume=%s "
            "requested_volume=%s executed_price=%s",
            order.id,
            new_status.value,
            broker_order_id,
            representative_deal_id,
            executed_volume,
            requested_volume,
            executed_price,
        )

        return "reconciled"

    # ==============================================================
    # BROKER ORDER MATCHING
    # ==============================================================

    def _match_broker_orders(
        self,
        order,
        broker_orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """
        Find the broker order attributable to an AQE order.

        If AQE already knows the broker ticket, only that ticket may
        be matched. A missing ticket in the latest snapshot must not
        result in a heuristic match to another broker order.

        For orders without a known ticket, fallback matching must
        produce a unique ticket or be treated as ambiguous.
        """

        known_order_id = self._optional_int(
            getattr(order, "broker_order_id", None),
        )

        if known_order_id is not None:
            direct_matches = [
                broker_order
                for broker_order in broker_orders
                if self._broker_order_id(broker_order) == known_order_id
            ]

            if direct_matches:
                latest = max(
                    direct_matches,
                    key=lambda item: (
                        self._broker_order_time(item)
                        or datetime.min.replace(tzinfo=timezone.utc)
                    ),
                )
                return [latest]

            # Keep the order unresolved until its known broker ticket
            # appears in history again. Do not substitute another ticket.
            return []

        candidates = [
            broker_order
            for broker_order in broker_orders
            if self._broker_order_matches_order(
                order,
                broker_order,
            )
        ]

        if not candidates:
            return []

        if len(candidates) == 1:
            return candidates

        grouped: dict[int | None, list[dict[str, Any]]] = {}

        for candidate in candidates:
            ticket = self._broker_order_id(candidate)
            grouped.setdefault(ticket, []).append(candidate)

        if len(grouped) == 1:
            ticket, same_order_records = next(iter(grouped.items()))

            if ticket is None:
                return None

            latest = max(
                same_order_records,
                key=lambda item: (
                    self._broker_order_time(item)
                    or datetime.min.replace(tzinfo=timezone.utc)
                ),
            )

            return [latest]

        expected_comment = self._matching_comment(
            getattr(order, "comment", None),
        )

        if expected_comment:
            exact_matches = [
                candidate
                for candidate in candidates
                if self._comment_matches(
                    expected_comment,
                    candidate.get("comment"),
                )
            ]

            if exact_matches:
                candidates = exact_matches

        if len(candidates) == 1:
            return candidates

        grouped = {}

        for candidate in candidates:
            ticket = self._broker_order_id(candidate)
            grouped.setdefault(ticket, []).append(candidate)

        if len(grouped) == 1:
            ticket, same_order_records = next(iter(grouped.items()))

            if ticket is not None:
                latest = max(
                    same_order_records,
                    key=lambda item: (
                        self._broker_order_time(item)
                        or datetime.min.replace(tzinfo=timezone.utc)
                    ),
                )
                return [latest]

        logger.warning(
            "Ambiguous broker-order match. "
            "order_id=%s candidate_groups=%d",
            order.id,
            len(grouped),
        )

        return None

    async def _apply_broker_order_match(
        self,
        *,
        db: AsyncSession,
        order,
        broker_order: dict[str, Any],
    ) -> str:
        """
        Apply authoritative broker order-state evidence.

        FILLED and PARTIALLY_FILLED states cannot establish fill
        quantities on their own. Deal history must confirm execution.
        """

        broker_order_id = self._broker_order_id(broker_order)

        if broker_order_id is None:
            return "unchanged"

        previous_order_id = self._optional_int(
            getattr(order, "broker_order_id", None),
        )

        previous_status = order.status

        order.broker_order_id = broker_order_id

        state = self._normalize_state(
            broker_order.get("state"),
            broker_order.get("status"),
        )

        if state in {
            "FILLED",
            "PARTIALLY_FILLED",
            "PARTIAL",
        }:
            # Deal history is required for accurate volume and price.
            await db.flush()

            if previous_order_id != broker_order_id:
                return "reconciled"

            return "unchanged"

        if state == "REJECTED":
            existing_volume = self._decimal_or_zero(
                getattr(order, "executed_volume", None),
            )

            if existing_volume > 0:
                logger.error(
                    "Broker reports REJECTED despite previously "
                    "confirmed execution. order_id=%s broker_order_id=%s "
                    "executed_volume=%s",
                    order.id,
                    broker_order_id,
                    existing_volume,
                )
                await db.flush()
                return "ambiguous"

            order.status = OrderStatus.REJECTED

        elif state == "CANCELLED":
            # Retain executed_volume when an order's remaining volume
            # has been cancelled after a partial fill.
            order.status = OrderStatus.CANCELLED

        elif state == "EXPIRED":
            order.status = OrderStatus.EXPIRED

        elif state in {
            "PENDING",
            "PLACED",
            "ACCEPTED",
            "OPEN",
        }:
            existing_volume = self._decimal_or_zero(
                getattr(order, "executed_volume", None),
            )

            if existing_volume > 0:
                order.status = OrderStatus.PARTIALLY_FILLED

            elif order.status == OrderStatus.SUBMITTED:
                order.status = OrderStatus.PENDING

        else:
            await db.flush()

            logger.warning(
                "Broker order ticket recovered, but the state is "
                "unrecognized. order_id=%s broker_order_id=%s state=%r",
                order.id,
                broker_order_id,
                state,
            )

            if previous_order_id != broker_order_id:
                return "reconciled"

            return "unchanged"

        await db.flush()

        if (
            previous_order_id != broker_order_id
            or previous_status != order.status
        ):
            logger.info(
                "Reconciled broker order state. "
                "order_id=%s broker_order_id=%s state=%s aqe_status=%s",
                order.id,
                broker_order_id,
                state,
                order.status.value,
            )
            return "reconciled"

        return "unchanged"

    # ==============================================================
    # BROKER DATA
    # ==============================================================

    async def _get_deals(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> Any:
        """Retrieve broker deal history."""

        return await self._broker.get_deal_history(
            start,
            end,
        )

    async def _get_orders(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> Any:
        """Retrieve historical broker orders."""

        return await self._broker.get_order_history(
            start,
            end,
        )

    async def _get_active_orders(self) -> Any:
        """Retrieve currently active/pending broker orders."""

        return await self._broker.get_orders()

    # ==============================================================
    # HISTORY NORMALIZATION
    # ==============================================================

    @staticmethod
    def _normalize_history(
        value: Any,
    ) -> list[dict[str, Any]]:
        """
        Normalize broker history response shapes.

        An explicit empty collection is valid. None or a malformed
        response is a retrieval/contract error, not empty history.
        """

        if value is None:
            raise OrderReconciliationError(
                "Broker history returned None instead of a collection."
            )

        if isinstance(value, (list, tuple)):
            if any(not isinstance(item, dict) for item in value):
                raise OrderReconciliationError(
                    "Broker history contains a non-object record."
                )

            return list(value)

        if isinstance(value, dict):
            for key in (
                "data",
                "results",
                "orders",
                "deals",
                "items",
            ):
                if key not in value:
                    continue

                nested = value[key]

                if not isinstance(nested, (list, tuple)):
                    raise OrderReconciliationError(
                        f"Broker history field {key!r} is not a collection."
                    )

                if any(not isinstance(item, dict) for item in nested):
                    raise OrderReconciliationError(
                        f"Broker history field {key!r} contains "
                        "a non-object record."
                    )

                return list(nested)

            if any(
                key in value
                for key in (
                    "ticket",
                    "deal_id",
                    "order_id",
                )
            ):
                return [value]

        raise OrderReconciliationError(
            "Broker history returned an unsupported response structure."
        )

    @classmethod
    def _deduplicate_deals(
        cls,
        deals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Deduplicate deals by their stable broker ticket.

        If two records with the same ticket disagree about execution
        identity or values, fail conservatively instead of picking one.
        """

        unique: dict[int, dict[str, Any]] = {}

        identity_fields = (
            "order",
            "order_id",
            "symbol",
            "type",
            "volume",
            "price",
        )

        for deal in deals:
            deal_id = cls._deal_id(deal)

            if deal_id is None:
                raise OrderReconciliationError(
                    "Broker deal history contains a record without "
                    "a valid deal ticket."
                )

            existing = unique.get(deal_id)

            if existing is None:
                unique[deal_id] = deal
                continue

            for field in identity_fields:
                old_value = existing.get(field)
                new_value = deal.get(field)

                if (
                    old_value is not None
                    and new_value is not None
                    and str(old_value) != str(new_value)
                ):
                    raise OrderReconciliationError(
                        "Conflicting history records for broker deal "
                        f"{deal_id}: field {field!r} disagrees."
                    )

            # Repeated identical ticket: count it only once.

        return sorted(
            unique.values(),
            key=cls._deal_time,
        )

    @classmethod
    def _normalize_active_orders(
        cls,
        value: Any,
    ) -> list[dict[str, Any]]:
        """
        Normalize the active-order endpoint.

        Because this endpoint represents currently active broker
        orders, records are assigned semantic state PENDING. MT5's
        numeric order-state enum is not interpreted in this service.
        """

        active_records = cls._normalize_history(value)
        normalized: list[dict[str, Any]] = []

        for record in active_records:
            ticket = cls._broker_order_id(record)

            if ticket is None:
                logger.warning(
                    "Ignoring active broker order without a ticket: %r",
                    record,
                )
                continue

            item = dict(record)
            item["ticket"] = ticket
            item["state"] = "PENDING"
            item["status"] = "PENDING"

            normalized.append(item)

        return normalized

    @classmethod
    def _merge_broker_orders(
        cls,
        historical_orders: list[dict[str, Any]],
        active_orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge historical and current order records by broker ticket.

        A current active-order snapshot overrides an older historical
        representation of the same order.
        """

        merged: dict[int, dict[str, Any]] = {}

        for record in historical_orders:
            ticket = cls._broker_order_id(record)

            if ticket is None:
                logger.warning(
                    "Ignoring historical broker order without a ticket: %r",
                    record,
                )
                continue

            current = merged.get(ticket)

            if current is None:
                merged[ticket] = dict(record)
                continue

            current_time = cls._broker_order_time(current)
            candidate_time = cls._broker_order_time(record)

            if candidate_time is not None and (
                current_time is None or candidate_time >= current_time
            ):
                merged[ticket] = dict(record)

        for record in active_orders:
            ticket = cls._broker_order_id(record)

            if ticket is not None:
                merged[ticket] = dict(record)

        return list(merged.values())

    # ==============================================================
    # TIME WINDOWS
    # ==============================================================

    @classmethod
    def _deal_belongs_to_window(
        cls,
        deal: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> bool:
        timestamp = cls._parse_datetime(
            deal.get("time"),
        )

        if timestamp is None:
            return False

        return start <= timestamp <= end

    @classmethod
    def _broker_order_belongs_to_window(
        cls,
        broker_order: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> bool:
        timestamp = cls._broker_order_time(
            broker_order,
        )

        # Retain records with a missing timestamp for direct-ticket
        # matching. Heuristic matching independently requires a time.
        if timestamp is None:
            return True

        return start <= timestamp <= end

    # ==============================================================
    # DATETIME
    # ==============================================================

    @classmethod
    def _order_created_at(
        cls,
        order,
    ) -> datetime:
        parsed = cls._parse_datetime(
            getattr(order, "created_at", None),
        )

        if parsed is None:
            raise OrderReconciliationError(
                "AQE order "
                f"{getattr(order, 'id', '<unknown>')} "
                "does not contain a valid created_at timestamp."
            )

        return parsed

    @classmethod
    def _deal_time(
        cls,
        deal: dict[str, Any],
    ) -> datetime:
        parsed = cls._parse_datetime(
            deal.get("time"),
        )

        if parsed is None:
            return datetime.min.replace(tzinfo=timezone.utc)

        return parsed

    @classmethod
    def _broker_order_time(
        cls,
        broker_order: dict[str, Any],
    ) -> datetime | None:
        return cls._parse_datetime(
            broker_order.get(
                "time_setup",
                broker_order.get("time"),
            )
        )

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, datetime):
            result = value

        elif isinstance(value, (int, float)):
            try:
                result = datetime.fromtimestamp(
                    float(value),
                    tz=timezone.utc,
                )
            except (OverflowError, OSError, ValueError):
                return None

        elif isinstance(value, str):
            raw = value.strip()

            if not raw:
                return None

            try:
                result = datetime.fromisoformat(
                    raw.replace("Z", "+00:00"),
                )
            except ValueError:
                return None

        else:
            return None

        if result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)

        return result.astimezone(timezone.utc)

    # ==============================================================
    # SYMBOL MATCHING
    # ==============================================================

    def _symbol_matches_order(
        self,
        order,
        broker_symbol: Any,
    ) -> bool:
        """
        Prefer the persisted broker-native symbol.

        Do not strip broker suffixes such as '.s' or 'm': different
        broker-native identifiers can represent different instruments.
        """

        candidate = self._normalize_symbol(broker_symbol)

        if not candidate:
            return False

        broker_symbol_candidates: set[str] = set()

        for attribute in (
            "broker_symbol",
            "broker_instrument",
        ):
            value = getattr(order, attribute, None)
            normalized = self._normalize_symbol(value)

            if normalized:
                broker_symbol_candidates.add(normalized)

        account_symbol = getattr(order, "account_symbol", None)

        if account_symbol is not None:
            normalized = self._normalize_symbol(
                getattr(
                    account_symbol,
                    "broker_symbol",
                    None,
                )
            )

            if normalized:
                broker_symbol_candidates.add(normalized)

        if broker_symbol_candidates:
            return candidate in broker_symbol_candidates

        return self._order_symbol(order) == candidate

    @classmethod
    def _order_symbol(
        cls,
        order,
    ) -> str:
        symbol = getattr(order, "symbol", None)

        if symbol is None:
            return ""

        name = getattr(symbol, "name", None)

        if name is not None:
            return cls._normalize_symbol(name)

        return cls._normalize_symbol(symbol)

    @staticmethod
    def _normalize_symbol(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        return str(value).strip().upper()

    # ==============================================================
    # DIRECTION MATCHING
    # ==============================================================

    def _side_matches_order(
        self,
        order,
        broker_record: dict[str, Any],
    ) -> bool:
        """
        Compare AQE BUY/SELL direction with an explicit broker direction.

        Unknown direction values are rejected rather than treated
        as matching evidence.
        """

        expected = self._normalize_side(
            getattr(order, "side", None),
        )

        if not expected:
            return False

        for key in (
            "side",
            "direction",
            "deal_type",
        ):
            if key not in broker_record:
                continue

            value = broker_record.get(key)

            if value is None:
                continue

            observed = self._normalize_side(value)

            return bool(observed) and observed == expected

        if "type" not in broker_record:
            return False

        raw_type = broker_record.get("type")
        observed = self._normalize_side(raw_type)

        if observed:
            return observed == expected

        raw = str(raw_type).strip().upper()

        # Deal records may contain an entry field. In that case,
        # type=0/1 denotes DEAL_TYPE_BUY/SELL. Do not interpret other
        # deal-type codes as pending order types.
        if "entry" in broker_record:
            return False

        buy_order_types = {
            "0",
            "2",
            "4",
            "ORDER_TYPE_BUY_LIMIT",
            "ORDER_TYPE_BUY_STOP",
        }

        sell_order_types = {
            "1",
            "3",
            "5",
            "ORDER_TYPE_SELL_LIMIT",
            "ORDER_TYPE_SELL_STOP",
        }

        if raw in buy_order_types:
            return expected == "BUY"

        if raw in sell_order_types:
            return expected == "SELL"

        return False

    @staticmethod
    def _normalize_side(
        value: Any,
    ) -> str:
        if value is None or isinstance(value, bool):
            return ""

        raw = str(getattr(value, "value", value)).strip().upper()

        if raw in {
            "BUY",
            "LONG",
            "0",
            "ORDER_TYPE_BUY",
            "DEAL_TYPE_BUY",
            "BUY_LIMIT",
            "BUY_STOP",
            "ORDER_TYPE_BUY_LIMIT",
            "ORDER_TYPE_BUY_STOP",
        }:
            return "BUY"

        if raw in {
            "SELL",
            "SHORT",
            "1",
            "ORDER_TYPE_SELL",
            "DEAL_TYPE_SELL",
            "SELL_LIMIT",
            "SELL_STOP",
            "ORDER_TYPE_SELL_LIMIT",
            "ORDER_TYPE_SELL_STOP",
        }:
            return "SELL"

        return ""

    # ==============================================================
    # DEAL MATCHING HELPERS
    # ==============================================================

    def _deal_matches_order(
        self,
        order,
        deal: dict[str, Any],
    ) -> bool:
        """
        Match a deal to an order using conservative fallback evidence.

        Fallback matching is used only when the AQE order has no known
        broker order ticket. It is not a substitute for a broker-provided
        correlation token.
        """

        if not self._symbol_matches_order(
            order,
            deal.get("symbol"),
        ):
            return False

        if not self._side_matches_order(
            order,
            deal,
        ):
            return False

        order_time = self._order_created_at(order)
        deal_time = self._deal_time(deal)

        if deal_time == datetime.min.replace(tzinfo=timezone.utc):
            return False

        if abs(deal_time - order_time) > self.HISTORY_BUFFER:
            return False

        requested_volume = self._decimal_or_zero(
            getattr(order, "volume", None),
        )

        deal_volume = self._decimal_or_zero(
            deal.get("volume"),
        )

        if requested_volume <= 0 or deal_volume <= 0:
            return False

        if deal_volume > requested_volume:
            return False

        return True

    # ==============================================================
    # BROKER ORDER MATCHING HELPERS
    # ==============================================================

    def _broker_order_matches_order(
        self,
        order,
        broker_order: dict[str, Any],
    ) -> bool:
        """
        Match a broker order by symbol, side, timestamp and initial volume.
        """

        if not self._symbol_matches_order(
            order,
            broker_order.get("symbol"),
        ):
            return False

        if not self._side_matches_order(
            order,
            broker_order,
        ):
            return False

        order_time = self._order_created_at(order)
        broker_time = self._broker_order_time(broker_order)

        if broker_time is None:
            return False

        if abs(broker_time - order_time) > self.HISTORY_BUFFER:
            return False

        requested_volume = self._decimal_or_zero(
            getattr(order, "volume", None),
        )

        broker_volume = self._decimal_or_zero(
            broker_order.get("volume_initial"),
            default=broker_order.get("volume"),
        )

        if requested_volume <= 0:
            return False

        if broker_volume > 0 and broker_volume != requested_volume:
            return False

        return True

    # ==============================================================
    # BROKER IDENTIFIER HELPERS
    # ==============================================================

    @classmethod
    def _broker_order_id(
        cls,
        broker_order: dict[str, Any],
    ) -> int | None:
        """Extract a broker order ID without truncating malformed values."""
        for key in ("ticket", "order_id", "order"):
            order_id = cls._optional_int(broker_order.get(key))

            if order_id is not None and order_id > 0:
                return order_id

        return None

    @staticmethod
    def _optional_int(
        value: Any,
    ) -> int | None:
        if value is None or value == "" or isinstance(value, bool):
            return None

        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None

        if not parsed.is_finite():
            return None

        if parsed != parsed.to_integral_value():
            return None

        return int(parsed)

    @classmethod
    def _deal_order_id(
        cls,
        deal: dict[str, Any],
    ) -> int | None:
        """Extract the originating broker order ticket from a deal."""
        for key in ("order", "order_id"):
            order_id = cls._optional_int(deal.get(key))

            if order_id is not None and order_id > 0:
                return order_id

        return None

    @classmethod
    def _deal_id(
        cls,
        deal: dict[str, Any],
    ) -> int | None:
        for key in (
            "ticket",
            "deal_id",
            "deal",
        ):
            deal_id = cls._optional_int(deal.get(key))

            if deal_id is not None and deal_id > 0:
                return deal_id

        return None

    # ==============================================================
    # COMMENT MATCHING
    # ==============================================================

    @staticmethod
    def _normalize_comment(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        return " ".join(str(value).split())

    @classmethod
    def _matching_comment(
        cls,
        value: Any,
    ) -> str:
        """
        Recover the original comment before execution diagnostics were
        appended to the same database comment field.
        """

        normalized = cls._normalize_comment(value)

        marker = " | [execution] "

        if marker in normalized:
            normalized = normalized.split(marker, 1)[0].strip()

        return normalized[:31]

    @classmethod
    def _comment_matches(
        cls,
        expected: str,
        observed: Any,
    ) -> bool:
        candidate = cls._normalize_comment(observed)[:31]

        return bool(candidate) and candidate == expected[:31]

    # ==============================================================
    # DECIMAL HELPERS
    # ==============================================================

    @staticmethod
    def _decimal_or_zero(
        value: Any,
        *,
        default: Any = Decimal("0"),
    ) -> Decimal:
        if value is None:
            value = default

        try:
            result = Decimal(str(value))
        except (
            InvalidOperation,
            TypeError,
            ValueError,
            OverflowError,
        ):
            return Decimal("0")

        if not result.is_finite():
            return Decimal("0")

        return result

    @classmethod
    def _weighted_average_price(
        cls,
        deals: list[dict[str, Any]],
    ) -> Decimal | None:
        numerator = Decimal("0")
        denominator = Decimal("0")

        for deal in deals:
            volume = cls._decimal_or_zero(
                deal.get("volume"),
            )

            price = cls._decimal_or_zero(
                deal.get("price"),
            )

            if volume <= 0 or price <= 0:
                continue

            numerator += volume * price
            denominator += volume

        if denominator <= 0:
            return None

        return numerator / denominator

    # ==============================================================
    # ORDER UPDATES
    # ==============================================================

    @staticmethod
    def _apply_order_updates(
        order,
        **updates: Any,
    ) -> None:
        """Apply ORM attribute changes within the caller's transaction."""

        for field, value in updates.items():
            setattr(order, field, value)

    # ==============================================================
    # SEMANTIC ORDER STATE
    #==============================================================

    @staticmethod
    def _normalize_state(
        *values: Any,
    ) -> str:
        """
        Normalize already-semantic broker order states.

        Numeric MT5 order states must be translated in MT5Adapter,
        not interpreted inside this broker-neutral service.
        """

        for value in values:
            if value is None:
                continue

            raw = str(getattr(value, "value", value)).strip().upper()

            if not raw:
                continue

            aliases = {
                "CANCELED": "CANCELLED",
                "PARTIAL": "PARTIALLY_FILLED",
                "PLACED": "PENDING",
                "ACCEPTED": "PENDING",
                "OPEN": "PENDING",
            }

            return aliases.get(raw, raw)

        return ""


__all__ = [
    "OrderReconciliationError",
    "OrderReconciliationService",
]
