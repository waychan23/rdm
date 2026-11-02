"""Load and freeze the packaged default workflow config.

The packaged file lives in ``resources/workflow-configs/default.json5``. At
runtime ``rdm serve`` also imports every ``*.json5`` under the data-dir
``workflow-configs`` directory (RDM-84); :func:`load_spec_text` keeps returning
the packaged default as the process-wide fallback for projects that have not
selected a config version.
"""

from functools import lru_cache
from importlib.resources import files

import pyjson5

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec
from rdm.domain.workflow.schema_versions import get_schema_strategy

DEFAULT_CONFIG_RESOURCE = ("workflow-configs", "default.json5")


def load_spec_text() -> str:
    """Raw JSON5 text of the packaged default workflow definition."""
    package = files("rdm.resources")
    for part in DEFAULT_CONFIG_RESOURCE:
        package = package.joinpath(part)
    return package.read_text(encoding="utf-8")


def parse_spec(text: str) -> WorkflowSpec:
    """Parse and validate one JSON5 workflow config document."""
    raw = pyjson5.loads(text)
    spec = WorkflowSpec.model_validate(raw)
    # Fail fast: a config using a schema version without a strategy cannot be
    # persisted or restored, so it must never reach the database (§17.120).
    get_schema_strategy(spec.version)
    return spec


@lru_cache(maxsize=1)
def load_spec() -> WorkflowSpec:
    return parse_spec(load_spec_text())


@lru_cache(maxsize=1)
def load_engine() -> WorkflowEngine:
    return WorkflowEngine(load_spec())


@lru_cache(maxsize=128)
def engine_from_text(text: str) -> WorkflowEngine:
    """Build (and cache) an engine from an immutable persisted config text."""
    return WorkflowEngine(parse_spec(text))
