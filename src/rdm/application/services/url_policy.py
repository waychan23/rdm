"""URL validation for artifact/workspace/webhook links."""

from __future__ import annotations

import re

from rdm.domain.errors import ValidationError

_URL_RE = re.compile(r"^https?://\S{1,980}$", re.IGNORECASE)


def ensure_http_url(url: str, *, field: str = "url") -> str:
    url = (url or "").strip()
    if not _URL_RE.match(url):
        raise ValidationError(
            f"{field} 必须是 http:// 或 https:// 开头的合法 URL",
            details={"field": field, "url": url},
        )
    return url
