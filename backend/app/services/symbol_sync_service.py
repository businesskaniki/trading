from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.core.constants import AssetClass
from app.database.models.account_symbol import AccountSymbol
from app.database.models.symbol import Symbol
from app.repositories.account_symbol_repository import (
    AccountSymbolRepository,
)
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.trading_account_repository import (
    TradingAccountRepository,
)
from app.services.mt5_bridge_service import (
    MT5BridgeError,
    MT5BridgeService,
)


class SymbolSyncError(Exception):
    """
    Raised when symbol synchronization fails.
    """

    pass


class SymbolSyncService:
    """
    Synchronizes symbols exposed by an MT5 account into AQE.

    The synchronization maintains two levels:

        Symbol
            Canonical AQE instrument.

        AccountSymbol
            Account-specific broker representation.

    Example:

        MT5:
            EURUSD.s

        AQE:
            Symbol.name = EURUSD

            AccountSymbol:
                broker_symbol = EURUSD.s

    Synchronization never changes AccountSymbol.enabled.
    """

    def __init__(
        self,
        bridge_service: MT5BridgeService,
        trading_account_repository: TradingAccountRepository,
        symbol_repository: SymbolRepository,
        account_symbol_repository: AccountSymbolRepository,
    ) -> None:
        self.bridge = bridge_service
        self.trading_accounts = trading_account_repository
        self.symbols = symbol_repository
        self.account_symbols = account_symbol_repository

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    async def sync_account_symbols(
        self,
        account_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        Synchronize all MT5 symbols for one owned trading account.

        The entire synchronization is performed inside one
        database transaction.

        AccountSymbol.enabled is never modified.
        """

        account = await self.trading_accounts.get_by_id_and_user(
            account_id=account_id,
            user_id=user_id,
        )

        if account is None:
            raise SymbolSyncError("Trading account not found.")

        # ------------------------------------------------------
        # Retrieve symbols from MT5
        # ------------------------------------------------------

        try:
            broker_symbols = await self.bridge.get_symbols()

        except MT5BridgeError as exc:
            raise SymbolSyncError(
                f"Unable to retrieve symbols from MT5 bridge: {exc}"
            ) from exc

        if not broker_symbols:
            return {
                "account_id": str(account.id),
                "total_broker_symbols": 0,
                "symbols_created": 0,
                "symbols_existing": 0,
                "account_symbols_created": 0,
                "account_symbols_updated": 0,
                "skipped": 0,
                "message": ("No symbols were returned by the MT5 bridge."),
            }

        symbols_created = 0
        symbols_existing = 0
        account_symbols_created = 0
        account_symbols_updated = 0
        skipped = 0

        try:
            # --------------------------------------------------
            # Process every broker symbol
            # --------------------------------------------------

            for broker_symbol_data in broker_symbols:

                if not isinstance(
                    broker_symbol_data,
                    dict,
                ):
                    skipped += 1
                    continue

                # --------------------------------------------------
                # Broker identity
                # --------------------------------------------------

                broker_symbol = self._get_broker_symbol_name(broker_symbol_data)

                if not broker_symbol:
                    skipped += 1
                    continue

                canonical_name = self._canonicalize_symbol_name(broker_symbol)

                if not canonical_name:
                    skipped += 1
                    continue

                asset_class = self._detect_asset_class(broker_symbol_data)

                # --------------------------------------------------
                # Canonical Symbol
                # --------------------------------------------------

                symbol = await self.symbols.get_by_name(canonical_name)

                if symbol is None:

                    symbol = Symbol(
                        name=canonical_name,
                        description=self._clean_string(
                            broker_symbol_data.get("description")
                        ),
                        asset_class=asset_class,
                        active=True,
                    )

                    self.symbols.add(symbol)

                    # We need the generated UUID before creating
                    # AccountSymbol.
                    await self.symbols.flush()

                    symbols_created += 1

                else:

                    symbols_existing += 1

                    description = self._clean_string(
                        broker_symbol_data.get("description")
                    )

                    # Do not overwrite an existing canonical
                    # description with empty broker data.
                    if description and not symbol.description:
                        symbol.description = description

                # --------------------------------------------------
                # AccountSymbol
                # --------------------------------------------------

                account_symbol = await self.account_symbols.get_by_account_and_symbol(
                    account_id=account.id,
                    symbol_id=symbol.id,
                )

                # --------------------------------------------------
                # Existing mapping may have changed broker name
                # --------------------------------------------------

                if account_symbol is None:

                    account_symbol = await self.account_symbols.get_by_broker_symbol(
                        account_id=account.id,
                        broker_symbol=broker_symbol,
                    )

                # --------------------------------------------------
                # Create AccountSymbol
                # --------------------------------------------------

                if account_symbol is None:

                    account_symbol = AccountSymbol(
                        account_id=account.id,
                        symbol_id=symbol.id,
                        broker_symbol=broker_symbol,
                        path=self._clean_string(broker_symbol_data.get("path")),
                        currency_base=self._clean_string(
                            broker_symbol_data.get("currency_base")
                        ),
                        currency_profit=self._clean_string(
                            broker_symbol_data.get("currency_profit")
                        ),
                        currency_margin=self._clean_string(
                            broker_symbol_data.get("currency_margin")
                        ),
                        digits=self._get_int(
                            broker_symbol_data.get("digits"),
                            default=0,
                        ),
                        point=self._get_decimal(
                            broker_symbol_data.get("point"),
                            default=0,
                        ),
                        tick_size=self._get_tick_size(broker_symbol_data),
                        contract_size=(
                            self._get_decimal_or_none(
                                broker_symbol_data.get("trade_contract_size")
                            )
                        ),
                        min_volume=(
                            self._get_decimal_or_none(
                                broker_symbol_data.get("volume_min")
                            )
                        ),
                        max_volume=(
                            self._get_decimal_or_none(
                                broker_symbol_data.get("volume_max")
                            )
                        ),
                        volume_step=(
                            self._get_decimal_or_none(
                                broker_symbol_data.get("volume_step")
                            )
                        ),
                        visible=bool(
                            broker_symbol_data.get(
                                "visible",
                                False,
                            )
                        ),
                        # IMPORTANT:
                        # New symbols always start disabled.
                        enabled=False,
                    )

                    self.account_symbols.add(account_symbol)

                    account_symbols_created += 1

                # --------------------------------------------------
                # Update AccountSymbol
                # --------------------------------------------------

                else:

                    account_symbol.symbol_id = symbol.id
                    account_symbol.broker_symbol = broker_symbol

                    self._update_account_symbol(
                        account_symbol,
                        broker_symbol_data,
                    )

                    account_symbols_updated += 1

            # ------------------------------------------------------
            # ONE FLUSH
            # ------------------------------------------------------

            await self.symbols.flush()

            await self.account_symbols.flush()

            # ------------------------------------------------------
            # ONE COMMIT
            # ------------------------------------------------------

            await self.symbols.commit()

        except Exception as exc:

            # Roll back the same SQLAlchemy session.
            await self.symbols.rollback()

            if isinstance(exc, SymbolSyncError):
                raise

            raise SymbolSyncError(f"Symbol synchronization failed: {exc}") from exc

        return {
            "account_id": str(account.id),
            "total_broker_symbols": len(broker_symbols),
            "symbols_created": symbols_created,
            "symbols_existing": symbols_existing,
            "account_symbols_created": (account_symbols_created),
            "account_symbols_updated": (account_symbols_updated),
            "skipped": skipped,
            "message": ("Symbol synchronization completed successfully."),
        }

    # ==========================================================
    # ACCOUNT SYMBOL UPDATE
    # ==========================================================

    @staticmethod
    def _update_account_symbol(
        account_symbol: AccountSymbol,
        data: dict[str, Any],
    ) -> None:
        """
        Update broker/MT5 metadata.

        IMPORTANT:

        `enabled` is intentionally never modified.
        """

        account_symbol.path = SymbolSyncService._clean_string(data.get("path"))

        account_symbol.currency_base = SymbolSyncService._clean_string(
            data.get("currency_base")
        )

        account_symbol.currency_profit = SymbolSyncService._clean_string(
            data.get("currency_profit")
        )

        account_symbol.currency_margin = SymbolSyncService._clean_string(
            data.get("currency_margin")
        )

        account_symbol.digits = SymbolSyncService._get_int(
            data.get("digits"),
            default=account_symbol.digits,
        )

        account_symbol.point = SymbolSyncService._get_decimal(
            data.get("point"),
            default=account_symbol.point,
        )

        account_symbol.tick_size = SymbolSyncService._get_tick_size(
            data,
            fallback=account_symbol.tick_size,
        )

        account_symbol.contract_size = SymbolSyncService._get_decimal_or_none(
            data.get("trade_contract_size")
        )

        account_symbol.min_volume = SymbolSyncService._get_decimal_or_none(
            data.get("volume_min")
        )

        account_symbol.max_volume = SymbolSyncService._get_decimal_or_none(
            data.get("volume_max")
        )

        account_symbol.volume_step = SymbolSyncService._get_decimal_or_none(
            data.get("volume_step")
        )

        account_symbol.visible = bool(
            data.get(
                "visible",
                False,
            )
        )

    # ==========================================================
    # BROKER SYMBOL IDENTITY
    # ==========================================================

    @staticmethod
    def _get_broker_symbol_name(
        data: dict[str, Any],
    ) -> str | None:
        """
        Extract the broker-native MT5 symbol name.
        """

        value = data.get("name")

        if not isinstance(value, str):
            return None

        value = value.strip()

        return value or None

    @staticmethod
    def _canonicalize_symbol_name(
        broker_symbol: str,
    ) -> str:
        """
        Convert broker-native symbol names into canonical
        AQE symbol names.

        Examples:

            EURUSD.s   -> EURUSD
            XAUUSD.s   -> XAUUSD
            BTCUSD.raw -> BTCUSD
            EURUSD     -> EURUSD
        """

        name = broker_symbol.strip().upper()

        if not name:
            return ""

        suffixes = (
            ".RAW",
            ".STD",
            ".PRO",
            ".ECN",
            ".VIP",
            ".MICRO",
            ".MINI",
            ".CENT",
            ".CASH",
            ".S",
        )

        for suffix in suffixes:

            if name.endswith(suffix):
                return name[: -len(suffix)]

        match = re.match(
            r"^([A-Z0-9]{3,20})(?:[._-])([A-Z0-9]{1,10})$",
            name,
        )

        if match:
            return match.group(1)

        return name

    # ==========================================================
    # ASSET CLASS
    # ==========================================================

    @staticmethod
    def _detect_asset_class(
        data: dict[str, Any],
    ) -> AssetClass:
        """
        Determine AQE asset class from MT5 metadata.
        """

        name = str(data.get("name") or "").upper()

        path = str(data.get("path") or "").upper()

        text = f"{name} {path}"

        # ------------------------------------------------------
        # Crypto
        # ------------------------------------------------------

        crypto_terms = (
            "CRYPTO",
            "BITCOIN",
            "BTC",
            "ETH",
            "XRP",
            "LTC",
            "DOGE",
        )

        if any(term in text for term in crypto_terms):
            return AssetClass.CRYPTO

        # ------------------------------------------------------
        # Metals
        # ------------------------------------------------------

        metal_terms = (
            "METAL",
            "GOLD",
            "SILVER",
            "XAU",
            "XAG",
            "XPT",
            "XPD",
        )

        if any(term in text for term in metal_terms):
            return AssetClass.METALS

        # ------------------------------------------------------
        # Indices
        # ------------------------------------------------------

        index_terms = (
            "INDEX",
            "INDICES",
            "US30",
            "US100",
            "US500",
            "NAS100",
            "NASDAQ",
            "SPX",
            "GER40",
            "DAX",
            "UK100",
            "FTSE",
            "JP225",
            "NIKKEI",
        )

        if any(term in text for term in index_terms):
            return AssetClass.INDICES

        # ------------------------------------------------------
        # Stocks
        # ------------------------------------------------------

        stock_terms = (
            "STOCK",
            "EQUITIES",
            "SHARES",
        )

        if any(term in text for term in stock_terms):
            return AssetClass.STOCKS

        # ------------------------------------------------------
        # Commodities
        # ------------------------------------------------------

        commodity_terms = (
            "COMMODIT",
            "OIL",
            "BRENT",
            "WTI",
            "NATURAL GAS",
            "GAS",
        )

        if any(term in text for term in commodity_terms):
            return AssetClass.COMMODITIES

        # ------------------------------------------------------
        # Forex
        # ------------------------------------------------------

        if re.match(
            r"^[A-Z]{6}(?:[._-].*)?$",
            name,
        ):
            return AssetClass.FOREX

        if "FOREX" in text or "FX" in text:
            return AssetClass.FOREX

        # ------------------------------------------------------
        # Safe default
        # ------------------------------------------------------

        return AssetClass.FOREX

    # ==========================================================
    # VALUE HELPERS
    # ==========================================================

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            value = str(value)

        value = value.strip()

        return value or None

    @staticmethod
    def _get_int(
        value: Any,
        default: int,
    ) -> int:

        if value is None:
            return default

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _get_decimal(
        value: Any,
        default: Any,
    ):
        from decimal import Decimal

        if value is None:
            return default

        try:
            return Decimal(str(value))

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _get_decimal_or_none(
        value: Any,
    ):
        from decimal import Decimal

        if value is None:
            return None

        try:
            return Decimal(str(value))

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _get_tick_size(
        data: dict[str, Any],
        fallback=None,
    ):
        """
        Return MT5 tick size.

        If MT5 does not provide a valid tick size, use
        the symbol point as the fallback.
        """

        tick_size = data.get("trade_tick_size")

        if tick_size is not None:
            try:
                from decimal import Decimal

                value = Decimal(str(tick_size))

                if value > 0:
                    return value

            except (
                TypeError,
                ValueError,
            ):
                pass

        if fallback is not None:
            return fallback

        return SymbolSyncService._get_decimal(
            data.get("point"),
            default=0,
        )
