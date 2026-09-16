from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_user_service
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    MessageResponse,
)
from app.schemas.email_verification import (
    VerifyEmailRequest,
    ResendOTPRequest,
)
from app.schemas.user import UserCreate, UserResponse
from app.schemas.password_reset import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.APP_ENV.lower() == "production",
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/api/v1/auth",
    )


# ==========================================================
# Register
# ==========================================================


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    payload: UserCreate,
    service=Depends(get_user_service),
):
    try:
        await service.create_user(payload)

        return MessageResponse(
            message="Registration successful. Please check your email for the verification code."
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ==========================================================
# Verify Email
# ==========================================================


@router.post(
    "/verify-email",
    response_model=MessageResponse,
)
async def verify_email(
    payload: VerifyEmailRequest,
    service=Depends(get_user_service),
):
    try:
        await service.verify_email(
            email=payload.email,
            otp=payload.otp,
        )

        return MessageResponse(message="Email verified successfully.")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ==========================================================
# Resend OTP
# ==========================================================


@router.post(
    "/resend-otp",
    response_model=MessageResponse,
)
async def resend_otp(
    payload: ResendOTPRequest,
    service=Depends(get_user_service),
):
    try:
        await service.resend_verification_code(
            payload.email,
        )

        return MessageResponse(message="Verification code sent successfully.")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ==========================================================
# Login
# ==========================================================


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    service=Depends(get_user_service),
):
    try:
        user = await service.authenticate(
            payload.email,
            payload.password,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token = create_access_token(subject=str(user.id), token_version=user.token_version)
    refresh_token = create_refresh_token(subject=str(user.id), token_version=user.token_version)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


# ==========================================================
# Refresh Token
# ==========================================================


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    service=Depends(get_user_service),
):
    try:
        token_data = verify_token(
            (payload.refresh_token if payload else request.cookies.get(REFRESH_COOKIE_NAME, "")),
            expected_type="refresh",
        )

        user = await service.get_user(token_data["sub"])
        if token_data.get("ver") != user.token_version:
            raise ValueError("Token has been revoked")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    # Rotate the refresh token and invalidate the presented one.
    user.token_version += 1
    user = await service.repository.update(user, token_version=user.token_version)
    new_refresh_token = create_refresh_token(subject=str(user.id), token_version=user.token_version)
    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), token_version=user.token_version),
        token_type="bearer",
    )


# ==========================================================
# Logout
# ==========================================================


@router.post(
    "/logout",
    response_model=MessageResponse,
)
async def logout(
    request: Request,
    response: Response,
    service=Depends(get_user_service),
):
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        try:
            token_data = verify_token(token, expected_type="refresh")
            user = await service.get_user(token_data["sub"])
            user.token_version += 1
            await service.repository.update(user, token_version=user.token_version)
        except ValueError:
            pass
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return MessageResponse(message="Logout successful.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    service=Depends(get_user_service),
):
    try:
        await service.forgot_password(
            payload.email,
        )

        return MessageResponse(message="Password reset code sent successfully.")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
)
async def reset_password(
    payload: ResetPasswordRequest,
    service=Depends(get_user_service),
):
    try:
        await service.reset_password(
            email=payload.email,
            otp=payload.otp,
            new_password=payload.new_password,
        )

        return MessageResponse(message="Password reset successfully.")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
