from pydantic import BaseModel


class ConnectRequest(BaseModel):
    login: int
    password: str
    server: str


class ConnectionStatus(BaseModel):
    connected: bool
    login: int | None = None
    server: str | None = None
    name: str | None = None
    last_error: str | None = None


class VersionResponse(BaseModel):
    version: tuple


class DisconnectResponse(BaseModel):
    success: bool
    message: str