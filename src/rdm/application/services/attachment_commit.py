"""Promote editor-pasted images from temp to active when content is saved.

The authoritative reference graph is the saved markdown itself: every
`/api/v1/attachments/{id}/download` URL in a persisted field keeps that
project-scoped attachment alive (docs/architecture.md §17.83). Scanning here
is idempotent and works for create/update/comment/mail/sprint uniformly.

Deliberately depends only on the UoW and a pure domain helper so
WorkItemService can call it without importing AttachmentService (which
imports WorkItemService).
"""

from __future__ import annotations

import datetime as dt

from rdm.domain.attachment_policy import extract_attachment_ids
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


async def commit_inline_images(
    uow: SqlAlchemyUnitOfWork, project_id: str, *texts: str | None
) -> int:
    """Mark referenced temp attachments active; returns the number promoted."""
    ids = extract_attachment_ids(*texts)
    if not ids or uow.attachments is None:
        return 0
    return await uow.attachments.commit_temp(project_id, sorted(ids), dt.datetime.now(dt.UTC))
