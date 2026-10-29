"""Persistence for OAuth clients, codes, consents and login tickets (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthLoginTicket,
)
from rdm.infrastructure.db.models import (
    OAuthAuthorizationCodeModel,
    OAuthClientModel,
    OAuthConsentModel,
    OAuthLoginTicketModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    oauth_client_to_domain,
    oauth_code_to_domain,
    oauth_consent_to_domain,
    oauth_login_ticket_to_domain,
)


class OAuthClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(self, client: OAuthClient) -> None:
        existing = await self._s.get(OAuthClientModel, client.client_id)
        if existing is None:
            self._s.add(
                OAuthClientModel(
                    client_id=client.client_id,
                    org_id=client.org_id,
                    client_info=client.client_info,
                    redirect_uris=client.redirect_uris,
                    is_first_party=client.is_first_party,
                    created_at=client.created_at,
                    revoked_at=client.revoked_at,
                )
            )
        else:
            existing.client_info = client.client_info
            existing.redirect_uris = client.redirect_uris
            existing.is_first_party = client.is_first_party
            existing.revoked_at = client.revoked_at

    async def get(self, client_id: str) -> OAuthClient | None:
        row = await self._s.get(OAuthClientModel, client_id)
        if row is None or row.revoked_at is not None:
            return None
        return oauth_client_to_domain(row)


class AuthorizationCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, code: OAuthAuthorizationCode) -> None:
        self._s.add(
            OAuthAuthorizationCodeModel(
                id=code.id,
                code_hash=code.code_hash,
                client_id=code.client_id,
                user_id=code.user_id,
                act_as_user_id=code.act_as_user_id,
                remember=code.remember,
                scopes=list(code.scopes),
                code_challenge=code.code_challenge,
                redirect_uri=code.redirect_uri,
                redirect_uri_explicit=code.redirect_uri_explicit,
                resource=code.resource,
                expires_at=code.expires_at,
                consumed_at=code.consumed_at,
                created_at=code.created_at,
            )
        )

    async def get_by_hash(self, code_hash: str) -> OAuthAuthorizationCode | None:
        stmt = select(OAuthAuthorizationCodeModel).where(
            OAuthAuthorizationCodeModel.code_hash == code_hash
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return oauth_code_to_domain(row) if row else None

    async def mark_consumed(self, code_id: str, when: dt.datetime) -> None:
        await self._s.execute(
            update(OAuthAuthorizationCodeModel)
            .where(OAuthAuthorizationCodeModel.id == code_id)
            .values(consumed_at=when)
        )


class ConsentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, consent: OAuthConsent) -> None:
        self._s.add(
            OAuthConsentModel(
                id=consent.id,
                client_id=consent.client_id,
                consent_key_hash=consent.consent_key_hash,
                authenticating_user_id=consent.authenticating_user_id,
                selectable_user_ids=list(consent.selectable_user_ids),
                remember=consent.remember,
                state=consent.state,
                scopes=list(consent.scopes),
                code_challenge=consent.code_challenge,
                redirect_uri=consent.redirect_uri,
                redirect_uri_explicit=consent.redirect_uri_explicit,
                resource=consent.resource,
                expires_at=consent.expires_at,
                decided_at=consent.decided_at,
                consumed_at=consent.consumed_at,
                created_at=consent.created_at,
            )
        )

    async def get(self, consent_id: str) -> OAuthConsent | None:
        row = await self._s.get(OAuthConsentModel, consent_id)
        return oauth_consent_to_domain(row) if row else None

    async def mark_decided(self, consent_id: str, when: dt.datetime) -> None:
        await self._s.execute(
            update(OAuthConsentModel)
            .where(OAuthConsentModel.id == consent_id)
            .values(decided_at=when, consumed_at=when)
        )


class LoginTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, ticket: OAuthLoginTicket) -> None:
        self._s.add(
            OAuthLoginTicketModel(
                id=ticket.id,
                org_id=ticket.org_id,
                key_hash=ticket.key_hash,
                client_id=ticket.client_id,
                code_challenge=ticket.code_challenge,
                redirect_uri=ticket.redirect_uri,
                redirect_uri_explicit=ticket.redirect_uri_explicit,
                scopes=list(ticket.scopes),
                state=ticket.state,
                resource=ticket.resource,
                expires_at=ticket.expires_at,
                consumed_at=ticket.consumed_at,
                created_at=ticket.created_at,
            )
        )

    async def get_by_hash(self, key_hash: str) -> OAuthLoginTicket | None:
        stmt = select(OAuthLoginTicketModel).where(OAuthLoginTicketModel.key_hash == key_hash)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return oauth_login_ticket_to_domain(row) if row else None

    async def consume(self, ticket_id: str, when: dt.datetime) -> None:
        await self._s.execute(
            update(OAuthLoginTicketModel)
            .where(OAuthLoginTicketModel.id == ticket_id)
            .values(consumed_at=when)
        )
