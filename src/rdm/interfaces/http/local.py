"""Loopback-only owner recovery endpoint (§17).

The deployer runs ``rdm account recover-owner`` on the host; the CLI calls
this endpoint over loopback. Any non-loopback peer gets a 404 so the endpoint
does not advertise its existence. The server itself already refuses to bind
non-loopback addresses (§16.59).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from rdm.application.services import password_tickets
from rdm.domain.constants import DEFAULT_ORG_ID
from rdm.domain.enums import PasswordTicketKind
from rdm.domain.errors import NotFound
from rdm.interfaces.http.container import Container, get_container

router = APIRouter(prefix="/api/v1/local", tags=["local"])

_LOOPBACK_PEERS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _peer_is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else None
    return host in _LOOPBACK_PEERS


@router.post("/owner-recovery")
async def owner_recovery(
    request: Request,
    container: Container = Depends(get_container),
) -> dict:
    if not _peer_is_loopback(request):
        raise NotFound("not found")

    async with container.uow() as uow:
        assert uow.users is not None
        owners = await uow.users.list_org_owners(DEFAULT_ORG_ID)
        if not owners:
            raise NotFound("组织尚无启用状态的 Org Owner")
        owner = owners[0]
        raw = await password_tickets.issue_ticket(
            uow,
            user=owner,
            kind=PasswordTicketKind.bootstrap,
            created_by="local-recovery",
        )
    return {
        "data": {
            "user": {"id": owner.id, "name": owner.name},
            "set_password_url": f"/set-password?ticket={raw}",
            "expires_in_days": 7,
        }
    }
