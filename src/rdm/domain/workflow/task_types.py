"""Task type normalization and per-item subtype lookup."""

from __future__ import annotations

from rdm.domain.entities import TaskFields, WorkItem

# Canonical task type codes live in workflow.json5; these aliases keep old
# clients/tests working for one milestone.
TASK_TYPE_ALIASES = {"qa": "testing", "ux_design": "ui_design"}


def normalize_task_type(value: str | None) -> str:
    task_type = str(value or "other").strip()
    return TASK_TYPE_ALIASES.get(task_type, task_type)


def item_task_type(item: WorkItem) -> str | None:
    if item.kind != "task":
        return None
    if isinstance(item.fields, TaskFields):
        return normalize_task_type(item.fields.task_type)
    return "other"
