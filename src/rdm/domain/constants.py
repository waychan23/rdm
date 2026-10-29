"""Process-wide domain constants (§17).

The deployment hosts exactly one organization for now. Everything that is
organization-scoped carries ``org_id``; the default organization is created
at bootstrap with this fixed id so tests, seeds and the CLI can refer to it
without a lookup.
"""

from __future__ import annotations

DEFAULT_ORG_ID = "01J" + "0" * 23
DEFAULT_ORG_NAME = "默认组织"

# First-party browser client seeded at bootstrap (OAuth 2.1, public/PKCE).
# MCP clients still use dynamic client registration (§16.54).
WEB_CLIENT_ID = "rdm-web"

# The org role held by exactly one active human at any time.
ORG_OWNER_ROLE = "org_owner"
