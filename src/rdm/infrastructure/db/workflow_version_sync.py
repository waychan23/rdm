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
from rdm.domain.workflow.loader import engine_from_text, load_spec
from rdm.domain.workflow.task_types import normalize_task_type
from rdm.domain.workflow.versioning import (
    definition_hash,
    definitions_equal,
    iter_effective_definitions,
    normalized_subtype,
    serialize_definition,
)
from rdm.infrastructure.db.models import (
    ProjectModel,
    WorkflowConfigModel,
    WorkflowConfigVersionModel,
    WorkItemModel,
    WorkItemTaskModel,
)
from rdm.infrastructure.db.models.workitem import WorkItemWorkflowVersionModel
from rdm.infrastructure.id import new_id


@dataclass
class WorkflowSyncReport:
    seeded: list[str] = field(default_factory=list)
    bound_items: int = 0
    config_snapshots: int = 0
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

            if {
                "workflow_config_key",
                "workflow_config_version",
                "workflow_config_version_id",
            } <= columns:
                report.config_snapshots = _backfill_config_snapshots(session)
    finally:
        db.dispose()
    return report


def _backfill_config_snapshots(session: Session) -> int:
    """Fill config provenance for items pinned before RDM-147.

    Provenance was never stored, but the pinned definition is a content hash of
    the effective workflow; rebuilding each stored config version's effective
    definition lets us match it back. Matching never guesses across a real
    definition change: when nothing matches, the columns stay NULL.
    """
    rows = session.execute(
        select(
            WorkItemModel.id,
            WorkItemModel.project_id,
            WorkItemModel.created_at,
            WorkItemModel.workflow_def_id,
            WorkItemTaskModel.task_type,
        )
        .outerjoin(
            WorkItemTaskModel,
            WorkItemTaskModel.work_item_id == WorkItemModel.id,
        )
        .where(
            WorkItemModel.deleted_at.is_(None),
            WorkItemModel.workflow_def_id.is_not(None),
            WorkItemModel.workflow_config_key.is_(None),
        )
    ).all()
    if not rows:
        return 0

    pinned_ids = {row[3] for row in rows if row[3]}
    pinned = {
        row.id: row
        for row in session.execute(
            select(WorkItemWorkflowVersionModel).where(
                WorkItemWorkflowVersionModel.id.in_(pinned_ids)
            )
        ).scalars()
    }
    config_versions = session.execute(
        select(WorkflowConfigVersionModel, WorkflowConfigModel).join(
            WorkflowConfigModel,
            WorkflowConfigModel.id == WorkflowConfigVersionModel.config_id,
        )
    ).all()
    project_selection = dict(
        session.execute(select(ProjectModel.id, ProjectModel.workflow_config_version_id)).all()
    )

    engines: dict[str, WorkflowEngine | None] = {}
    matches_by_definition: dict[
        str, list[tuple[WorkflowConfigVersionModel, WorkflowConfigModel]]
    ] = {}
    updated = 0
    for item_id, project_id, created_at, def_id, _task_type in rows:
        row = pinned.get(def_id) if def_id else None
        if row is None:
            continue
        matches = matches_by_definition.get(def_id or "")
        if matches is None:
            matches = _matching_config_versions(row, config_versions, engines)
            matches_by_definition[def_id or ""] = matches
        if not matches:
            # Custom config versions are immutable and never deleted, so an
            # unmatched pinned definition can only descend from the packaged
            # default (projects without a config selection, including items
            # created before configs were imported). Record the key without
            # inventing a config version number.
            session.execute(
                update(WorkItemModel)
                .where(WorkItemModel.id == item_id)
                .values(workflow_config_key="default")
            )
            updated += 1
            continue

        # The project's current selection is the most trustworthy tie-breaker
        # when the definition is shared by several configs (forks).
        selected_id = project_selection.get(project_id)
        chosen = next((pair for pair in matches if pair[0].id == selected_id), None)
        if chosen is None:
            cutoff = _naive(created_at)
            eligible = [
                pair for pair in matches if cutoff is None or _naive(pair[0].created_at) <= cutoff
            ]
            chosen = max(
                eligible or matches,
                key=lambda pair: (
                    _naive(pair[0].created_at) or dt.datetime.min,
                    pair[0].version,
                    pair[1].key,
                ),
            )
        version, config = chosen
        session.execute(
            update(WorkItemModel)
            .where(WorkItemModel.id == item_id)
            .values(
                workflow_config_key=config.key,
                workflow_config_version=version.version,
                workflow_config_version_id=version.id,
            )
        )
        updated += 1
    return updated


def _matching_config_versions(
    row: WorkItemWorkflowVersionModel,
    config_versions: list[tuple[WorkflowConfigVersionModel, WorkflowConfigModel]],
    engines: dict[str, WorkflowEngine | None],
) -> list[tuple[WorkflowConfigVersionModel, WorkflowConfigModel]]:
    candidates = [
        (version, config)
        for version, config in config_versions
        if version.schema_version == row.config_schema_version
        and version.revision == row.config_version
    ]
    if not candidates:
        # Old snapshots may predate the imported config revision bookkeeping;
        # fall back to the schema-version match and let the definition hash
        # decide.
        candidates = [
            (version, config)
            for version, config in config_versions
            if version.schema_version == row.config_schema_version
        ]

    task_type = (row.subtype or None) if row.kind == "task" else None
    matches: list[tuple[WorkflowConfigVersionModel, WorkflowConfigModel]] = []
    for version, config in candidates:
        if version.id not in engines:
            try:
                engines[version.id] = engine_from_text(version.content_text)
            except Exception:  # noqa: BLE001 - broken historical rows are skipped
                engines[version.id] = None
        engine = engines[version.id]
        if engine is None:
            continue
        try:
            resolved = engine.resolve(row.kind, task_type)
            payload = serialize_definition(resolved, schema_version=engine.spec.version)
        except Exception:  # noqa: BLE001 - broken historical rows are skipped
            continue
        if definition_hash(payload) == row.def_hash and definitions_equal(row.definition, payload):
            matches.append((version, config))
    return matches


def _naive(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


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
