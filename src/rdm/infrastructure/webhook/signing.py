"""HMAC-SHA256 request signing and the on-disk process secret (§16.47)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path


class WebhookSecretStore:
    """Lazily creates data-dir/webhook-secret with 0600 permissions."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._secret: bytes | None = None

    def get(self) -> bytes:
        if self._secret is not None:
            return self._secret
        if self._path.exists():
            self._secret = self._path.read_bytes().strip()
            return self._secret
        self._path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_bytes(32)
        fd = os.open(
            self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            os.write(fd, token.hex().encode("ascii"))
        finally:
            os.close(fd)
        self._secret = token.hex().encode("ascii")
        return self._secret


def sign(secret: bytes, timestamp: int, body: bytes) -> str:
    """HMAC over '<unix-seconds>.<raw-body>' (§16.47)."""
    message = f"{timestamp}.".encode("ascii") + body
    return hmac.new(secret, message, hashlib.sha256).hexdigest()
