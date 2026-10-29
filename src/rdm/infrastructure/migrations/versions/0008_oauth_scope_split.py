"""M5: split the single `mcp` scope into `web` (browser) and `mcp` (DCR).

Before this revision the first-party `rdm-web` client also asked for `mcp`,
which made every OAuth token interchangeable between the REST API and /mcp.
Tokens are now audience-bound (§17.79); rows issued to the browser client must
be rewritten, otherwise refresh keeps minting `mcp` tokens that the REST API
rejects.

Data-only: no schema change.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEB_CLIENT_ID = "rdm-web"
_OLD_SCOPE = '["mcp"]'
_NEW_SCOPE = '["web"]'
_SCOPE_COLUMNS = (
    "user_token",
    "oauth_authorization_code",
    "oauth_consent_request",
    "oauth_login_ticket",
)


def upgrade() -> None:
    conn = op.get_bind()
    _rewrite_client_info(conn, "web")
    for table in _SCOPE_COLUMNS:
        conn.execute(
            text(f"UPDATE {table} SET scopes = :new WHERE client_id = :cid AND scopes = :old"),
            {"new": _NEW_SCOPE, "cid": _WEB_CLIENT_ID, "old": _OLD_SCOPE},
        )


def downgrade() -> None:
    conn = op.get_bind()
    _rewrite_client_info(conn, "mcp")
    for table in _SCOPE_COLUMNS:
        conn.execute(
            text(f"UPDATE {table} SET scopes = :old WHERE client_id = :cid AND scopes = :new"),
            {"new": _NEW_SCOPE, "cid": _WEB_CLIENT_ID, "old": _OLD_SCOPE},
        )


def _rewrite_client_info(conn, scope: str) -> None:  # type: ignore[no-untyped-def]
    """Patch the verbatim OAuthClientInformationFull JSON of the web client."""
    row = conn.execute(
        text("SELECT client_info FROM oauth_client WHERE client_id = :cid"),
        {"cid": _WEB_CLIENT_ID},
    ).first()
    if row is None:
        return
    raw = row[0]
    info = json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)
    if info.get("scope") == scope:
        return
    info["scope"] = scope
    conn.execute(
        text("UPDATE oauth_client SET client_info = :info WHERE client_id = :cid"),
        {"info": json.dumps(info), "cid": _WEB_CLIENT_ID},
    )
