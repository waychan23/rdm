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


def _rewrite_scopes(conn, table: str, *, new: str, old: str) -> None:  # type: ignore[no-untyped-def]
    if conn.dialect.name == "postgresql":
        # json has no equality operator; compare as jsonb for semantic equality
        # and cast the text parameter when assigning.
        conn.execute(
            text(
                f"UPDATE {table} SET scopes = CAST(:new AS JSON) "
                "WHERE client_id = :cid AND CAST(scopes AS JSONB) = CAST(:old AS JSONB)"
            ),
            {"new": new, "cid": _WEB_CLIENT_ID, "old": old},
        )
    else:
        conn.execute(
            text(f"UPDATE {table} SET scopes = :new WHERE client_id = :cid AND scopes = :old"),
            {"new": new, "cid": _WEB_CLIENT_ID, "old": old},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _rewrite_client_info(conn, "web")
    for table in _SCOPE_COLUMNS:
        _rewrite_scopes(conn, table, new=_NEW_SCOPE, old=_OLD_SCOPE)


def downgrade() -> None:
    conn = op.get_bind()
    _rewrite_client_info(conn, "mcp")
    for table in _SCOPE_COLUMNS:
        _rewrite_scopes(conn, table, new=_OLD_SCOPE, old=_NEW_SCOPE)


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
    statement = (
        "UPDATE oauth_client SET client_info = CAST(:info AS JSON) WHERE client_id = :cid"
        if conn.dialect.name == "postgresql"
        else "UPDATE oauth_client SET client_info = :info WHERE client_id = :cid"
    )
    conn.execute(statement, {"info": json.dumps(info), "cid": _WEB_CLIENT_ID})
