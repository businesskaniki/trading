from pydantic import BaseModel


class ConnectRequest(BaseModel):
    login: int
    password: str
    server: str


class ConnectionStatus(BaseModel):
    connected: bool


class VersionResponse(BaseModel):
    version: tuple


class DisconnectResponse(BaseModel):
    success: bool
    message: str