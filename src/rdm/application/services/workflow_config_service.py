"""Workflow config registry and project-level engine resolution (RDM-84).

Two responsibilities:

* manage selectable configs — list, fork a builtin into an editable config,
  save a new version, enable/disable — with lineage recorded on every version;
* resolve the engine a project runs on. Projects store a specific version id,
  so later edits never mutate the workflow of an existing project's items.
  ``NULL`` keeps the historical behavior: the packaged default.

Version documents are immutable; :func:`engine_from_text` caches engines by
source text, which is safe because a version row never changes after insert.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from rdm.application import security
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, WorkflowConfig, WorkflowConfigVersion
from rdm.domain.errors import ConflictVersion, NotFound, ValidationError
from rdm.domain.workflow.config import (
    WorkflowConfigDocument,
    WorkflowConfigDocumentError,
    parse_config_document,
    validate_config_key,
    validate_config_name,
)
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import engine_from_text, load_engine
from rdm.domain.workflow.versioning import definition_hash
from rdm.i18n import tr
from rdm.infrastructure.db.repositories.workflow_config import WorkflowConfigRepository
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.workflow_configs")


@dataclass(frozen=True)
class WorkflowConfigView:
    config: WorkflowConfig
    active_version: WorkflowConfigVersion | None
    version_count: int


def _not_found(key: str) -> NotFound:
    return NotFound(
        tr("workflow_config.not_found", default="工作流配置 {key} 不存在", key=key),
        details={"key": key},
    )


def _version_not_found(version_id: str) -> NotFound:
    return NotFound(
        tr(
            "workflow_config.version_not_found",
            default="工作流配置版本不存在",
        ),
        details={"version_id": version_id},
    )


class WorkflowConfigService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    @property
    def _repo(self) -> WorkflowConfigRepository:
        repo = self.uow.workflow_configs
        assert repo is not None
        return repo

    # --- reads ------------------------------------------------------------

    async def list_configs(self, *, enabled_only: bool = False) -> list[WorkflowConfigView]:
        views: list[WorkflowConfigView] = []
        for config in await self._repo.list_configs():
            if enabled_only and not config.enabled:
                continue
            versions = await self._repo.list_versions(config.id)
            active = next((v for v in versions if v.is_active), None)
            views.append(
                WorkflowConfigView(
                    config=config,
                    active_version=active,
                    version_count=len(versions),
                )
            )
        return views

    async def get_config(self, key: str) -> WorkflowConfig:
        config = await self._repo.get_by_key(key)
        if config is None:
            raise _not_found(key)
        return config

    async def get_detail(self, key: str) -> tuple[WorkflowConfig, list[WorkflowConfigVersion]]:
        config = await self.get_config(key)
        return config, await self._repo.list_versions(config.id)

    async def list_versions(self, config_id: str) -> list[WorkflowConfigVersion]:
        return await self._repo.list_versions(config_id)

    async def active_version(self, config_id: str) -> WorkflowConfigVersion | None:
        return await self._repo.active_version(config_id)

    async def get_version(self, version_id: str) -> WorkflowConfigVersion:
        version = await self._repo.get_version(version_id)
        if version is None:
            raise _version_not_found(version_id)
        return version

    async def selectable_version(
        self, version_id: str
    ) -> tuple[WorkflowConfig, WorkflowConfigVersion]:
        """A project may only select the active version of an enabled config."""
        version = await self.get_version(version_id)
        config = await self._repo.get_config(version.config_id)
        if config is None:
            raise _version_not_found(version_id)
        if not version.is_active or config.current_version_id != version.id:
            raise ValidationError(
                tr(
                    "workflow_config.version_not_active",
                    default="只能选择工作流配置的当前活跃版本",
                ),
                details={
                    "version_id": version_id,
                    "active_version_id": config.current_version_id,
                },
            )
        if not config.enabled:
            raise ValidationError(
                tr(
                    "workflow_config.disabled",
                    default="工作流配置 {name} 已停用，不能被新项目选择",
                    name=config.name,
                ),
                details={"key": config.key, "version_id": version_id},
            )
        return config, version

    # --- writes -----------------------------------------------------------

    async def save_version(
        self,
        actor: Actor,
        key: str,
        *,
        content_text: str,
        base_version_id: str,
    ) -> tuple[WorkflowConfig, WorkflowConfigVersion, bool]:
        """Create a new version on top of the current active one.

        Returns ``(config, version, created)``. When the canonical document is
        identical to the active version, no row is written and the existing
        active version is returned with ``created=False`` (RDM-85 feedback):
        re-saving without semantic changes must not accumulate versions.
        """
        security.require_user_manager(actor)
        config = await self.get_config(key)
        if config.is_builtin:
            raise ValidationError(
                tr(
                    "workflow_config.builtin_readonly",
                    default="内置工作流配置不能直接编辑；请先 fork 出可编辑的副本。",
                ),
                details={"key": key, "is_builtin": True},
            )
        active = await self._repo.active_version(config.id)
        if active is None:
            raise ValidationError(
                tr(
                    "workflow_config.no_active_version",
                    default="工作流配置没有活跃版本",
                ),
                details={"key": key},
            )
        if base_version_id != active.id:
            raise ConflictVersion(
                tr(
                    "workflow_config.stale_base",
                    default="只能基于当前活跃版本编辑，请刷新后重试",
                ),
                details={
                    "key": key,
                    "base_version_id": base_version_id,
                    "active_version_id": active.id,
                },
            )

        document = self._parse(content_text)
        if document.key != config.key:
            raise ValidationError(
                tr(
                    "workflow_config.key_mismatch",
                    default="配置内容中的 key（{document_key}）与正在编辑的配置 key（{key}）不一致",
                    document_key=document.key,
                    key=config.key,
                ),
                details={"expected": config.key, "actual": document.key},
            )

        digest = definition_hash(document.raw)
        if digest == active.content_hash:
            # Comments/formatting only, or a plain re-save: keep the current
            # active version instead of creating a byte-identical copy.
            return config, active, False

        version = WorkflowConfigVersion(
            id=new_id(),
            config_id=config.id,
            version=await self._repo.next_version_number(config.id),
            schema_version=document.schema_version,
            revision=document.revision,
            content_text=content_text,
            content=dict(document.raw),
            content_hash=digest,
            source_version_id=active.id,
            is_active=True,
            created_by=actor.id,
        )
        await self._repo.add_version(version)
        await self._repo.activate(config.id, version.id)
        config.name = document.name
        config.current_version_id = version.id
        config.updated_by = actor.id
        await self._repo.update_config(config)
        return config, version, True

    async def fork(
        self,
        actor: Actor,
        *,
        source_version_id: str,
        key: str,
        name: str | None,
    ) -> tuple[WorkflowConfig, WorkflowConfigVersion]:
        """Copy the current active version into a new non-builtin config."""
        security.require_user_manager(actor)
        source_version = await self.get_version(source_version_id)
        source_config = await self._repo.get_config(source_version.config_id)
        if source_config is None:
            raise _version_not_found(source_version_id)
        if not source_version.is_active or source_config.current_version_id != source_version.id:
            raise ValidationError(
                tr(
                    "workflow_config.fork_active_only",
                    default="只能从工作流配置的当前活跃版本 fork",
                ),
                details={
                    "source_version_id": source_version_id,
                    "active_version_id": source_config.current_version_id,
                },
            )

        try:
            new_key = validate_config_key(key)
            document = self._parse(source_version.content_text)
            new_name = validate_config_name(name or f"{source_config.name} 副本")
        except WorkflowConfigDocumentError as exc:
            raise ValidationError(str(exc), details={"key": key}) from exc

        if await self._repo.get_by_key(new_key) is not None:
            raise ValidationError(
                tr(
                    "workflow_config.key_duplicate",
                    default="工作流配置 key {key} 已存在",
                    key=new_key,
                ),
                details={"key": new_key},
            )

        raw = dict(document.raw)
        raw["key"] = new_key
        raw["name"] = new_name
        text = json.dumps(raw, ensure_ascii=False, indent=2) + "\n"

        config = WorkflowConfig(
            id=new_id(),
            key=new_key,
            name=new_name,
            is_builtin=False,
            enabled=True,
            created_by=actor.id,
        )
        version = WorkflowConfigVersion(
            id=new_id(),
            config_id=config.id,
            version=1,
            schema_version=document.schema_version,
            revision=document.revision,
            content_text=text,
            content=raw,
            content_hash=definition_hash(raw),
            source_version_id=source_version.id,
            is_active=True,
            created_by=actor.id,
        )
        config.current_version_id = version.id
        await self._repo.add_config(config)
        await self._repo.add_version(version)
        return config, version

    async def update_config(
        self,
        actor: Actor,
        key: str,
        *,
        name: str | None = None,
        enabled: bool | None = None,
    ) -> WorkflowConfig:
        security.require_user_manager(actor)
        config = await self.get_config(key)
        if name is not None:
            try:
                config.name = validate_config_name(name)
            except WorkflowConfigDocumentError as exc:
                raise ValidationError(str(exc), details={"key": key}) from exc
        if enabled is not None:
            config.enabled = enabled
        config.updated_by = actor.id
        await self._repo.update_config(config)
        return config

    # --- project engine ---------------------------------------------------

    async def engine_for_project(self, project: Project) -> WorkflowEngine:
        """Engine the project's new work items should be created under."""
        version_id = project.workflow_config_version_id
        if not version_id:
            return load_engine()
        version = await self._repo.get_version(version_id)
        if version is None:
            logger.warning(
                "project %s references missing workflow config version %s; using default",
                project.key,
                version_id,
            )
            return load_engine()
        return engine_from_text(version.content_text)

    async def selected_version(self, project: Project) -> WorkflowConfigVersion | None:
        if not project.workflow_config_version_id:
            return None
        return await self._repo.get_version(project.workflow_config_version_id)

    async def config_for_version(self, version: WorkflowConfigVersion) -> WorkflowConfig | None:
        """The key-level config row a version belongs to (upgrade provenance)."""
        return await self._repo.get_config(version.config_id)

    async def default_active(self) -> tuple[WorkflowConfig, WorkflowConfigVersion] | None:
        """The builtin ``default`` config's active version, if imported.

        Projects without an explicit selection run the packaged default. The
        config row normally exists (startup sync imports it), which gives the
        item a human-readable key/version snapshot.
        """
        config = await self._repo.get_by_key("default")
        if config is None or config.current_version_id is None:
            return None
        version = await self._repo.get_version(config.current_version_id)
        if version is None:
            return None
        return config, version

    async def project_selection(self, project: Project) -> dict[str, object] | None:
        """Echo the project's pinned version, even if it is old or disabled.

        The settings page cannot derive this from ``/workflow-configs``: that
        endpoint lists only each key's *active* version and hides disabled
        configs. A project may legitimately stay pinned to a version that is
        neither (RDM-86).
        """
        version = await self.selected_version(project)
        if version is None:
            return None
        config = await self._repo.get_config(version.config_id)
        if config is None:
            return None
        latest = await self._repo.active_version(config.id)
        has_update = bool(
            config.enabled
            and latest is not None
            and latest.id != version.id
            and latest.version > version.version
        )
        return {
            "config_id": config.id,
            "key": config.key,
            "name": config.name,
            "is_builtin": config.is_builtin,
            "enabled": config.enabled,
            "version_id": version.id,
            "version": version.version,
            "schema_version": version.schema_version,
            "revision": version.revision,
            "is_active": version.is_active,
            "latest_version_id": latest.id if latest is not None else None,
            "latest_version": latest.version if latest is not None else None,
            "has_update": has_update,
        }

    async def engine_for_version_ids(self, version_ids: Sequence[str]) -> dict[str, WorkflowEngine]:
        """Batch variant for callers holding many projects (unused for now)."""
        engines: dict[str, WorkflowEngine] = {}
        for version_id in dict.fromkeys(version_ids):
            version = await self._repo.get_version(version_id)
            if version is not None:
                engines[version_id] = engine_from_text(version.content_text)
        return engines

    def _parse(self, text: str) -> WorkflowConfigDocument:
        try:
            return parse_config_document(text)
        except WorkflowConfigDocumentError as exc:
            # Surface the concrete reason: "missing base kind" is actionable,
            # a generic "validation failed" is not.
            raise ValidationError(str(exc), details={"reason": str(exc)}) from exc


__all__ = ["WorkflowConfigService", "WorkflowConfigView"]
