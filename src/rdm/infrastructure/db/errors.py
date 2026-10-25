"""Translate DB integrity errors into domain errors.

SQLite's UNIQUE message names columns rather than the index; Postgres names
the constraint. We match on table/column substrings so both dialects map to
the same domain error. Call around uow.flush(); the failed transaction is
rolled back by the UoW exit, the translated error must not be retried on it.
"""

from __future__ import annotations

from rdm.domain.errors import RdmError, SprintActiveExists, ValidationError


def _text(exc: Exception) -> str:
    orig = getattr(exc, "orig", None)
    return f"{orig} | {exc}" if orig is not None else str(exc)


def translate_integrity(exc: Exception) -> RdmError:
    text = _text(exc)
    if "sprint.project_id" in text or "ux_sprint_one_active_per_project" in text:
        return SprintActiveExists(
            "该项目已有一个 ACTIVE Sprint；请先关闭它再启动新的 Sprint。",
            details={"constraint": "ux_sprint_one_active_per_project"},
        )
    if "sprint_item" in text or "ux_sprint_item" in text:
        return ValidationError(
            "该工作项已在另一个 Sprint 中，一个工作项同一时间只能属于一个 Sprint。",
            details={"constraint": "ux_sprint_item_one_sprint"},
        )
    if "mailbox_member" in text or "ux_mailbox_member" in text:
        return ValidationError(
            "该成员已在此 group 信箱中。",
            details={"constraint": "ux_mailbox_member"},
        )
    if "mailbox.project_id" in text or "ux_mailbox_indiv_owner" in text:
        return ValidationError(
            "该成员的 indiv 信箱已存在。",
            details={"constraint": "ux_mailbox_indiv_owner"},
        )
    return ValidationError(f"数据约束冲突：{text}", details={"raw": text})
