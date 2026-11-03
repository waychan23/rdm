"""organization, users, user_token and password_set_token tables (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class OrganizationModel(Base):
    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Org-wide event sequence: org-level events have no project (§17).
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailSettingsModel(Base):
    """One outbound SMTP configuration per organization (RDM-122)."""

    __tablename__ = "email_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(
        Integer, nullable=False, default=587, server_default="587"
    )
    smtp_security: Mapped[str] = mapped_column(
        String(10), nullable=False, default="starttls", server_default="starttls"
    )
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "smtp_security in ('none', 'starttls', 'ssl')",
            name="ck_email_settings_security",
        ),
        Index("ux_email_settings_org", "org_id", unique=True),
    )


class UserModel(AuditMixin, SoftDeleteMixin, Base):
    """Human and agent identities owned by the organization (§17).

    Replaces the old project-scoped ``project_member`` table: identity no
    longer belongs to a project. Project roles live on ProjectMemberModel.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Presentation-only; NULL means "fall back to name" (§17.116).
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Self FK: humans have NULL; agents must point at their human manager.
    manager_user_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    # org_owner / user_manager / project_director (humans only).
    org_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    accept_kinds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notify_webhook: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notify_webhook_format: Mapped[str] = mapped_column(
        String(10), nullable=False, default="generic", server_default="generic"
    )
    # Per-type in-app notification switches (§17 M7); missing key = enabled.
    notification_prefs: Mapped[dict[str, bool]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    # argon2id password hash for console login; agents always have NULL (§16.55).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "type = 'human' OR manager_user_id IS NOT NULL",
            name="agent_requires_manager",
        ),
        Index(
            "ux_users_org_name_lower",
            "org_id",
            text("lower(name)"),
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_users_org_type", "org_id", "type"),
        Index("ix_users_manager", "manager_user_id"),
    )


class UserTokenModel(Base):
    """Credentials are never soft-deleted; revocation sets revoked_at (§3.2).

    One table for every credential kind (§16.53/§17): personal access tokens
    and OAuth access/refresh tokens. All are opaque random strings stored only
    as sha256 hashes. ``user_id`` is always the owning human; ``act_as_user_id``
    selects an agent identity for that credential.
    """

    __tablename__ = "user_token"
    __table_args__ = (
        CheckConstraint(
            "kind in ('pat', 'oauth_access', 'oauth_refresh')",
            name="ck_user_token_kind",
        ),
        Index("ix_user_token_user_kind", "user_id", "kind"),
        Index("ix_user_token_family", "family_id"),
        Index("ix_user_token_act_as", "act_as_user_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    act_as_user_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pat", server_default="pat"
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    absolute_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    remember: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    family_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordTicketModel(Base):
    """One-shot bootstrap / reset / forced-reset password tickets (§17)."""

    __tablename__ = "password_set_token"
    __table_args__ = (
        CheckConstraint(
            "kind in ('bootstrap', 'reset', 'must_reset')",
            name="ck_password_set_token_kind",
        ),
        Index("ix_password_set_token_user_kind", "user_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
