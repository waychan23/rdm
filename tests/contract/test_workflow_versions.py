"""Contract: persisted effective workflow definitions (§17.120)."""

from __future__ import annotations

import pyjson5

from rdm.application.services.workflow_version_service import WorkflowVersionService
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_engine, load_spec_text
from rdm.domain.workflow.schema import WorkflowSpec
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


def _modified_spec(
    *,
    label: str | None = None,
    version: int | None = None,
    revision: int | None = None,
) -> WorkflowSpec:
    raw = pyjson5.loads(load_spec_text())
    if label is not None:
        raw["kinds"]["task"]["subtypes"]["code_review"]["label"] = label
    if version is not None:
        raw["version"] = version
    if revision is not None:
        raw["revision"] = revision
    return WorkflowSpec.model_validate(raw)


async def test_ensure_reuses_identical_definition(uow: SqlAlchemyUnitOfWork) -> None:
    service = WorkflowVersionService(uow, load_engine())
    first = await service.ensure("task", "code_review")
    second = await service.ensure("task", "code_review")

    assert first.id == second.id
    assert first.version == 1
    assert first.def_hash == second.def_hash
    spec = load_engine().spec
    assert first.config_schema_version == spec.version
    assert first.config_version == spec.revision


async def test_ensure_creates_next_version_for_changed_definition(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    service = WorkflowVersionService(uow, load_engine())
    first = await service.ensure("task", "code_review")

    changed_engine = WorkflowEngine(_modified_spec(label="CR"))
    second = await service.ensure(
        "task",
        "code_review",
        resolved=changed_engine.resolve("task", "code_review"),
    )

    assert second.id != first.id
    assert second.version == 2
    assert second.definition["label"] == "CR"


async def test_ensure_reverting_creates_new_version(uow: SqlAlchemyUnitOfWork) -> None:
    service = WorkflowVersionService(uow, load_engine())
    original = await service.ensure("task", "code_review")
    changed_engine = WorkflowEngine(_modified_spec(label="CR"))
    await service.ensure(
        "task",
        "code_review",
        resolved=changed_engine.resolve("task", "code_review"),
    )

    reverted = await service.ensure("task", "code_review")

    assert reverted.id != original.id
    assert reverted.version == 3
    assert reverted.def_hash == original.def_hash


async def test_config_schema_version_change_creates_new_version(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    from rdm.domain.workflow.schema_versions import base, v3

    # A throwaway strategy keeps this test independent of the packaged schema
    # version (currently 4 with parent triggers, §17.137).
    class SchemaTest(v3.SchemaV3):
        schema_version = 105

    try:
        first = await WorkflowVersionService(uow, load_engine()).ensure("story", None)

        schema_engine = WorkflowEngine(_modified_spec(version=105))
        second = await WorkflowVersionService(uow, schema_engine).ensure(
            "story", None, resolved=schema_engine.resolve("story")
        )

        assert second.id != first.id
        assert second.version == 2
        assert second.config_schema_version == 105
        assert second.definition["format"] == 105
    finally:
        base._REGISTRY.pop(105, None)


async def test_config_version_only_change_reuses_latest(
    uow: SqlAlchemyUnitOfWork,
) -> None:
    first = await WorkflowVersionService(uow, load_engine()).ensure("story", None)

    revision_engine = WorkflowEngine(_modified_spec(revision=2))
    second = await WorkflowVersionService(uow, revision_engine).ensure(
        "story", None, resolved=revision_engine.resolve("story")
    )

    assert second.id == first.id
    assert second.version == 1


async def test_non_task_definitions_have_no_subtype(uow: SqlAlchemyUnitOfWork) -> None:
    service = WorkflowVersionService(uow, load_engine())
    row = await service.ensure("story", "ignored")
    assert row.subtype is None
