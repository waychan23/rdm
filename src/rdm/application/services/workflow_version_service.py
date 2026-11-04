"""Pin work items to persisted effective workflow definitions (§17.120)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from rdm.domain.entities import WorkflowVersion, WorkItem
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_engine
from rdm.domain.workflow.schema import ResolvedKindWorkflow, StatusFlags
from rdm.domain.workflow.task_types import item_task_type
from rdm.domain.workflow.versioning import (
    canonical_json,
    definition_hash,
    definitions_equal,
    deserialize_definition,
    normalized_subtype,
    serialize_definition,
)
from rdm.infrastructure.db.repositories.workflow_version import WorkflowVersionRepository
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.workflow_versions")


@lru_cache(maxsize=256)
def _deserialize_cached(
    kind: str,
    subtype: str | None,
    schema_version: int,
    payload_json: str,
) -> ResolvedKindWorkflow:
    return deserialize_definition(
        kind,
        subtype,
        json.loads(payload_json),
        schema_version=schema_version,
    )


@dataclass(frozen=True)
class TargetDefinitionPreview:
    """Read-only preview of the definition an item would move to (RDM-147)."""

    def_id: str | None
    version: int
    schema_version: int
    definition_hash: str
    resolved: ResolvedKindWorkflow


class WorkflowVersionService:
    def __init__(
        self,
        uow: SqlAlchemyUnitOfWork,
        current_engine: WorkflowEngine | None = None,
    ) -> None:
        self.uow = uow
        self._current_engine = current_engine

    def _engine(self) -> WorkflowEngine:
        return self._current_engine or load_engine()

    @property
    def _repo(self) -> WorkflowVersionRepository:
        repo = self.uow.workflow_versions
        assert repo is not None
        return repo

    async def ensure(
        self,
        kind: str,
        subtype: str | None,
        *,
        resolved: ResolvedKindWorkflow | None = None,
        created_by: str | None = None,
    ) -> WorkflowVersion:
        """Return the latest matching definition, inserting the next version otherwise."""
        subtype = normalized_subtype(kind, subtype)
        engine = self._engine()
        definition = resolved or engine.resolve(kind, subtype)
        payload = serialize_definition(definition, schema_version=engine.spec.version)
        digest = definition_hash(payload)
        latest = await self._repo.latest(kind, subtype)
        if latest is not None and latest.def_hash == digest:
            if not definitions_equal(latest.definition, payload):
                logger.warning(
                    "workflow definition hash collision for %s/%s; inserting a version",
                    kind,
                    subtype,
                )
            elif latest.config_schema_version == engine.spec.version:
                # config_version (workflow.json5 revision) is informational only;
                # config_schema_version forces a new version when it changes.
                return latest
        version = 1 if latest is None else latest.version + 1
        row = WorkflowVersion(
            id=new_id(),
            kind=kind,
            subtype=subtype,
            version=version,
            def_hash=digest,
            definition=payload,
            config_schema_version=engine.spec.version,
            config_version=engine.spec.revision,
            created_by=created_by,
        )
        await self._repo.add(row)
        return row

    async def resolved_for(self, item: WorkItem) -> ResolvedKindWorkflow:
        engine = await self.engine_for(item)
        return engine.resolve(item.kind, item_task_type(item))

    async def preview_target(
        self, item: WorkItem, engine: WorkflowEngine
    ) -> TargetDefinitionPreview:
        """Compute the definition row an upgrade would land on, without writing.

        Mirrors :meth:`ensure`'s reuse rule: same canonical definition *and*
        same config schema version reuses the latest row; otherwise the next
        version would be inserted.
        """
        kind = item.kind
        task_type = item_task_type(item)
        resolved = engine.resolve(kind, task_type)
        payload = serialize_definition(resolved, schema_version=engine.spec.version)
        digest = definition_hash(payload)
        latest = await self._repo.latest(kind, normalized_subtype(kind, task_type))
        if (
            latest is not None
            and latest.def_hash == digest
            and latest.config_schema_version == engine.spec.version
            and definitions_equal(latest.definition, payload)
        ):
            return TargetDefinitionPreview(
                def_id=latest.id,
                version=latest.version,
                schema_version=latest.config_schema_version,
                definition_hash=digest,
                resolved=resolved,
            )
        return TargetDefinitionPreview(
            def_id=None,
            version=1 if latest is None else latest.version + 1,
            schema_version=engine.spec.version,
            definition_hash=digest,
            resolved=resolved,
        )

    async def engine_for(self, item: WorkItem) -> WorkflowEngine:
        current = self._engine()
        if not item.workflow_def_id:
            return current
        row = await self._repo.get(item.workflow_def_id)
        if row is None:
            logger.warning("missing workflow definition %s for %s", item.workflow_def_id, item.id)
            return current
        pinned = _deserialize_pinned(row)
        key = (row.kind, normalized_subtype(row.kind, row.subtype))
        if key[0] != item.kind:
            logger.warning(
                "workflow definition kind mismatch for %s: %s != %s",
                item.id,
                key[0],
                item.kind,
            )
            return current
        return WorkflowEngine(current.spec, pinned={key: pinned})

    async def engines_for(self, items: Sequence[WorkItem]) -> dict[str, WorkflowEngine]:
        """Batch-load pinned definitions for list/gate callers (no N+1)."""
        current = self._engine()
        rows = await self._repo.get_many(
            [item.workflow_def_id for item in items if item.workflow_def_id]
        )
        engines: dict[str, WorkflowEngine] = {}
        for item in items:
            row = rows.get(item.workflow_def_id) if item.workflow_def_id else None
            if row is None:
                engines[item.id] = current
                continue
            key = (row.kind, normalized_subtype(row.kind, row.subtype))
            if key[0] != item.kind:
                engines[item.id] = current
                continue
            engines[item.id] = WorkflowEngine(current.spec, pinned={key: _deserialize_pinned(row)})
        return engines

    async def terminal_map(self, items: Sequence[WorkItem]) -> dict[str, bool]:
        engines = await self.engines_for(items)
        return {
            item.id: engines[item.id].is_terminal(
                item.kind, item.status, task_type=item_task_type(item)
            )
            for item in items
        }

    async def status_flags_map(self, items: Sequence[WorkItem]) -> dict[str, StatusFlags]:
        """Map each item to its workflow status flags under its pinned flow."""
        engines = await self.engines_for(items)
        flags: dict[str, StatusFlags] = {}
        for item in items:
            resolved = engines[item.id].resolve(item.kind, item_task_type(item))
            flags[item.id] = StatusFlags(
                start=item.status == resolved.initial,
                terminal=item.status in resolved.terminal,
                main_terminal=item.status in resolved.main_terminal,
                side_terminal=item.status in resolved.side_terminal,
            )
        return flags


def _deserialize_pinned(row: WorkflowVersion) -> ResolvedKindWorkflow:
    return _deserialize_cached(
        row.kind,
        normalized_subtype(row.kind, row.subtype),
        row.config_schema_version,
        canonical_json(row.definition),
    )
