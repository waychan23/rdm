"""OAuth 2.1 dynamic clients, authorization codes and consent requests."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import Base


class OAuthClientModel(Base):
    __tablename__ = "oauth_client"

    client_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Full OAuthClientInformationFull record (contains the plaintext secret).
    client_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAuthorizationCodeModel(Base):
    __tablename__ = "oauth_authorization_code"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    member_id: Mapped[str] = mapped_column(String(32), nullable=False)
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
    session_token_id: Mapped[str] = mapped_column(String(32), nullable=False)
    selectable_member_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
