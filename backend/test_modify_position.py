import asyncio

from app.broker.mt5.adapter import MT5Adapter
from app.broker.broker_manager import BrokerManager
from app.services.execution_service import ExecutionService


POSITION_ID = 421503164


async def main():

    adapter = MT5Adapter(
        "http://127.0.0.1:9000"
    )

    broker = BrokerManager(adapter)

    service = ExecutionService(broker)

    # ==========================================================
    # GET POSITION BEFORE MODIFICATION
    # ==========================================================

    print("\n=== POSITION BEFORE ===")

    position = await adapter.get_position(
        POSITION_ID
    )

    print(position)

    # ==========================================================
    # MODIFY SL / TP
    # ==========================================================

    print("\n=== MODIFYING POSITION ===")

    result = await service.modify_position(
        position_id=POSITION_ID,
        sl=4405.00,
        tp=4425.00,
    )

    print(result)

    # ==========================================================
    # GET POSITION AFTER MODIFICATION
    # ==========================================================

    print("\n=== POSITION AFTER ===")

    position = await adapter.get_position(
        POSITION_ID
    )

    print(position)


if __name__ == "__main__":
    asyncio.run(main())