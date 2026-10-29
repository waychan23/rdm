"""First-start bootstrap: the default organization and its owner (§17).

No files are written any more. The plaintext bootstrap token is embedded in a
one-shot URL logged once at startup; the deployer hands that URL to the real
Org Owner, who sets a password. The bootstrap PAT and password file are gone.
"""

from __future__ import annotations

import datetime as dt
import logging

from rdm.application.services.password_tickets import issue_ticket
from rdm.domain.constants import (
    DEFAULT_ORG_ID,
    DEFAULT_ORG_NAME,
    SCOPE_WEB,
    WEB_CLIENT_ID,
)
from rdm.domain.entities import OAuthClient, Organization, User
from rdm.domain.enums import PasswordTicketKind
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.bootstrap")

OWNER_NAME = "owner"


async def is_bootstrapped(uow: SqlAlchemyUnitOfWork) -> bool:
    assert uow.organizations is not None
    return (await uow.organizations.get(DEFAULT_ORG_ID)) is not None


def web_client_redirect_uris(base_url: str) -> list[str]:
    """Loopback redirect URIs for the first-party browser client (§17)."""
    uris = [
        f"{base_url}/auth/callback",
    ]
    # Accept both spellings of loopback for the same bound port.
    if "://127.0.0.1" in base_url:
        uris.append(base_url.replace("://127.0.0.1", "://localhost") + "/auth/callback")
    elif "://localhost" in base_url:
        uris.append(base_url.replace("://localhost", "://127.0.0.1") + "/auth/callback")
    # Vite dev server.
    uris += [
        "http://127.0.0.1:5173/auth/callback",
        "http://localhost:5173/auth/callback",
    ]
    return uris


def seed_web_client(base_url: str, extra_redirect_uris: list[str] | None = None) -> OAuthClient:
    redirect_uris = web_client_redirect_uris(base_url)
    for uri in extra_redirect_uris or []:
        if uri not in redirect_uris:
            redirect_uris.append(uri)
    return OAuthClient(
        client_id=WEB_CLIENT_ID,
        org_id=DEFAULT_ORG_ID,
        is_first_party=True,
        redirect_uris=redirect_uris,
        client_info={
            "client_id": WEB_CLIENT_ID,
            "client_name": "rdm Web",
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            # The browser audience is REST, not MCP (§17.79).
            "scope": SCOPE_WEB,
        },
        created_at=dt.datetime.now(dt.UTC),
    )


async def bootstrap_if_empty(
    uow: SqlAlchemyUnitOfWork,
    *,
    base_url: str,
    extra_redirect_uris: list[str] | None = None,
) -> str | None:
    """Create the organization, owner, web client and bootstrap ticket.

    Returns the raw bootstrap ticket when bootstrap happened, else None.
    """
    if await is_bootstrapped(uow):
        return None

    now = dt.datetime.now(dt.UTC)
    org = Organization(id=DEFAULT_ORG_ID, name=DEFAULT_ORG_NAME, created_at=now)
    owner = User(
        id=new_id(),
        org_id=DEFAULT_ORG_ID,
        type="human",
        name=OWNER_NAME,
        org_roles=["org_owner"],
        # No password yet: the bootstrap ticket is the only way in.
        password_hash=None,
        must_reset_password=True,
        created_by="bootstrap",
        created_at=now,
    )

    assert uow.organizations and uow.users and uow.oauth_clients and uow.events
    await uow.organizations.add(org)
    await uow.users.add(owner)
    await uow.oauth_clients.upsert(seed_web_client(base_url, extra_redirect_uris))
    await uow.flush()

    raw_ticket = await issue_ticket(
        uow,
        user=owner,
        kind=PasswordTicketKind.bootstrap,
        created_by="bootstrap",
    )

    seq = await uow.allocate_event_seq(DEFAULT_ORG_ID)
    await uow.events.append(
        org_id=DEFAULT_ORG_ID,
        project_id=None,
        seq=seq,
        aggregate_type="organization",
        aggregate_id=DEFAULT_ORG_ID,
        aggregate_version=0,
        event_type=EventType.ORG_BOOTSTRAPPED,
        actor_user_id=owner.id,
        payload={"snapshot": {"id": org.id, "name": org.name, "owner_id": owner.id}},
    )
    return raw_ticket
