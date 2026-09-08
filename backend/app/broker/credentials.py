import json

from app.core.security import decrypt_secret, encrypt_secret


def encrypt_credentials(data: dict) -> str:
    """
    Encrypt a dict of broker credentials - e.g. {"password": "..."}
    for MT5, or {"api_key": "...", "api_secret": "..."} for Binance -
    into the single string stored in
    TradingAccount.credentials_encrypted.
    """
    return encrypt_secret(json.dumps(data))


def decrypt_credentials(token: str) -> dict:
    """
    Reverse of encrypt_credentials(). Only call this from internal
    code that needs the real credentials (e.g. the engine connecting
    to a broker) - never expose the result through an API route.
    """
    return json.loads(decrypt_secret(token))