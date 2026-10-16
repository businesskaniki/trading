
from pydantic import BaseModel, ConfigDict


class ConnectRequest(BaseModel):
    login: int
    password: str
    server: str


class ConnectionStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    connected: bool

    login: int | None = None
    server: str | None = None
    name: str | None = None
    last_error: str | None = None

    internet_connected: bool | None = None
    terminal_running: bool | None = None
    terminal_connected: bool | None = None

    recovery_state: str | None = None
    reconnect_attempts: int = 0

    last_connect_attempt_at: float | None = None
    last_internet_check_at: float | None = None
    last_recovery_action: str | None = None


class VersionResponse(BaseModel):
    version: tuple


class DisconnectResponse(BaseModel):
    success: bool
    message: str
