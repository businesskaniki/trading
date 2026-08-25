import asyncio

from app.broker.mt5.adapter import MT5Adapter
from app.broker.broker_manager import BrokerManager
from app.services.execution_service import ExecutionService
from app.schemas.execution import (
    ExecutionOrder,
    OrderSide,
    OrderType,
)


async def main():

    # ==========================================================
    # MT5 BRIDGE
    # ==========================================================

    adapter = MT5Adapter(
        "http://127.0.0.1:9000"
    )

    # ==========================================================
    # BROKER MANAGER
    # ==========================================================

    broker = BrokerManager(adapter)

    # ==========================================================
    # EXECUTION SERVICE
    # ==========================================================

    service = ExecutionService(broker)

    # ==========================================================
    # TEST ORDER
    # ==========================================================

    order = ExecutionOrder(
        symbol="XAUUSD.s",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.01,
        stop_loss=None,
        take_profit=None,
        deviation=20,
        magic_number=10001,
        comment="AQE EXECUTION SERVICE TEST",
    )

    print("\n=== EXECUTING ORDER ===")

    result = await service.execute_order(order)

    print(result)


if __name__ == "__main__":
    asyncio.run(main())