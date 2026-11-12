from __future__ import annotations

import asyncio
import logging

from app.database.session import SessionLocal
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.services.mt5_bridge_service import (
    MT5BridgeError,
    MT5BridgeService,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class MarketDataSubscriptionManager:
    """Reconciles AQE's desired market-data subscriptions with the

    subscriptions currently active on the MT5 Bridge.

    Desired state
    -------------
    PostgreSQL AccountSymbol.enabled == True

    Actual state
    ------------
    MT5 Bridge market-data subscriptions

    The manager operates globally across all trading accounts.

    If multiple trading accounts have the same broker symbol enabled,
    only one MT5 Bridge subscription is maintained.

    Database sessions
    -----------------
    A fresh AsyncSession is created for every reconciliation query.
    The manager never stores a request-scoped database session.

    Concurrency
    -----------
    Reconciliation is protected by an asyncio.Lock so multiple API
    requests cannot simultaneously modify MT5 Bridge subscriptions.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bridge_service: MT5BridgeService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.bridge_service = bridge_service or MT5BridgeService()

        self._lock = asyncio.Lock()

    # ======================================================================
    # DESIRED STATE
    # ======================================================================

    async def get_desired_subscriptions(self) -> set[str]:
        """Return subscriptions required by the actual connected MT5 account.

        The MT5 Bridge maintains one terminal session. Only enabled symbols
        belonging to the saved account matching the bridge's current login
        and server are considered desired.

        If the bridge explicitly reports that it is disconnected, the
        desired subscription set is empty. Existing saved symbol selections
        are not modified.
        """

        # The live terminal identity is authoritative. Do not infer it from
        # the frontend's selected account or potentially stale DB status.
        bridge_status = await self.bridge_service.status()

        if not bridge_status.get("connected", False):
            logger.info(
                "MT5 Bridge is disconnected; no market-data subscriptions "
                "are currently required."
            )
            return set()

        bridge_login = bridge_status.get("login")
        bridge_server = bridge_status.get("server")

        if bridge_login is None or not isinstance(bridge_server, str):
            raise MT5BridgeError(
                "MT5 Bridge reports a connected session but did not provide "
                "a valid login and server. Subscription reconciliation "
                "was aborted to avoid using the wrong account."
            )

        try:
            bridge_login = int(bridge_login)
        except (TypeError, ValueError) as exc:
            raise MT5BridgeError(
                "MT5 Bridge returned an invalid connected-account login."
            ) from exc

        bridge_server = bridge_server.strip()

        if not bridge_server:
            raise MT5BridgeError(
                "MT5 Bridge returned an empty connected-account server."
            )

        async with self.session_factory() as session:
            repository = AccountSymbolRepository(session)

            account_symbols = await repository.list_enabled_for_broker_account(
                login=bridge_login,
                server=bridge_server,
            )

        desired: set[str] = set()

        for account_symbol in account_symbols:
            broker_symbol = account_symbol.broker_symbol

            if isinstance(broker_symbol, str) and broker_symbol.strip():
                desired.add(broker_symbol.strip())

        logger.info(
            "Desired market-data subscriptions resolved for connected "
            "MT5 account login=%s server=%s: %d symbols",
            bridge_login,
            bridge_server,
            len(desired),
        )

        return desired

    # ======================================================================
    # ACTUAL STATE
    # ======================================================================

    async def get_actual_subscriptions(self) -> set[str]:
        """Read the subscriptions currently active on the MT5 Bridge."""

        response = await self.bridge_service.get_subscriptions()

        subscriptions = response.get("subscriptions")

        if not isinstance(subscriptions, list):
            raise MT5BridgeError(
                "MT5 Bridge returned an invalid subscriptions collection."
            )

        actual: set[str] = set()

        for symbol in subscriptions:
            if not isinstance(symbol, str):
                raise MT5BridgeError("MT5 Bridge returned a non-string subscription.")

            symbol = symbol.strip()

            if symbol:
                actual.add(symbol)

        return actual

    # ======================================================================
    # RECONCILIATION
    # ======================================================================

    async def reconcile(self) -> dict[str, list[str]]:
        """Reconcile PostgreSQL desired subscriptions with the actual

        subscriptions on the MT5 Bridge.

        Returns
        -------
        dict
            {
                "subscribed": [...],
                "unsubscribed": [...],
                "unchanged": [...],
                "failed_subscriptions": [...],
                "failed_unsubscriptions": [...],
            }

        Database state remains the source of truth.

        If the MT5 Bridge is temporarily unavailable, the database
        selection is not changed or rolled back. A later reconciliation
        can correct the bridge state.
        """

        async with self._lock:
            return await self._reconcile_locked()

    async def _reconcile_locked(self) -> dict[str, list[str]]:
        """Perform reconciliation while the manager lock is held."""

        desired = await self.get_desired_subscriptions()
        actual = await self.get_actual_subscriptions()

        to_subscribe = sorted(desired - actual)
        to_unsubscribe = sorted(actual - desired)
        unchanged = sorted(desired & actual)

        subscribed: list[str] = []
        unsubscribed: list[str] = []

        failed_subscriptions: list[str] = []
        failed_unsubscriptions: list[str] = []

        # --------------------------------------------------------------
        # Subscribe missing symbols
        # --------------------------------------------------------------

        for symbol in to_subscribe:
            try:
                await self.bridge_service.subscribe_symbol(symbol)

                subscribed.append(symbol)

                logger.info(
                    "Market-data subscription added: %s",
                    symbol,
                )

            except MT5BridgeError:
                failed_subscriptions.append(symbol)

                logger.exception(
                    "Failed to subscribe market-data symbol: %s",
                    symbol,
                )

        # --------------------------------------------------------------
        # Unsubscribe symbols no longer required
        # --------------------------------------------------------------

        for symbol in to_unsubscribe:
            try:
                await self.bridge_service.unsubscribe_symbol(symbol)

                unsubscribed.append(symbol)

                logger.info(
                    "Market-data subscription removed: %s",
                    symbol,
                )

            except MT5BridgeError:
                failed_unsubscriptions.append(symbol)

                logger.exception(
                    "Failed to unsubscribe market-data symbol: %s",
                    symbol,
                )

        result = {
            "subscribed": subscribed,
            "unsubscribed": unsubscribed,
            "unchanged": unchanged,
            "failed_subscriptions": failed_subscriptions,
            "failed_unsubscriptions": failed_unsubscriptions,
        }

        logger.info(
            (
                "Market-data subscription reconciliation completed: "
                "desired=%d actual=%d subscribed=%d "
                "unsubscribed=%d unchanged=%d "
                "failed_subscriptions=%d "
                "failed_unsubscriptions=%d"
            ),
            len(desired),
            len(actual),
            len(subscribed),
            len(unsubscribed),
            len(unchanged),
            len(failed_subscriptions),
            len(failed_unsubscriptions),
        )

        return result

    # ======================================================================
    # SINGLE SYMBOL
    # ======================================================================

    async def reconcile_symbol(
        self,
        broker_symbol: str,
    ) -> dict[str, list[str]]:
        """Reconcile the subscription state after a single broker symbol

        has been enabled or disabled.

        The full desired state is still evaluated so duplicate usage
        of the same broker symbol across accounts is handled correctly.

        The broker_symbol argument is retained for logging and
        diagnostics.
        """

        logger.debug(
            "Reconciling market-data subscription for symbol: %s",
            broker_symbol,
        )

        return await self.reconcile()


# ==========================================================================
# GLOBAL INSTANCE
# ==========================================================================

market_data_subscription_manager = MarketDataSubscriptionManager(
    session_factory=SessionLocal,
)
