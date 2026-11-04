"""Validation for the Web frontend origin used in work item links (RDM-127).

The API and the Web SPA are deployed separately, so an agent must not assume
that work item links share the MCP server's origin. Every configuration surface
(CLI, REST, MCP) accepts only a bare origin: scheme + host[:port], with no
path, query or fragment.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def normalize_web_origin(value: str) -> str:
    """Return ``scheme://host[:port]`` or raise ``ValueError``."""
    raw = value.strip()
    parts = urlsplit(raw)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            f"invalid web origin {value!r}; want http(s)://host[:port] without path/query"
        )
    return f"{parts.scheme}://{parts.netloc}"
