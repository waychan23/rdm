"""Load and freeze the built-in resources/workflow.json5."""

from functools import lru_cache
from importlib.resources import files

import pyjson5

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec
from rdm.domain.workflow.schema_versions import get_schema_strategy


def load_spec_text() -> str:
    """Raw JSON5 text of the packaged workflow definition."""
    return files("rdm.resources").joinpath("workflow.json5").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_spec() -> WorkflowSpec:
    raw = pyjson5.loads(load_spec_text())
    spec = WorkflowSpec.model_validate(raw)
    # Fail fast: bumping workflow.json5 version requires a SchemaVn strategy
    # so persisted definitions of that version can be written and read (§17.120).
    get_schema_strategy(spec.version)
    return spec


@lru_cache(maxsize=1)
def load_engine() -> WorkflowEngine:
    return WorkflowEngine(load_spec())
