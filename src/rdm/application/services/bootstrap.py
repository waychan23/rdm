"""First-start bootstrap: default project RDM + owner member + admin token.

Architecture §6 / decisions §16.1/55: the plaintext bootstrap token and the
initial owner password are each written once to data-dir (mode 0600).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from rdm.application.services.member_service import generate_token, hash_token
from rdm.application.services.passwords import generate_password, hash_password
from rdm.domain.entities import Member, MemberToken, Project
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.bootstrap")

DEFAULT_PROJECT_KEY = "RDM"
DEFAULT_PROJECT_NAME = "默认项目"
OWNER_NAME = "owner"
BOOTSTRAP_LABEL = "bootstrap"


async def is_bootstrapped(uow: SqlAlchemyUnitOfWork) -> bool:
    assert uow.projects is not None
    return bool(await uow.projects.list_all())


async def bootstrap_if_empty(
    uow: SqlAlchemyUnitOfWork, token_file: Path, password_file: Path
) -> str | None:
    """Create default project/owner/token/password when the DB is empty.

    Returns the plaintext token when bootstrap happened, else None. The
    caller logs the file paths once; both files are mode 0600.
    """
    if await is_bootstrapped(uow):
        return None

    project = Project(id=new_id(), key=DEFAULT_PROJECT_KEY, name=DEFAULT_PROJECT_NAME)
    raw_password = generate_password()
    owner = Member(
        id=new_id(),
        project_id=project.id,
        type="human",
        name=OWNER_NAME,
        roles=["project_owner"],
        accept_kinds=[],
        password_hash=hash_password(raw_password),
        created_by="bootstrap",
    )
    project.owner_member_id = owner.id

    raw = generate_token()
    token = MemberToken(
        id=new_id(),
        member_id=owner.id,
        token_hash=hash_token(raw),
        label=BOOTSTRAP_LABEL,
    )

    assert uow.projects and uow.members and uow.tokens and uow.events
    session = uow.session
    assert session is not None
    await uow.projects.add(project)
    await uow.members.add(owner)
    await uow.tokens.add(token)
    await session.flush()

    # Implicit indiv mailbox (architecture §16.27).
    from rdm.application.services.mailbox_service import MailboxService

    await MailboxService(uow).ensure_indiv(owner)
    seq = await uow.allocate_event_seq(project.id)
    await uow.events.append(
        project_id=project.id,
        seq=seq,
        aggregate_type="project",
        aggregate_id=project.id,
        aggregate_version=0,
        event_type=EventType.PROJECT_CREATED,
        actor_member_id=owner.id,
        payload={"snapshot": {"id": project.id, "key": project.key, "name": project.name}},
    )

    _write_secret_file(token_file, raw)
    _write_secret_file(password_file, raw_password)
    return raw


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
