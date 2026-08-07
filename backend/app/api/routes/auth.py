from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_user_service
from app.core.security import (
    create_access_token,
    create_refresh_token,
    oauth2_scheme,
    verify_token,
)
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

    access_token = create_access_token(
        subject=str(user.id),
    )

    refresh_token = create_refresh_token(
        subject=str(user.id),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
    }


# ==========================================================
# Refresh Token
# ==========================================================


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh_token(
    payload: RefreshTokenRequest,
    service=Depends(get_user_service),
):
    try:
        token_data = verify_token(
            payload.refresh_token,
            expected_type="refresh",
        )

        user = await service.get_user(token_data["sub"])

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    return TokenResponse(
        access_token=create_access_token(
            subject=str(user.id),
        ),
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
    token: str = Depends(oauth2_scheme),
):
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
