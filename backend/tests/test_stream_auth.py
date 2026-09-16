import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_USERNAME", "test")
os.environ.setdefault("SMTP_PASSWORD", "test")
os.environ.setdefault("SMTP_FROM_EMAIL", "test@example.com")

from app.core.security import create_access_token, verify_token


def test_tick_stream_requires_access_token():
    try:
        verify_token("", expected_type="access")
    except ValueError as exc:
        assert str(exc) == "Invalid token format"
    else:
        raise AssertionError("invalid stream token was accepted")


def test_tick_stream_accepts_access_token():
    payload = verify_token(create_access_token("user-1"), expected_type="access")
    assert payload["sub"] == "user-1"


def test_tokens_include_the_user_token_version():
    payload = verify_token(
        create_access_token("user-1", token_version=4),
        expected_type="access",
    )
    assert payload["ver"] == 4
