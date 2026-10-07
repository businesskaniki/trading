from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
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
    """Raised when symbol synchronization fails."""


class SymbolSyncService:
    """
    Synchronize symbols exposed by an MT5 account into AQE.

    AQE maintains two levels of symbol identity:

        Symbol
            Canonical AQE instrument identity.

        AccountSymbol
            Account-specific broker representation.

    Example:

        MT5:
            XAUUSD.s

        AQE:

            Symbol
                name = XAUUSD

            AccountSymbol
                broker_symbol = XAUUSD.s

    Synchronization rules:

    - Broker-native names are preserved in AccountSymbol.broker_symbol.
    - Canonical names are stored in Symbol.name.
    - AccountSymbol.enabled is owned by AQE and is NEVER changed here.
    - Broker metadata is refreshed on every synchronization.
    - Existing canonical Symbol metadata is not blindly overwritten.
    - Unknown instruments are not silently classified as FOREX.
    - Synchronization is atomic for the current database session.
    """

    # ==========================================================
    # CLASSIFICATION CONSTANTS
    # ==========================================================

    _CRYPTO_SYMBOLS = frozenset(
        {
            "BTCUSD",
            "BTCUSDT",
            "BTCEUR",
            "BTCGBP",
            "ETHUSD",
            "ETHUSDT",
            "ETHEUR",
            "XRPUSD",
            "XRPUSDT",
            "LTCUSD",
            "LTCUSDT",
            "DOGEUSD",
            "DOGEUSDT",
        }
    )

    _METAL_SYMBOLS = frozenset(
        {
            "XAUUSD",
            "XAUEUR",
            "XAUGBP",
            "XAGUSD",
            "XAGEUR",
            "XPTUSD",
            "XPDUSD",
        }
    )

    _INDEX_SYMBOLS = frozenset(
        {
            "US30",
            "US100",
            "US500",
            "NAS100",
            "NASDAQ",
            "SPX",
            "SP500",
            "GER40",
            "GER30",
            "DAX",
            "UK100",
            "FTSE",
            "JP225",
            "JPN225",
            "NIKKEI",
        }
    )

    _COMMODITY_SYMBOLS = frozenset(
        {
            "USOIL",
            "UKOIL",
            "WTI",
            "BRENT",
            "XBRUSD",
            "XTIUSD",
            "NATGAS",
            "NGAS",
        }
    )

    _CRYPTO_PATH_TERMS = (
        "CRYPTO",
        "CRYPTOS",
        "CRYPTOCURRENCY",
        "DIGITAL ASSET",
        "DIGITAL ASSETS",
    )

    _METAL_PATH_TERMS = (
        "METAL",
        "METALS",
        "PRECIOUS METAL",
        "PRECIOUS METALS",
    )

    _INDEX_PATH_TERMS = (
        "INDEX",
        "INDICES",
        "INDICE",
    )

    _STOCK_PATH_TERMS = (
        "STOCK",
        "STOCKS",
        "EQUITY",
        "EQUITIES",
        "SHARE",
        "SHARES",
    )

    _COMMODITY_PATH_TERMS = (
        "COMMODITY",
        "COMMODITIES",
        "ENERGY",
        "OIL",
        "BRENT",
        "WTI",
        "NATURAL GAS",
        "NATGAS",
        "GAS",
    )

    _FOREX_PATH_TERMS = (
        "FOREX",
        "FX",
        "CURRENCIES",
        "CURRENCY",
    )

    _BROKER_SUFFIXES = (
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

        AccountSymbol.enabled is never modified.

        Returns a synchronization summary containing creation,
        update, and skipped-symbol counts.
        """

        account = await self.trading_accounts.get_by_id_and_user(
            account_id=account_id,
            user_id=user_id,
        )

        if account is None:
            raise SymbolSyncError("Trading account not found.")

        # ------------------------------------------------------
        # Retrieve broker symbols
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
                "message": "No symbols were returned by the MT5 bridge.",
            }

        symbols_created = 0
        symbols_existing = 0
        account_symbols_created = 0
        account_symbols_updated = 0
        skipped = 0

        # Prevent duplicate processing of the same broker symbol
        # if the bridge unexpectedly returns duplicates.
        processed_broker_symbols: set[str] = set()

        try:
            # --------------------------------------------------
            # Process broker symbols
            # --------------------------------------------------

            for raw_data in broker_symbols:

                if not isinstance(raw_data, dict):
                    skipped += 1
                    continue

                broker_symbol = self._get_broker_symbol_name(raw_data)

                if not broker_symbol:
                    skipped += 1
                    continue

                broker_symbol_key = broker_symbol.upper()

                if broker_symbol_key in processed_broker_symbols:
                    skipped += 1
                    continue

                processed_broker_symbols.add(broker_symbol_key)

                # --------------------------------------------------
                # Canonical identity
                # --------------------------------------------------

                canonical_name = self._canonicalize_symbol_name(broker_symbol)

                if not canonical_name:
                    skipped += 1
                    continue

                # --------------------------------------------------
                # Asset class
                # --------------------------------------------------

                asset_class = self._detect_asset_class(raw_data)

                if asset_class is None:
                    skipped += 1
                    continue

                # --------------------------------------------------
                # Canonical Symbol
                # --------------------------------------------------

                symbol = await self.symbols.get_by_name(canonical_name)

                if symbol is None:

                    description = self._clean_string(raw_data.get("description"))

                    symbol = Symbol(
                        name=canonical_name,
                        description=description,
                        asset_class=asset_class,
                        active=True,
                    )

                    self.symbols.add(symbol)

                    # We need symbol.id before creating the
                    # AccountSymbol relation.
                    await self.symbols.flush()

                    symbols_created += 1

                else:

                    symbols_existing += 1

                    # Description is broker-derived information,
                    # but we only fill an empty canonical
                    # description. We do not destroy existing AQE
                    # metadata with empty broker data.
                    description = self._clean_string(raw_data.get("description"))

                    if description and not symbol.description:
                        symbol.description = description

                # --------------------------------------------------
                # AccountSymbol lookup
                # --------------------------------------------------

                account_symbol = await self.account_symbols.get_by_account_and_symbol(
                    account_id=account.id,
                    symbol_id=symbol.id,
                )

                # If the broker representation changed, try the
                # broker-native identity as a fallback.
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
                        path=self._clean_string(raw_data.get("path")),
                        currency_base=self._clean_string(raw_data.get("currency_base")),
                        currency_profit=self._clean_string(
                            raw_data.get("currency_profit")
                        ),
                        currency_margin=self._clean_string(
                            raw_data.get("currency_margin")
                        ),
                        digits=self._get_int(
                            raw_data.get("digits"),
                            default=0,
                        ),
                        point=self._get_decimal(
                            raw_data.get("point"),
                            default=Decimal("0"),
                        ),
                        tick_size=self._get_tick_size(raw_data),
                        contract_size=self._get_decimal_or_none(
                            raw_data.get("trade_contract_size")
                        ),
                        min_volume=self._get_decimal_or_none(
                            raw_data.get("volume_min")
                        ),
                        max_volume=self._get_decimal_or_none(
                            raw_data.get("volume_max")
                        ),
                        volume_step=self._get_decimal_or_none(
                            raw_data.get("volume_step")
                        ),
                        visible=self._get_bool(
                            raw_data.get("visible"),
                            default=False,
                        ),
                        # IMPORTANT:
                        # AQE owns this field.
                        # Synchronization never enables symbols.
                        enabled=False,
                    )

                    self.account_symbols.add(account_symbol)

                    account_symbols_created += 1

                # --------------------------------------------------
                # Update AccountSymbol
                # --------------------------------------------------

                else:

                    # Keep the canonical relationship synchronized.
                    account_symbol.symbol_id = symbol.id

                    # Preserve the current broker-native name.
                    account_symbol.broker_symbol = broker_symbol

                    # Update only broker metadata.
                    self._update_account_symbol(
                        account_symbol,
                        raw_data,
                    )

                    account_symbols_updated += 1

            # ------------------------------------------------------
            # Flush pending changes
            # ------------------------------------------------------

            await self.symbols.flush()
            await self.account_symbols.flush()

            # ------------------------------------------------------
            # Commit the complete synchronization
            # ------------------------------------------------------

            await self.symbols.commit()

        except Exception as exc:

            # All repositories use the same AsyncSession, so
            # rolling back through one repository rolls back the
            # complete transaction.
            await self.symbols.rollback()

            if isinstance(exc, SymbolSyncError):
                raise

            raise SymbolSyncError(f"Symbol synchronization failed: {exc}") from exc

        return {
            "account_id": str(account.id),
            "total_broker_symbols": len(broker_symbols),
            "symbols_created": symbols_created,
            "symbols_existing": symbols_existing,
            "account_symbols_created": account_symbols_created,
            "account_symbols_updated": account_symbols_updated,
            "skipped": skipped,
            "message": "Symbol synchronization completed successfully.",
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
        Update broker-derived AccountSymbol metadata.

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

        account_symbol.visible = SymbolSyncService._get_bool(
            data.get("visible"),
            default=False,
        )

        # NEVER modify account_symbol.enabled here.

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

    @classmethod
    def _canonicalize_symbol_name(
        cls,
        broker_symbol: str,
    ) -> str:
        """
        Convert a broker-native MT5 symbol into an AQE
        canonical symbol.

        Examples:

            EURUSD.s      -> EURUSD
            XAUUSD.s      -> XAUUSD
            BTCUSD.raw    -> BTCUSD
            EURUSD        -> EURUSD
            US100         -> US100

        The broker-native representation remains available through
        AccountSymbol.broker_symbol.
        """

        name = broker_symbol.strip().upper()

        if not name:
            return ""

        # Remove known broker suffixes.
        for suffix in cls._BROKER_SUFFIXES:

            if name.endswith(suffix):
                canonical = name[: -len(suffix)].strip()

                if canonical:
                    return canonical

        # Generic broker suffix handling.
        #
        # Example:
        #
        #     EURUSD.MYBROKER
        #
        # becomes:
        #
        #     EURUSD
        #
        # Only apply this when the prefix is clearly an
        # instrument-style identifier. This avoids blindly
        # stripping meaningful names.
        match = re.fullmatch(
            r"([A-Z0-9]{3,20})[._-][A-Z0-9]{1,10}",
            name,
        )

        if match:
            return match.group(1)

        return name

    # ==========================================================
    # ASSET CLASS
    # ==========================================================

    @classmethod
    def _detect_asset_class(
        cls,
        data: dict[str, Any],
    ) -> AssetClass | None:
        """
        Determine the AQE asset class from MT5 metadata.

        Returns None when the instrument cannot be classified
        safely.

        The method intentionally does NOT default unknown
        instruments to FOREX.
        """

        name = cls._canonicalize_symbol_name(cls._get_broker_symbol_name(data) or "")

        raw_name = str(data.get("name") or "").strip().upper()

        path = str(data.get("path") or "").strip().upper()

        description = str(data.get("description") or "").strip().upper()

        # ------------------------------------------------------
        # Explicit broker metadata
        # ------------------------------------------------------

        # Some bridge implementations may expose an asset class
        # directly. Accept it when it matches our enum.
        explicit_asset_class = data.get("asset_class")

        if isinstance(explicit_asset_class, AssetClass):
            return explicit_asset_class

        if isinstance(explicit_asset_class, str):
            normalized = explicit_asset_class.strip().upper()

            for asset_class in AssetClass:

                if normalized in {
                    asset_class.name,
                    asset_class.value,
                }:
                    return asset_class

        # ------------------------------------------------------
        # Exact canonical symbol matches
        # ------------------------------------------------------

        if name in cls._CRYPTO_SYMBOLS:
            return AssetClass.CRYPTO

        if name in cls._METAL_SYMBOLS:
            return AssetClass.METALS

        if name in cls._INDEX_SYMBOLS:
            return AssetClass.INDICES

        if name in cls._COMMODITY_SYMBOLS:
            return AssetClass.COMMODITIES

        # ------------------------------------------------------
        # Path classification
        # ------------------------------------------------------

        if cls._contains_term(path, cls._CRYPTO_PATH_TERMS):
            return AssetClass.CRYPTO

        if cls._contains_term(path, cls._METAL_PATH_TERMS):
            return AssetClass.METALS

        if cls._contains_term(path, cls._INDEX_PATH_TERMS):
            return AssetClass.INDICES

        if cls._contains_term(path, cls._STOCK_PATH_TERMS):
            return AssetClass.STOCKS

        if cls._contains_term(path, cls._COMMODITY_PATH_TERMS):
            return AssetClass.COMMODITIES

        if cls._contains_term(path, cls._FOREX_PATH_TERMS):
            return AssetClass.FOREX

        # ------------------------------------------------------
        # Description classification
        # ------------------------------------------------------

        descriptive_text = f"{description} {path}"

        if cls._contains_term(
            descriptive_text,
            cls._CRYPTO_PATH_TERMS,
        ):
            return AssetClass.CRYPTO

        if cls._contains_term(
            descriptive_text,
            cls._METAL_PATH_TERMS,
        ):
            return AssetClass.METALS

        if cls._contains_term(
            descriptive_text,
            cls._INDEX_PATH_TERMS,
        ):
            return AssetClass.INDICES

        if cls._contains_term(
            descriptive_text,
            cls._STOCK_PATH_TERMS,
        ):
            return AssetClass.STOCKS

        if cls._contains_term(
            descriptive_text,
            cls._COMMODITY_PATH_TERMS,
        ):
            return AssetClass.COMMODITIES

        # ------------------------------------------------------
        # Strong symbol-name patterns
        # ------------------------------------------------------

        # Standard FX pair:
        #
        #     EURUSD
        #     GBPJPY
        #     AUDCAD
        #
        # ISO-style currencies consist of exactly six letters.
        if re.fullmatch(
            r"[A-Z]{6}",
            name,
        ):
            return AssetClass.FOREX

        # Crypto symbols that were not in the explicit list.
        crypto_prefixes = (
            "BTC",
            "ETH",
            "XRP",
            "LTC",
            "DOGE",
            "SOL",
            "ADA",
            "DOT",
            "BNB",
            "AVAX",
            "LINK",
            "MATIC",
        )

        if name.startswith(crypto_prefixes):
            return AssetClass.CRYPTO

        # Common precious-metal naming conventions.
        if name.startswith(
            (
                "XAU",
                "XAG",
                "XPT",
                "XPD",
            )
        ):
            return AssetClass.METALS

        # ------------------------------------------------------
        # Common index naming conventions
        # ------------------------------------------------------

        index_prefixes = (
            "US30",
            "US100",
            "US500",
            "NAS",
            "SPX",
            "GER",
            "DAX",
            "UK100",
            "FTSE",
            "JP225",
            "JPN225",
            "NIKKEI",
        )

        if name.startswith(index_prefixes):
            return AssetClass.INDICES

        # ------------------------------------------------------
        # Common commodity naming conventions
        # ------------------------------------------------------

        commodity_prefixes = (
            "OIL",
            "BRENT",
            "WTI",
            "NATGAS",
            "GAS",
        )

        if name.startswith(commodity_prefixes):
            return AssetClass.COMMODITIES

        # ------------------------------------------------------
        # No safe classification
        # ------------------------------------------------------

        return None

    @staticmethod
    def _contains_term(
        text: str,
        terms: tuple[str, ...],
    ) -> bool:
        """
        Check whether text contains one of the supplied
        classification terms.

        Terms containing spaces are matched literally.
        Short abbreviations are matched as tokens to avoid
        accidental substring classifications.
        """

        if not text:
            return False

        normalized = text.upper()

        for term in terms:

            term = term.upper().strip()

            if not term:
                continue

            if " " in term:
                if term in normalized:
                    return True

                continue

            # Match path/name components rather than arbitrary
            # substrings. This prevents values such as "GAS"
            # from matching unrelated words accidentally.
            if re.search(
                rf"(?<![A-Z0-9]){re.escape(term)}(?![A-Z0-9])",
                normalized,
            ):
                return True

        return False

    # ==========================================================
    # VALUE HELPERS
    # ==========================================================

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> str | None:
        """
        Normalize an arbitrary value into a stripped string.
        """

        if value is None:
            return None

        if not isinstance(value, str):
            value = str(value)

        value = value.strip()

        return value or None

    @staticmethod
    def _get_int(
        value: Any,
        default: int,
    ) -> int:
        """
        Safely convert a value to int.
        """

        if value is None:
            return default

        try:
            return int(value)

        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get_decimal(
        value: Any,
        default: Decimal,
    ) -> Decimal:
        """
        Safely convert a value to Decimal.
        """

        if value is None:
            return default

        try:
            return Decimal(str(value))

        except (
            TypeError,
            ValueError,
            InvalidOperation,
        ):
            return default

    @staticmethod
    def _get_decimal_or_none(
        value: Any,
    ) -> Decimal | None:
        """
        Safely convert a value to Decimal or None.
        """

        if value is None:
            return None

        try:
            return Decimal(str(value))

        except (
            TypeError,
            ValueError,
            InvalidOperation,
        ):
            return None

    @staticmethod
    def _get_bool(
        value: Any,
        default: bool,
    ) -> bool:
        """
        Safely normalize boolean-like broker values.

        MT5 bridge responses may provide either actual booleans
        or serialized values.
        """

        if value is None:
            return default

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):

            normalized = value.strip().lower()

            if normalized in {
                "true",
                "1",
                "yes",
                "y",
                "on",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "n",
                "off",
            }:
                return False

        return default

    @staticmethod
    def _get_tick_size(
        data: dict[str, Any],
        fallback: Decimal | None = None,
    ) -> Decimal:
        """
        Return the broker's tick size.

        Priority:

            1. trade_tick_size
            2. existing AccountSymbol.tick_size
            3. point
            4. Decimal("0")
        """

        tick_size = data.get("trade_tick_size")

        if tick_size is not None:

            try:
                value = Decimal(str(tick_size))

                if value > 0:
                    return value

            except (
                TypeError,
                ValueError,
                InvalidOperation,
            ):
                pass

        if fallback is not None:
            return fallback

        point = SymbolSyncService._get_decimal(
            data.get("point"),
            default=Decimal("0"),
        )

        return point
