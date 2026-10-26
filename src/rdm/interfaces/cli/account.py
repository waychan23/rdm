"""Offline account recovery commands (direct DB connection).

These escape hatches run while the server is stopped and bypass the API
self-protection rules (architecture §16.55/58): they can reset any human
member's password and rotate the bootstrap owner token. No domain events are
emitted by the offline path.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3
from pathlib import Path

import typer
from sqlalchemy import create_engine, text

from rdm.application.services.member_service import generate_token
from rdm.application.services.passwords import generate_password, hash_password
from rdm.infrastructure.id import new_id

# Python 3.12 deprecates the implicit datetime→str adapter for raw sqlite3.
# These offline statements bind datetimes directly, so register an explicit one.
sqlite3.register_adapter(dt.datetime, lambda v: v.strftime("%Y-%m-%d %H:%M:%S.%f"))


def _db_url(data_dir: Path) -> str:
    return f"sqlite:///{data_dir / 'rdm.db'}"


def _write_secret_file(path: Path, raw: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
    except BaseException:
        os.close(fd)
        raise
    os.chmod(path, 0o600)


def reset_password(
    data_dir: Path,
    *,
    project_key: str = "RDM",
    name: str = "owner",
    new_password: str | None = None,
    password_file: Path | None = None,
) -> str:
    """Reset a human member's password; returns the new plaintext."""
    engine = create_engine(_db_url(data_dir))
    try:
        with engine.begin() as conn:
            member = conn.execute(
                text(
                    "select m.id, m.type, p.owner_member_id from project_member m "
                    "join project p on p.id = m.project_id "
                    "where lower(p.key) = lower(:key) and m.name = :name "
                    "and m.deleted_at is null"
                ),
                {"key": project_key, "name": name},
            ).first()
            if member is None:
                typer.secho(f"member {name!r} not found in project {project_key}", fg="red")
                raise typer.Exit(1)
            member_id, member_type, owner_id = member
            if member_type != "human":
                typer.secho("agents cannot have a console password", fg="red")
                raise typer.Exit(1)
            raw = new_password or generate_password()
            conn.execute(
                text(
                    "update project_member set password_hash = :h, updated_at = :now where id = :id"
                ),
                {"h": hash_password(raw), "now": dt.datetime.now(dt.UTC), "id": member_id},
            )
            # Keep the bootstrap-password file in sync when it is the owner.
            if password_file is not None and member_id == owner_id:
                _write_secret_file(password_file, raw)
    finally:
        engine.dispose()
    return raw


def rotate_bootstrap_token(data_dir: Path, *, keep_old: bool = False) -> str:
    """Issue a fresh bootstrap PAT for the RDM owner and rewrite the file."""
    engine = create_engine(_db_url(data_dir))
    try:
        with engine.begin() as conn:
            project = conn.execute(
                text(
                    "select id, owner_member_id from project "
                    "where lower(key) = 'rdm' and deleted_at is null"
                )
            ).first()
            if project is None or project[1] is None:
                typer.secho("bootstrapped RDM project/owner not found", fg="red")
                raise typer.Exit(1)
            owner_id = project[1]
            raw = generate_token()
            now = dt.datetime.now(dt.UTC)
            conn.execute(
                text(
                    "insert into member_token (id, member_id, token_hash, label, kind, "
                    "scopes, created_at) values (:id, :m, :h, 'bootstrap', 'pat', '[]', :now)"
                ),
                {
                    "id": new_id(),
                    "m": owner_id,
                    "h": hashlib.sha256(raw.encode()).hexdigest(),
                    "now": now,
                },
            )
            if not keep_old:
                conn.execute(
                    text(
                        "update member_token set revoked_at = :now "
                        "where member_id = :m and label = 'bootstrap' and kind = 'pat' "
                        "and revoked_at is null and token_hash != :h"
                    ),
                    {"now": now, "m": owner_id, "h": hashlib.sha256(raw.encode()).hexdigest()},
                )
    finally:
        engine.dispose()
    _write_secret_file(data_dir / "bootstrap-token", raw)
    return raw
