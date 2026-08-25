import asyncio

from app.broker.mt5.adapter import MT5Adapter
from app.broker.broker_manager import BrokerManager
from app.services.execution_service import ExecutionService


async def main():

    # ==========================================================
    # MT5 ADAPTER
    # ==========================================================

    adapter = MT5Adapter(
        "http://127.0.0.1:9000"
    )

    # ==========================================================
    # BROKER MANAGER
    # ==========================================================

    broker = BrokerManager(
        adapter=adapter
    )

    # ==========================================================
    # EXECUTION SERVICE
    # ==========================================================

    service = ExecutionService(
        broker=broker
    )

    # ==========================================================
    # CONNECTION
    # ==========================================================

    print("\n=== CONNECTION ===")

    connection = await adapter.connection_status()

    print(connection)

    # ==========================================================
    # ACCOUNT
    # ==========================================================

    print("\n=== ACCOUNT ===")

    account = await broker.get_account()

    print(account)

    # ==========================================================
    # POSITIONS
    # ==========================================================

    print("\n=== POSITIONS ===")

    positions = await service.get_positions()

    print(positions)

    # ==========================================================
    # ORDERS
    # ==========================================================

    print("\n=== ORDERS ===")

    orders = await broker.get_orders()

    print(orders)


if __name__ == "__main__":
    asyncio.run(main())