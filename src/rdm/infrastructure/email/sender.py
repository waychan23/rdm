"""Outbound email delivery (RDM-122)."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from rdm.domain.entities import EmailSettings
from rdm.domain.errors import EmailSendFailed
from rdm.i18n import tr


class EmailSecretBox:
    """Encrypts the stored SMTP password with a process-local key file.

    Mirrors the webhook/attachment secret pattern: the key lives in the data
    dir with 0600 permissions, so a database dump alone cannot reveal the
    password.
    """

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_path(cls, path: Path) -> EmailSecretBox:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(Fernet.generate_key())
            path.chmod(0o600)
        return cls(Fernet(path.read_bytes().strip()))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise EmailSendFailed(
                tr("email.password_decrypt_failed"),
                details={"reason": "invalid_secret_key"},
            ) from exc


class SmtpEmailSender:
    """Send one plain-text message through the configured SMTP server.

    ``smtplib`` is blocking, so the network call runs in a worker thread; the
    configured timeout bounds how long a mailbox send can hold the write lock.
    """

    def __init__(self, secret_box: EmailSecretBox, *, timeout: float = 15.0) -> None:
        self._secret_box = secret_box
        self._timeout = timeout

    async def send(
        self,
        settings: EmailSettings,
        *,
        recipients: Sequence[tuple[str, str]],
        subject: str,
        text: str,
        reply_to: str | None = None,
    ) -> None:
        if not settings.enabled:
            raise EmailSendFailed(tr("email.disabled"))
        if not settings.smtp_host or not settings.from_address:
            raise EmailSendFailed(tr("email.incomplete"))
        to = [address for address, kind in recipients if kind == "to"]
        cc = [address for address, kind in recipients if kind == "cc"]
        password = (
            self._secret_box.decrypt(settings.password_ciphertext)
            if settings.password_ciphertext
            else None
        )
        message = self._build_message(
            settings,
            to=to,
            cc=cc,
            subject=subject,
            text=text,
            reply_to=reply_to,
        )
        await asyncio.to_thread(self._send_sync, settings, password, message, to + cc)

    @staticmethod
    def _build_message(
        settings: EmailSettings,
        *,
        to: Sequence[str],
        cc: Sequence[str],
        subject: str,
        text: str,
        reply_to: str | None,
    ) -> EmailMessage:
        assert settings.from_address is not None
        message = EmailMessage()
        sender_name = (settings.from_name or "").strip()
        message["From"] = formataddr((sender_name, settings.from_address))
        if to:
            message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        message["Subject"] = subject
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(text)
        return message

    def _send_sync(
        self,
        settings: EmailSettings,
        password: str | None,
        message: EmailMessage,
        envelope_recipients: Sequence[str],
    ) -> None:
        assert settings.smtp_host is not None and settings.from_address is not None
        try:
            if settings.smtp_security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=self._timeout,
                    context=ssl.create_default_context(),
                )
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=self._timeout)
            try:
                if settings.smtp_security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    server.login(settings.smtp_username, password or "")
                server.send_message(
                    message,
                    from_addr=settings.from_address,
                    to_addrs=list(envelope_recipients),
                )
            finally:
                try:
                    server.quit()
                except smtplib.SMTPException:
                    server.close()
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailSendFailed(
                tr("email.send_failed", reason=str(exc)),
                details={"reason": str(exc)},
            ) from exc
