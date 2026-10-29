"""Short-lived signed download URLs for MCP attachment access.

MCP OAuth access tokens carry the `mcp` audience and are rejected by the REST
API (§17.79), so an agent cannot simply `curl` a `download_url` with its MCP
token. `attachment_list` / `work_item_get` / `comment_list` therefore return a
15-minute signed URL; the download endpoint accepts either a Bearer credential
or a valid signature. PAT clients keep using `download_url` with Bearer.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

DEFAULT_TTL_SECONDS = 900


class AttachmentUrlSigner:
    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    @classmethod
    def from_path(cls, path: Path) -> AttachmentUrlSigner:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(secrets.token_bytes(32))
            path.chmod(0o600)
        return cls(path.read_bytes())

    def _signature(self, attachment_id: str, exp: int) -> str:
        message = f"{attachment_id}.{exp}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def signed_url(
        self,
        base_url: str,
        attachment_id: str,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> str:
        exp = int(time.time()) + max(1, ttl_seconds)
        sig = self._signature(attachment_id, exp)
        return (
            f"{base_url.rstrip('/')}/api/v1/attachments/{attachment_id}/download"
            f"?exp={exp}&sig={sig}"
        )

    def verify(self, attachment_id: str, exp: int, sig: str) -> bool:
        if exp < int(time.time()):
            return False
        return hmac.compare_digest(self._signature(attachment_id, exp), sig)
