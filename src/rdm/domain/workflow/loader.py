"""Load and freeze the built-in resources/workflow.yml."""

from functools import lru_cache
from importlib.resources import files

import yaml

from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.schema import WorkflowSpec


def load_yaml_text() -> str:
    return files("rdm.resources").joinpath("workflow.yml").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_spec() -> WorkflowSpec:
    raw = yaml.safe_load(load_yaml_text())
    return WorkflowSpec.model_validate(raw)


@lru_cache(maxsize=1)
def load_engine() -> WorkflowEngine:
    return WorkflowEngine(load_spec())
