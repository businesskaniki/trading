from datetime import datetime, timezone
from uuid import UUID

from app.core.security import get_password_hash, verify_password
from app.database.models.email_verification import EmailVerification
from app.repositories.email_verification_repository import (
    EmailVerificationRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.email_service import EmailService
from app.services.otp_service import OTPService
from app.repositories.password_reset_repository import PasswordResetRepository
from app.database.models.password_reset import PasswordReset


class UserService:
    """
    Business logic for users and authentication.
    """

    def __init__(
        self,
        repository: UserRepository,
        email_verification_repository: EmailVerificationRepository,
        password_reset_repository: PasswordResetRepository,
        email_service: EmailService,
    ):
        self.repository = repository
        self.email_verification_repository = email_verification_repository
        self.password_reset_repository = password_reset_repository
        self.email_service = email_service

    # ==========================================================
    # Register
    # ==========================================================

    async def create_user(self, data: UserCreate):
        existing = await self.repository.get_by_email(data.email)

        if existing:
            raise ValueError("A user with this email already exists.")

        user = await self.repository.create(
            email=data.email,
            full_name=data.full_name,
            hashed_password=get_password_hash(data.password),
        )

        otp, otp_hash = OTPService.generate_hashed_otp()

        verification = EmailVerification(
            user_id=user.id,
            otp_hash=otp_hash,
            expires_at=OTPService.expires_at(),
        )

        await self.email_verification_repository.create(verification)

        await self.email_service.send_verification_email(
            recipient=user.email,
            otp=otp,
        )

        return user

    # ==========================================================
    # Verify Email
    # ==========================================================

    async def verify_email(self, email: str, otp: str):
        user = await self.repository.get_by_email(email)

        if not user:
            raise ValueError("User not found.")

        if user.email_verified:
            raise ValueError("Email already verified.")

        verification = await self.email_verification_repository.get_active_by_user_id(
            user.id
        )

        if verification is None:
            raise ValueError("Verification code not found.")

        if verification.expires_at < datetime.now(timezone.utc):
            raise ValueError("Verification code has expired.")

        verification.attempts += 1
        await self.email_verification_repository.update(verification)

        if not OTPService.verify_otp(
            otp,
            verification.otp_hash,
        ):
            raise ValueError("Invalid verification code.")

        await self.repository.update(
            user,
            email_verified=True,
        )

        await self.email_verification_repository.mark_verified(verification)

        return user

    # ==========================================================
    # Resend OTP
    # ==========================================================

    async def resend_verification_code(self, email: str):
        user = await self.repository.get_by_email(email)

        if not user:
            raise ValueError("User not found.")

        if user.email_verified:
            raise ValueError("Email already verified.")

        verification = await self.email_verification_repository.get_active_by_user_id(
            user.id
        )

        otp, otp_hash = OTPService.generate_hashed_otp()

        if verification:

            verification.otp_hash = otp_hash
            verification.expires_at = OTPService.expires_at()
            verification.attempts = 0

            await self.email_verification_repository.update(verification)

        else:

            verification = EmailVerification(
                user_id=user.id,
                otp_hash=otp_hash,
                expires_at=OTPService.expires_at(),
            )

            await self.email_verification_repository.create(verification)

        await self.email_service.send_verification_email(
            recipient=user.email,
            otp=otp,
        )

        return True

    # ==========================================================
    # Authentication
    # ==========================================================

    async def authenticate(
        self,
        email: str,
        password: str,
    ):
        user = await self.repository.get_by_email(email)

        if not user:
            return None

        if not verify_password(
            password,
            user.hashed_password,
        ):
            return None

        if not user.email_verified:
            raise ValueError("Please verify your email before logging in.")

        return user

    # ==========================================================
    # Queries
    # ==========================================================

    async def get_user(self, user_id: UUID):
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise ValueError("User not found.")

        return user

    async def get_user_by_email(self, email: str):
        return await self.repository.get_by_email(email)


    async def forgot_password(self, email: str):
        """
        Generate and email a password reset OTP.
        """

        user = await self.repository.get_by_email(email)

        if not user:
            raise ValueError("User not found.")

        otp, otp_hash = OTPService.generate_hashed_otp()

        password_reset = await self.password_reset_repository.get_by_user_id(
            user.id
        )

        if password_reset:

            password_reset.otp_hash = otp_hash
            password_reset.expires_at = OTPService.expires_at()
            password_reset.used = False
            password_reset.attempts = 0

            await self.password_reset_repository.update(password_reset)

        else:

            password_reset = PasswordReset(
                user_id=user.id,
                otp_hash=otp_hash,
                expires_at=OTPService.expires_at(),
            )

            await self.password_reset_repository.create(password_reset)

        await self.email_service.send_password_reset_email(
            recipient=user.email,
            otp=otp,
        )

        return True


    async def reset_password(
        self,
        email: str,
        otp: str,
        new_password: str,
    ):
        """
        Verify OTP and update the user's password.
        """

        user = await self.repository.get_by_email(email)

        if not user:
            raise ValueError("User not found.")

        password_reset = await self.password_reset_repository.get_by_user_id(
            user.id
        )

        if password_reset is None:
            raise ValueError("Password reset request not found.")

        if password_reset.used:
            raise ValueError("This reset code has already been used.")

        if password_reset.expires_at < datetime.now(timezone.utc):
            raise ValueError("Reset code has expired.")

        if not OTPService.verify_otp(
            otp,
            password_reset.otp_hash,
        ):
            await self.password_reset_repository.increment_attempts(
                password_reset,
            )

            raise ValueError("Invalid reset code.")

        await self.repository.update(
            user,
            hashed_password=get_password_hash(new_password),
        )

        await self.password_reset_repository.mark_used(
            password_reset,
        )

        return True
