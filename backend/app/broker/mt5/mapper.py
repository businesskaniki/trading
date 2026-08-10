from app.schemas.execution import (
    ExecutionOrder,
    OrderSide,
    OrderType,
)


class MT5OrderMapper:
    """
    Converts AQE broker-agnostic orders into
    MT5 Bridge order payloads.
    """

    @staticmethod
    def to_mt5(
        order: ExecutionOrder,
    ) -> dict:

        payload = {
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "volume": float(order.volume),
            "deviation": order.deviation,
            "magic_number": order.magic_number,
            "comment": order.comment,
        }

        if order.price is not None:
            payload["price"] = float(order.price)

        if order.stop_loss is not None:
            payload["stop_loss"] = float(
                order.stop_loss
            )

        if order.take_profit is not None:
            payload["take_profit"] = float(
                order.take_profit
            )

        return payload