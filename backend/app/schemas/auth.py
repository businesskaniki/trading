from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    email: str
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "password": "StrongPassword123",
            }
        }
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI..."
            }
        }
    )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "<JWT_ACCESS_TOKEN>",
                "refresh_token": "<JWT_REFRESH_TOKEN>",
                "token_type": "bearer",
                "user": {
                    "id": "uuid",
                    "email": "john@example.com",
                    "full_name": "John Doe",
                    "is_active": True,
                    "is_superuser": False,
                    "email_verified": True,
                    "created_at": "2026-08-05T10:00:00Z",
                    "updated_at": "2026-08-05T10:00:00Z",
                },
            }
        }
    )


class MessageResponse(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Operation completed successfully"
            }
        }
    )