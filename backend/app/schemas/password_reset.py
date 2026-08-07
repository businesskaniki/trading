from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com"
            }
        }
    )


class ResetPasswordRequest(BaseModel):
    email: EmailStr

    otp: str = Field(
        min_length=6,
        max_length=6,
    )

    new_password: str = Field(
        min_length=8,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "otp": "123456",
                "new_password": "StrongPassword123!"
            }
        }
    )