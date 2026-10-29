"""OAuth 2.1 clients, authorization codes, consents and login tickets (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import Base


class OAuthClientModel(Base):
    __tablename__ = "oauth_client"

    client_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Full OAuthClientInformationFull record (contains the plaintext secret
    # for DCR clients; the first-party rdm-web client has none).
    client_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_first_party: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAuthorizationCodeModel(Base):
    __tablename__ = "oauth_authorization_code"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Subject is always the authenticated human; act_as selects an agent.
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    act_as_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remember: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthConsentModel(Base):
    __tablename__ = "oauth_consent_request"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # One-shot capability key carried in the SPA URL; only its hash is stored.
    consent_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    authenticating_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    selectable_user_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    remember: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthLoginTicketModel(Base):
    """Parks an /authorize request while the browser authenticates (§17).

    The SPA login form posts the raw key back together with name/password;
    the server then continues the OAuth flow from the stored parameters.
    """

    __tablename__ = "oauth_login_ticket"
    __table_args__ = (Index("ix_oauth_login_ticket_hash", "key_hash"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
