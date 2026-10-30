"""Shared pydantic input models for REST routers and MCP tools.

Keep framework-validation here (types, required-ness) and business/cross-kind
validation in WorkItemService (mcp-tools.md §4: wrong-kind fields are a
VALIDATION_ERROR with an actionable message).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from rdm.domain.constants import DEFAULT_PRIORITY, PRIORITY_MAX, PRIORITY_MIN

Kind = Literal["epic", "story", "issue", "task"]
Severity = Literal["blocker", "critical", "major", "minor", "trivial"]


class _Strict(BaseModel):
    model_config = {"extra": "forbid"}


class WorkItemCreateIn(_Strict):
    kind: Kind
    title: str = Field(min_length=1, max_length=300)
    parent: str | None = None
    description_md: str | None = None
    priority: int = Field(default=DEFAULT_PRIORITY, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    planned_start_date: dt.date | None = None
    planned_end_date: dt.date | None = None
    assignee: str | None = None
    # M6 people/optional fields (enabled per workflow; validated in the service)
    participants: list[str] | None = None
    reviewer: list[str] | None = None
    review_content_md: str | None = None
    custom_fields: dict[str, Any] | None = None
    # story
    acceptance_criteria_md: str | None = None
    # issue
    severity: Severity | None = None
    environment: str | None = None
    repro_steps_md: str | None = None
    expected_behavior_md: str | None = None
    actual_behavior_md: str | None = None
    source_story: str | None = None
    # task
    task_type: str | None = None
    est_work_hours: float | None = Field(default=None, ge=0, le=9999.9)
    actual_work_hours: float | None = Field(default=None, ge=0, le=9999.9)
    code_branch: str | None = None


class WorkItemUpdateIn(_Strict):
    row_version: int
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description_md: str | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    planned_start_date: dt.date | None = None
    planned_end_date: dt.date | None = None
    participants: list[str] | None = None
    reviewer: list[str] | None = None
    review_content_md: str | None = None
    custom_fields: dict[str, Any] | None = None
    # story
    acceptance_criteria_md: str | None = None
    # issue
    severity: Severity | None = None
    environment: str | None = None
    repro_steps_md: str | None = None
    expected_behavior_md: str | None = None
    actual_behavior_md: str | None = None
    source_story: str | None = None
    # task
    task_type: str | None = None
    est_work_hours: float | None = Field(default=None, ge=0, le=9999.9)
    actual_work_hours: float | None = Field(default=None, ge=0, le=9999.9)
    code_branch: str | None = None


class ReparentIn(_Strict):
    parent: str | None = None
    row_version: int


class WorkItemAssignIn(_Strict):
    # M1 supports assignee only (no reviewer/watcher tables, §16.22).
    member: str = Field(min_length=1)


class TransitionIn(_Strict):
    to: str = Field(min_length=1)
    row_version: int
    reason: str | None = None


class StepStartIn(_Strict):
    row_version: int
    executors: list[str] | None = None
    note_md: str | None = None
    attachment_ids: list[str] | None = None


class StepExecuteIn(_Strict):
    note_md: str | None = None
    attachment_ids: list[str] | None = None


class StepCancelIn(_Strict):
    row_version: int
    reason: str | None = None


class StepReassignIn(_Strict):
    row_version: int
    executors: list[str]


class StepRetryIn(_Strict):
    row_version: int
