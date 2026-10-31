"""One-shot password-setting tickets (§17).

Three sources reuse the same mechanism with different lifetimes:
- ``bootstrap``: first start / loopback owner recovery (7 days);
- ``reset``: a user-manager generates a link for the holder (24 hours);
- ``must_reset``: a login attempt by a user with a temporary password (15 min).
"""

from __future__ import annotations

import datetime as dt

from rdm.application.services.tokens import generate_token, hash_token
from rdm.domain.entities import PasswordTicket, User
from rdm.domain.enums import PasswordTicketKind
from rdm.domain.errors import ValidationError
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

BOOTSTRAP_TTL = dt.timedelta(days=7)
RESET_TTL = dt.timedelta(hours=24)
MUST_RESET_TTL = dt.timedelta(minutes=15)

_TTLS = {
    PasswordTicketKind.bootstrap.value: BOOTSTRAP_TTL,
    PasswordTicketKind.reset.value: RESET_TTL,
    PasswordTicketKind.must_reset.value: MUST_RESET_TTL,
}


async def issue_ticket(
    uow: SqlAlchemyUnitOfWork,
    *,
    user: User,
    kind: PasswordTicketKind,
    created_by: str | None,
) -> str:
    """Create a ticket, invalidating older unused tickets of the same kind."""
    assert uow.password_tickets is not None
    now = dt.datetime.now(dt.UTC)
    await uow.password_tickets.invalidate_kind(user.id, kind.value, now)
    raw = generate_token()
    ticket = PasswordTicket(
        id=new_id(),
        org_id=user.org_id,
        user_id=user.id,
        kind=kind.value,
        token_hash=hash_token(raw),
        expires_at=now + _TTLS[kind.value],
        created_by=created_by,
        created_at=now,
    )
    await uow.password_tickets.add(ticket)
    return raw


async def resolve_ticket(
    uow: SqlAlchemyUnitOfWork,
    raw: str,
    *,
    kinds: set[str] | None = None,
) -> PasswordTicket:
    assert uow.password_tickets is not None
    ticket = await uow.password_tickets.get_by_hash(hash_token(raw))
    if ticket is None or not ticket.is_usable:
        raise ValidationError(
            tr("auth.ticket_invalid", default="链接无效或已过期"), details={"field": "ticket"}
        )
    if kinds is not None and ticket.kind not in kinds:
        raise ValidationError(
            tr("auth.ticket_kind_mismatch", default="链接类型不匹配"), details={"field": "ticket"}
        )
    return ticket


async def inspect_ticket(uow: SqlAlchemyUnitOfWork, raw: str) -> PasswordTicket | None:
    """Look up a ticket without consuming or rejecting it.

    The set-password page evaluates the link as soon as it opens, so it needs
    the row (and its expired/consumed state) instead of a ValidationError.
    """
    assert uow.password_tickets is not None
    return await uow.password_tickets.get_by_hash(hash_token(raw))


async def consume_ticket(uow: SqlAlchemyUnitOfWork, ticket: PasswordTicket) -> None:
    assert uow.password_tickets is not None
    await uow.password_tickets.consume(ticket.id, dt.datetime.now(dt.UTC))
