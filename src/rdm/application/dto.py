"""Shared DTO helpers used by both REST and MCP adapters."""

import re
from typing import Any

from rdm.domain.entities import User
from rdm.domain.errors import ValidationError
from rdm.i18n import tr

# 2–12 uppercase letters/digits (docs/architecture.md §3.2, decision §16.10).
PROJECT_KEY_RE = re.compile(r"^[A-Z0-9]{2,12}$")


def validate_project_key(key: str) -> str:
    if not isinstance(key, str) or not PROJECT_KEY_RE.match(key):
        raise ValidationError(
            tr(
                "errors.project_key_format",
                default="项目 key 必须是 2–12 位大写字母或数字（name 可用中文）。",
            ),
            details={"field": "key", "pattern": PROJECT_KEY_RE.pattern},
        )
    return key


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def user_brief(user: User) -> dict[str, Any]:
    """Compact user payload shared by REST and MCP (§17.116).

    ``name`` stays the address handle; ``display_name`` is presentation-only
    and may be ``None``, in which case clients render ``name``.
    """
    return {
        "id": user.id,
        "name": user.name,
        "display_name": user.display_name,
        "type": user.type,
    }
