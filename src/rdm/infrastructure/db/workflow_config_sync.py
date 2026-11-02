"""Import ``workflow-configs/*.json5`` into the database at startup (RDM-84).

Runs synchronously from ``run_upgrade`` (shared by ``rdm init`` / ``rdm serve``
/ ``rdm db upgrade``), after migrations. Each file becomes a *builtin* config:
it can be selected by projects and forked in the web UI, but not edited there.
A changed ``(version, revision)`` pair is imported as a new active version;
re-importing the same pair is idempotent.

Packaged configs are canonical for their key: an upgraded bundled file is
imported on the next startup even when the data-dir copy is stale, and the
copy is refreshed so operators inspect the content that was imported.

Files must use the newest schema version. A stale schema or malformed document
fails startup instead of silently serving a half-imported config set.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.orm import Session

from rdm.config import Settings
from rdm.domain.workflow.config import WorkflowConfigDocument, parse_config_document
from rdm.domain.workflow.versioning import definition_hash
from rdm.infrastructure.db.models import WorkflowConfigModel, WorkflowConfigVersionModel
from rdm.infrastructure.id import new_id


@dataclass
class WorkflowConfigSyncReport:
    imported: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    activated: list[str] = field(default_factory=list)
    seeded_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    shadowed_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def sync_workflow_configs(settings: Settings) -> WorkflowConfigSyncReport:
    """Sync packaged builtins, then import every ``*.json5``.

    Packaged configs are canonical for their key: changing a bundled file and
    restarting appends a new version even when the data-dir copy is stale. The
    data-dir copy is refreshed from the package so operators inspect the same
    content the server imports.
    """
    report = WorkflowConfigSyncReport()
    directory = settings.workflow_configs_dir
    package_dir = _packaged_config_dir()
    packaged = _parse_packaged(package_dir, report)
    _seed_packaged_configs(directory, package_dir, report)

    documents = _read_documents(directory, report, packaged_keys=set(packaged))
    documents.extend(packaged.values())
    if not documents:
        return report

    db = create_engine(settings.db_sync_url)
    try:
        with Session(db) as session, session.begin():
            tables = set(inspect(session.connection()).get_table_names())
            if "workflow_config" not in tables:
                report.errors.append("workflow_config 表不存在，跳过工作流配置入库")
                return report
            for document in documents:
                try:
                    _upsert_document(session, document, report)
                except ValueError as exc:
                    report.errors.append(f"{document.key}: {exc}")
                    raise
    finally:
        db.dispose()
    return report


def _packaged_config_dir() -> Traversable:
    return files("rdm.resources").joinpath("workflow-configs")


def _parse_packaged(
    package: Traversable, report: WorkflowConfigSyncReport
) -> dict[str, WorkflowConfigDocument]:
    documents: dict[str, WorkflowConfigDocument] = {}
    sources: dict[str, str] = {}
    for entry in sorted(package.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".json5"):
            continue
        text = entry.read_text(encoding="utf-8")
        try:
            document = parse_config_document(text)
        except ValueError as exc:
            report.errors.append(f"{entry.name}: {exc}")
            raise ValueError(f"{entry.name}: {exc}") from exc
        if document.key in documents:
            raise ValueError(
                f"{entry.name}: 工作流 key {document.key!r} 与 {sources[document.key]} 重复"
            )
        documents[document.key] = document
        sources[document.key] = entry.name
    return documents


def _seed_packaged_configs(
    directory: Path, package: Traversable, report: WorkflowConfigSyncReport
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for entry in package.iterdir():
        if not entry.name.endswith(".json5"):
            continue
        text = entry.read_text(encoding="utf-8")
        target = directory / entry.name
        if target.exists():
            if target.read_text(encoding="utf-8") == text:
                continue
            # Builtin keys are canonical in the package; refresh the copy so
            # the data dir never shows a stale definition (RDM-111).
            target.write_text(text, encoding="utf-8")
            report.updated_files.append(entry.name)
            continue
        target.write_text(text, encoding="utf-8")
        report.seeded_files.append(entry.name)


def _read_documents(
    directory: Path,
    report: WorkflowConfigSyncReport,
    *,
    packaged_keys: set[str],
) -> list[WorkflowConfigDocument]:
    documents: list[WorkflowConfigDocument] = []
    seen: dict[str, Path] = {}
    for path in sorted(directory.glob("*.json5")):
        text = path.read_text(encoding="utf-8")
        try:
            document = parse_config_document(text)
        except ValueError as exc:
            report.errors.append(f"{path.name}: {exc}")
            raise ValueError(f"{path.name}: {exc}") from exc
        if document.key in packaged_keys:
            # The packaged definition wins; keep the data-dir file only as a
            # refreshed copy (it may lag if the package was upgraded).
            report.shadowed_files.append(path.name)
            continue
        if document.key in seen:
            raise ValueError(
                f"{path.name}: 工作流 key {document.key!r} 与 {seen[document.key].name} 重复"
            )
        seen[document.key] = path
        documents.append(document)
    return documents


def _upsert_document(
    session: Session,
    document: WorkflowConfigDocument,
    report: WorkflowConfigSyncReport,
) -> None:
    config_row = session.execute(
        select(WorkflowConfigModel).where(WorkflowConfigModel.key == document.key)
    ).scalar_one_or_none()

    if config_row is not None and not config_row.is_builtin:
        raise ValueError(
            f"key {document.key!r} 已存在非内置工作流配置；内置文件不能覆盖它，"
            "请改用其他 key 或先删除/改名 web 创建的配置。"
        )

    digest = definition_hash(document.raw)
    if config_row is None:
        config_row = WorkflowConfigModel(
            id=new_id(),
            key=document.key,
            name=document.name,
            is_builtin=True,
            enabled=True,
            created_at=dt.datetime.now(dt.UTC),
        )
        session.add(config_row)
        session.flush()

    existing = list(
        session.execute(
            select(WorkflowConfigVersionModel).where(
                WorkflowConfigVersionModel.config_id == config_row.id,
                WorkflowConfigVersionModel.schema_version == document.schema_version,
                WorkflowConfigVersionModel.revision == document.revision,
            )
        ).scalars()
    )
    if existing:
        match = next((row for row in existing if row.content_hash == digest), None)
        if match is None:
            raise ValueError(
                f"{document.key!r} 的 version={document.schema_version} "
                f"revision={document.revision} 已在库中，但内容不同；"
                "请先提升文件 revision 再启动。"
            )
        if not match.is_active:
            newer = session.execute(
                select(WorkflowConfigVersionModel.version).where(
                    WorkflowConfigVersionModel.config_id == config_row.id,
                    WorkflowConfigVersionModel.version > match.version,
                )
            ).first()
            if newer is not None:
                raise ValueError(
                    f"{document.key!r} 的文件 revision={document.revision} 对应旧版本 "
                    f"v{match.version}，但库中已有更新版本 v{newer[0]}；"
                    "请恢复最新文件内容或提升 revision。"
                )
            _activate(session, config_row.id, match.id)
            report.activated.append(f"{document.key} v{match.version}")
        report.unchanged.append(f"{document.key} v{match.version}")
        return

    next_version = (
        session.execute(
            select(WorkflowConfigVersionModel.version)
            .where(WorkflowConfigVersionModel.config_id == config_row.id)
            .order_by(WorkflowConfigVersionModel.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        or 0
    ) + 1
    previous = session.execute(
        select(WorkflowConfigVersionModel).where(
            WorkflowConfigVersionModel.config_id == config_row.id,
            WorkflowConfigVersionModel.is_active.is_(True),
        )
    ).scalar_one_or_none()
    row = WorkflowConfigVersionModel(
        id=new_id(),
        config_id=config_row.id,
        version=next_version,
        schema_version=document.schema_version,
        revision=document.revision,
        content_text=_document_text(document),
        content=dict(document.raw),
        content_hash=digest,
        source_version_id=previous.id if previous is not None else None,
        is_active=False,
        created_at=dt.datetime.now(dt.UTC),
    )
    session.add(row)
    session.flush()
    _activate(session, config_row.id, row.id)
    config_row.name = document.name
    report.imported.append(f"{document.key} v{next_version}")


def _activate(session: Session, config_id: str, version_id: str) -> None:
    session.execute(
        update(WorkflowConfigVersionModel)
        .where(
            WorkflowConfigVersionModel.config_id == config_id,
            WorkflowConfigVersionModel.is_active.is_(True),
        )
        .values(is_active=False)
    )
    session.execute(
        update(WorkflowConfigVersionModel)
        .where(WorkflowConfigVersionModel.id == version_id)
        .values(is_active=True)
    )
    session.execute(
        update(WorkflowConfigModel)
        .where(WorkflowConfigModel.id == config_id)
        .values(current_version_id=version_id, updated_at=dt.datetime.now(dt.UTC))
    )


def _document_text(document: WorkflowConfigDocument) -> str:
    return document.text


__all__ = [
    "WorkflowConfigSyncReport",
    "sync_workflow_configs",
]
