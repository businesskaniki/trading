from datetime import datetime, timedelta, timezone

from jose import jwt

from backend.app.core.config import settings

ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    expires_minutes: int = 60,
):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )

    payload = {
        "sub": subject,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_token(token: str):
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
    )