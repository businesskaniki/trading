from datetime import UTC, datetime, timedelta
import hashlib
import secrets


class OTPService:
    """
    Service responsible for generating and validating OTP codes.
    """

    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 10

    # ==========================================================
    # Generate
    # ==========================================================

    @staticmethod
    def generate_otp() -> str:
        """
        Generate a secure 6-digit OTP.
        """
        return f"{secrets.randbelow(1_000_000):06d}"

    # ==========================================================
    # Hashing
    # ==========================================================

    @staticmethod
    def hash_otp(otp: str) -> str:
        """
        Hash an OTP before storing it in the database.
        """
        return hashlib.sha256(otp.encode()).hexdigest()

    @classmethod
    def generate_hashed_otp(cls) -> tuple[str, str]:
        """
        Returns:
            (plain_otp, hashed_otp)
        """
        otp = cls.generate_otp()
        hashed = cls.hash_otp(otp)
        return otp, hashed

    # ==========================================================
    # Verification
    # ==========================================================

    @classmethod
    def verify_otp(
        cls,
        plain_otp: str,
        stored_hash: str,
    ) -> bool:
        """
        Verify an OTP against its stored hash.
        """
        return cls.hash_otp(plain_otp) == stored_hash

    # ==========================================================
    # Expiration
    # ==========================================================

    @classmethod
    def expires_at(cls) -> datetime:
        """
        Returns the expiration timestamp for a newly generated OTP.
        """
        return datetime.now(UTC) + timedelta(
            minutes=cls.OTP_EXPIRY_MINUTES
        )

    @staticmethod
    def is_expired(expires_at: datetime) -> bool:
        """
        Returns True if the OTP has expired.
        """
        return datetime.now(UTC) >= expires_at