"""SMTP STARTTLS certificate-validation regression.

``smtplib.SMTP.starttls()`` called with no ``context`` argument does not
verify the server's certificate by default, which would silently accept a
MITM'd SMTP connection. ``SmtpEmailSender`` must pass an explicit
``ssl.create_default_context()`` (which verifies hostname and certificate
chain by default) so TLS actually protects the connection when
``smtp_use_tls`` is enabled, while leaving the (test/local) non-TLS path
unchanged.
"""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.services.email import SmtpEmailSender


def _settings(**overrides) -> Settings:
    base = dict(
        environment="test",
        jwt_secret_key="test-jwt-secret-key-at-least-32-bytes-long",
        smtp_host="smtp.example.com",
        smtp_port=587,
    )
    base.update(overrides)
    return Settings(**base)


def _mock_smtp_client() -> MagicMock:
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


def test_starttls_uses_a_verifying_default_context_in_correct_order() -> None:
    settings = _settings(smtp_use_tls=True, smtp_username="mailer", smtp_password="mailer-secret")
    sender = SmtpEmailSender(settings)
    client = _mock_smtp_client()

    created_contexts: list[ssl.SSLContext] = []
    real_create_default_context = ssl.create_default_context

    def _spy_create_default_context(*args, **kwargs):
        context = real_create_default_context(*args, **kwargs)
        created_contexts.append(context)
        return context

    with (
        patch("app.services.email.smtplib.SMTP", return_value=client) as mock_smtp_cls,
        patch(
            "app.services.email.ssl.create_default_context",
            side_effect=_spy_create_default_context,
        ) as mock_create_context,
    ):
        sender.send(to_address="player@example.com", subject="Subject", body="Body")

    mock_smtp_cls.assert_called_once_with(settings.smtp_host, settings.smtp_port, timeout=10)
    mock_create_context.assert_called_once_with()
    assert len(created_contexts) == 1
    context = created_contexts[0]
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED

    client.starttls.assert_called_once_with(context=context)
    client.login.assert_called_once_with("mailer", "mailer-secret")
    client.send_message.assert_called_once()

    call_order = [call[0] for call in client.method_calls]
    assert call_order.index("starttls") < call_order.index("login") < call_order.index("send_message")


def test_tls_disabled_never_creates_a_context_or_calls_starttls() -> None:
    settings = _settings(smtp_use_tls=False)
    sender = SmtpEmailSender(settings)
    client = _mock_smtp_client()

    with (
        patch("app.services.email.smtplib.SMTP", return_value=client),
        patch("app.services.email.ssl.create_default_context") as mock_create_context,
    ):
        sender.send(to_address="player@example.com", subject="Subject", body="Body")

    mock_create_context.assert_not_called()
    client.starttls.assert_not_called()
    client.send_message.assert_called_once()
