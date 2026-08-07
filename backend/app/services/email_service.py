from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


class EmailService:
    """
    Service responsible for sending application emails.
    """

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.use_tls = settings.SMTP_USE_TLS

    # ==========================================================
    # Generic Email Sender
    # ==========================================================

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
    ) -> None:
        """
        Send an email.
        """

        message = EmailMessage()

        message["From"] = self.from_email
        message["To"] = recipient
        message["Subject"] = subject

        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=self.use_tls,
        )

    # ==========================================================
    # Email Verification
    # ==========================================================

    async def send_verification_email(
        self,
        recipient: str,
        otp: str,
    ) -> None:
        """
        Send an email verification OTP.
        """

        subject = "Verify your Athena Quant Engine account"

        body = f"""
Hello,

Welcome to Athena Quant Engine.

Your email verification code is:

{otp}

This code will expire in 10 minutes.

If you did not create an account, you can safely ignore this email.

Regards,
Athena Quant Engine Team
"""

        await self.send_email(
            recipient=recipient,
            subject=subject,
            body=body,
        )

    # ==========================================================
    # Password Reset
    # ==========================================================

    async def send_password_reset_email(
        self,
        recipient: str,
        otp: str,
    ) -> None:
        """
        Send a password reset OTP.
        """

        subject = "Reset your Athena Quant Engine password"

        body = f"""
Hello,

We received a request to reset your Athena Quant Engine password.

Use the verification code below to continue:

{otp}

This code will expire in 10 minutes.

If you did not request a password reset, simply ignore this email. Your password has not been changed.

Regards,
Athena Quant Engine Team
"""

        await self.send_email(
            recipient=recipient,
            subject=subject,
            body=body,
        )
