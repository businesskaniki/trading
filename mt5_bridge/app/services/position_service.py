from app.broker.positions import PositionBroker


class PositionService:

    def __init__(self):
        self.broker = PositionBroker()

    def list_positions(self):

        positions = self.broker.positions()

        if positions is None:
            return []

        return [
            position._asdict()
            for position in positions
        ]

    def get_position(
        self,
        ticket: int,
    ):

        positions = self.broker.position(ticket)

        if not positions:
            return None

        return positions[0]._asdict()

    def by_symbol(
        self,
        symbol: str,
    ):

        positions = self.broker.by_symbol(symbol)

        if positions is None:
            return []

        return [
            position._asdict()
            for position in positions
        ]

    def close_position(
        self,
        ticket: int,
    ):

        return self.broker.close(ticket)