import MetaTrader5 as mt5


class AccountBroker:

    @staticmethod
    def get_account():

        return mt5.account_info()