import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login"
)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(message: str) -> bytes:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _serialize(payload: dict) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _base64url_encode(header_bytes)
    payload_b64 = _base64url_encode(payload_bytes)
    signature_b64 = _base64url_encode(_sign(f"{header_b64}.{payload_b64}"))

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _deserialize(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise ValueError("Invalid token format")

    expected_signature = _base64url_encode(_sign(f"{header_b64}.{payload_b64}"))
    if not hmac.compare_digest(expected_signature, signature_b64):
        raise ValueError("Invalid token signature")

    payload_json = _base64url_decode(payload_b64)
    payload = json.loads(payload_json)

    exp = payload.get("exp")
    if exp is None or datetime.now(timezone.utc).timestamp() > exp:
        raise ValueError("Token has expired")

    return payload


def create_access_token(subject: str, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "exp": expire.timestamp(),
        "type": "access",
    }
    return _serialize(payload)


def create_refresh_token(subject: str, expires_minutes: int = REFRESH_TOKEN_EXPIRE_MINUTES) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "exp": expire.timestamp(),
        "type": "refresh",
    }
    return _serialize(payload)


def verify_token(token: str, expected_type: str | None = None) -> dict:
    payload = _deserialize(token)
    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise ValueError("Invalid token type")
    return payload


def get_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    raw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    )
    return f"{salt}${_base64url_encode(raw_hash)}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, expected = hashed_password.split("$", 1)
    except ValueError:
        return False

    raw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    )
    return hmac.compare_digest(_base64url_encode(raw_hash), expected)
