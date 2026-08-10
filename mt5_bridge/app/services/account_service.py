from app.broker.account import AccountBroker


class AccountService:

    def __init__(self):
        self.broker = AccountBroker()

    def get_account(self):

        account = self.broker.get_account()

        if account is None:
            raise Exception("Unable to retrieve account information.")

        return account._asdict()