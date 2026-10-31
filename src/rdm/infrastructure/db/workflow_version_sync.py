"""Seed effective workflow definitions and pin legacy items after upgrade.

Runs synchronously from ``run_upgrade`` because that hook is shared by
``rdm init``/``rdm serve``/``rdm db upgrade`` and by the async pytest fixture.
Migrations stay pure DDL; this module is the only place that reads the packaged
workflow definition during an upgrade (§17.120).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.orm import Session

from rdm.config import Settings
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_spec
from rdm.domain.workflow.task_types import normalize_task_type
from rdm.domain.workflow.versioning import (
    definition_hash,
    definitions_equal,
    iter_effective_definitions,
    normalized_subtype,
    serialize_definition,
)
from rdm.infrastructure.db.models import WorkItemModel, WorkItemTaskModel
from rdm.infrastructure.db.models.workitem import WorkItemWorkflowVersionModel
from rdm.infrastructure.id import new_id


@dataclass
class WorkflowSyncReport:
    seeded: list[str] = field(default_factory=list)
    bound_items: int = 0
    skipped: list[str] = field(default_factory=list)


def sync_workflow_versions(settings: Settings) -> WorkflowSyncReport:
    """Idempotently materialize current definitions and pin unpinned items."""
    report = WorkflowSyncReport()
    spec = load_spec()
    engine = WorkflowEngine(spec)
    db = create_engine(settings.db_sync_url)
    try:
        with Session(db) as session, session.begin():
            tables = set(inspect(session.connection()).get_table_names())
            if "work_item_workflow_version" not in tables:
                report.skipped.append("work_item_workflow_version 表不存在，跳过")
                return report
            columns = {
                column["name"] for column in inspect(session.connection()).get_columns("work_item")
            }
            if "workflow_def_id" not in columns:
                report.skipped.append("work_item.workflow_def_id 列不存在，跳过")
                return report

            for kind, subtype, payload in iter_effective_definitions(spec):
                row, created = _ensure(session, kind, subtype, payload, spec.version, spec.revision)
                if created:
                    report.seeded.append(f"{kind}/{subtype or '-'} v{row.version}")

            rows = session.execute(
                select(WorkItemModel.id, WorkItemModel.kind, WorkItemTaskModel.task_type)
                .outerjoin(
                    WorkItemTaskModel,
                    WorkItemTaskModel.work_item_id == WorkItemModel.id,
                )
                .where(
                    WorkItemModel.workflow_def_id.is_(None),
                    WorkItemModel.deleted_at.is_(None),
                )
            ).all()

            groups: dict[tuple[str, str | None], list[str]] = {}
            for item_id, kind, task_type in rows:
                subtype = (
                    normalized_subtype(kind, normalize_task_type(task_type))
                    if kind == "task"
                    else None
                )
                groups.setdefault((kind, subtype), []).append(item_id)

            for (kind, subtype), item_ids in groups.items():
                try:
                    resolved = engine.resolve(kind, subtype)
                except Exception as exc:  # noqa: BLE001 - report and keep going
                    report.skipped.append(f"{kind}/{subtype or '-'}: {exc}")
                    continue
                row, created = _ensure(
                    session,
                    kind,
                    subtype,
                    serialize_definition(resolved, schema_version=spec.version),
                    spec.version,
                    spec.revision,
                )
                if created:
                    report.seeded.append(f"{kind}/{subtype or '-'} v{row.version}")
                result = session.execute(
                    update(WorkItemModel)
                    .where(WorkItemModel.id.in_(item_ids))
                    .values(
                        workflow_def_id=row.id,
                        workflow_version=row.version,
                    )
                )
                report.bound_items += result.rowcount or 0
    finally:
        db.dispose()
    return report


def _ensure(
    session: Session,
    kind: str,
    subtype: str | None,
    payload: dict,
    config_schema_version: int,
    config_version: int,
) -> tuple[WorkItemWorkflowVersionModel, bool]:
    stored_subtype = subtype or ""
    digest = definition_hash(payload)
    latest = session.execute(
        select(WorkItemWorkflowVersionModel)
        .where(
            WorkItemWorkflowVersionModel.kind == kind,
            WorkItemWorkflowVersionModel.subtype == stored_subtype,
        )
        .order_by(WorkItemWorkflowVersionModel.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if (
        latest is not None
        and latest.def_hash == digest
        and latest.config_schema_version == config_schema_version
        and definitions_equal(latest.definition, payload)
    ):
        return latest, False
    version = 1 if latest is None else latest.version + 1
    row = WorkItemWorkflowVersionModel(
        id=new_id(),
        kind=kind,
        subtype=stored_subtype,
        version=version,
        def_hash=digest,
        definition=payload,
        config_schema_version=config_schema_version,
        config_version=config_version,
        created_at=dt.datetime.now(dt.UTC),
    )
    session.add(row)
    session.flush()
    return row, True
