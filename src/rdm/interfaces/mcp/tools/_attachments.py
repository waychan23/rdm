"""Shared MCP attachment DTO: REST shape plus a short-lived signed URL."""

from __future__ import annotations

from typing import Any

from rdm.domain.entities import Attachment
from rdm.interfaces.http.serializers import attachment_out


def attachment_mcp_out(container: Any, attachment: Attachment, members: dict) -> dict[str, Any]:
    out = attachment_out(attachment, members)
    out["fetch_url"] = container.attachment_signer.signed_url(
        container.settings.base_url, attachment.id
    )
    return out
