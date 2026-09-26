from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.database.models.trading_account import TradingAccount
from app.services.trading_account_service import TradingAccountService


@dataclass(frozen=True, slots=True)
class RuntimeAccount:
    """
    Runtime representation of an AQE trading account.

    This object contains the information required to construct and
    authenticate a broker connection.

    The decrypted password exists only in this runtime object and must
    never be persisted or exposed through an API response.
    """

    account_id: UUID
    user_id: UUID

    broker: str
    login: int
    server: str

    account_name: str | None
    bridge_url: str | None
    is_demo: bool

    password: str

    @property
    def broker_credentials(self) -> dict[str, object]:
        """
        Build the credentials payload expected by BrokerAdapter.connect().

        The payload intentionally contains only broker authentication
        information. AQE account metadata is kept outside the broker
        credentials payload.
        """

        return {
            "login": self.login,
            "password": self.password,
            "server": self.server,
        }


class RuntimeAccountResolver:
    """
    Resolve a persisted TradingAccount into runtime broker credentials.

    Responsibilities:
        - Load the requested trading account.
        - Verify that the account is eligible for runtime use.
        - Decrypt the stored broker password.
        - Produce a RuntimeAccount.

    This class does NOT:
        - connect to a broker,
        - create a BrokerAdapter,
        - start market data,
        - start strategies,
        - execute orders,
        - modify account state.

    Those responsibilities belong to the AQE runtime/composition layer.
    """

    def __init__(
        self,
        trading_account_service: TradingAccountService,
    ) -> None:
        self.trading_account_service = trading_account_service

    async def resolve(
        self,
        account_id: UUID,
    ) -> RuntimeAccount:
        """
        Resolve an account for AQE runtime use.

        The account's own user_id is used when requesting the decrypted
        credentials from TradingAccountService. This keeps ownership
        validation inside the account service while avoiding any
        dependency on an authenticated HTTP request inside the engine.
        """

        account = await self._get_account(account_id)

        password = await self.trading_account_service.get_decrypted_credentials(
            account_id=account.id,
            user_id=account.user_id,
        )

        return self._build_runtime_account(
            account=account,
            password=password,
        )

    async def _get_account(
        self,
        account_id: UUID,
    ) -> TradingAccount:
        """
        Retrieve the persisted trading account.

        TradingAccountService owns the repository access and therefore
        remains the single business-logic boundary for account retrieval.
        """

        account = await self.trading_account_service.repository.get_by_id(
            account_id,
        )

        if account is None:
            raise ValueError(
                f"Trading account {account_id} was not found."
            )

        if not account.active:
            raise ValueError(
                f"Trading account {account_id} is disabled."
            )

        return account

    @staticmethod
    def _build_runtime_account(
        *,
        account: TradingAccount,
        password: str,
    ) -> RuntimeAccount:
        """
        Convert the persisted ORM account into an immutable runtime object.
        """

        broker = account.broker.value

        return RuntimeAccount(
            account_id=account.id,
            user_id=account.user_id,
            broker=broker,
            login=account.login,
            server=account.server,
            account_name=account.account_name,
            bridge_url=account.bridge_url,
            is_demo=account.is_demo,
            password=password,
        )