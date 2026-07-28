"""Email delivery abstraction.

``EmailSender`` is a small protocol so tests can inject a fake that records
messages instead of talking to a real SMTP server. In local development and
docker-compose, ``SmtpEmailSender`` talks to Mailpit.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings


class EmailSender(Protocol):
    def send(self, *, to_address: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, *, to_address: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_address
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as client:
            if self._settings.smtp_use_tls:
                client.starttls()
            if self._settings.smtp_username and self._settings.smtp_password:
                client.login(self._settings.smtp_username, self._settings.smtp_password)
            client.send_message(message)


def send_verification_email(sender: EmailSender, *, to_address: str, verify_url: str) -> None:
    sender.send(
        to_address=to_address,
        subject="Verify your Breakpoint account",
        body=f"Welcome to Breakpoint! Verify your account:\n\n{verify_url}\n",
    )


def send_password_reset_email(sender: EmailSender, *, to_address: str, reset_url: str) -> None:
    sender.send(
        to_address=to_address,
        subject="Reset your Breakpoint password",
        body=f"Reset your Breakpoint password:\n\n{reset_url}\n\nIf you did not request this, ignore this email.\n",
    )
