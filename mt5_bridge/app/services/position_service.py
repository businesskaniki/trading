
from __future__ import annotations

from typing import Any

from app.broker.positions import PositionBroker


class PositionService:
    """
    Application service for MetaTrader 5 position operations.

    The broker layer deals with MT5 objects. This service converts
    those objects into the stable HTTP contract consumed by AQE.
    """

    def __init__(self) -> None:
        self.broker = PositionBroker()

    # ------------------------------------------------------------------
    # Position retrieval
    # ------------------------------------------------------------------

    def list_positions(self) -> list[dict[str, Any]]:
        positions = self.broker.positions()

        if positions is None:
            return []

        return [
            self._normalize_position(position)
            for position in positions
        ]

    def get_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        positions = self.broker.position(ticket)

        if not positions:
            return None

        return self._normalize_position(positions[0])

    def by_symbol(
        self,
        symbol: str,
    ) -> list[dict[str, Any]]:
        positions = self.broker.by_symbol(symbol)

        if positions is None:
            return []

        return [
            self._normalize_position(position)
            for position in positions
        ]

    # ------------------------------------------------------------------
    # Position execution
    # ------------------------------------------------------------------

    def close_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        return self.broker.close(ticket)

    def modify_position(
        self,
        ticket: int,
        sl: float | None = None,
        tp: float | None = None,
    ) -> dict[str, Any] | None:
        return self.broker.modify(
            ticket=ticket,
            sl=sl,
            tp=tp,
        )

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_position(position: Any) -> dict[str, Any]:
        """
        Convert an MT5 Position namedtuple into the bridge's
        explicit position contract.

        No order/deal IDs are invented here because an MT5 position
        object does not represent the originating order/deal.
        """

        return {
            # Position identity
            "ticket": int(position.ticket),
            "identifier": int(position.identifier),

            # Broker metadata
            "symbol": str(position.symbol),
            "magic": int(position.magic),
            "reason": int(position.reason),
            "comment": str(position.comment or ""),

            # Position state
            "type": int(position.type),
            "volume": float(position.volume),

            "price_open": float(position.price_open),
            "price_current": float(position.price_current),

            "sl": float(position.sl or 0.0),
            "tp": float(position.tp or 0.0),

            # Financial state
            "swap": float(position.swap),
            "profit": float(position.profit),

            # Timestamps
            "time": int(position.time),
            "time_msc": int(position.time_msc),

            "time_update": int(position.time_update),
            "time_update_msc": int(position.time_update_msc),
        }
