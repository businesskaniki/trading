from pydantic import BaseModel, ConfigDict, EmailStr, Field


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "otp": "482931",
            }
        }
    )


class ResendOTPRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
            }
        }
    )


class VerificationResponse(BaseModel):
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Email verified successfully.",
            }
        }
    )