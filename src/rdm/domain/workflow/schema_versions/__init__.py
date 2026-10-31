"""Versioned persisted-definition schemas (§17.120).

Importing this package registers every version module. Add a new version by
creating ``vN.py`` and importing it below; do not edit the registry or callers.
"""

from rdm.domain.workflow.schema_versions.base import (
    DefinitionSchema,
    UnsupportedWorkflowSchema,
    get_schema_strategy,
    latest_schema_version,
    normalized_subtype,
    validate_definition,
)

# Import after ``base`` so subclass registration sees the registry.
from . import v3 as v3  # noqa: F401,E402

__all__ = [
    "DefinitionSchema",
    "UnsupportedWorkflowSchema",
    "get_schema_strategy",
    "latest_schema_version",
    "normalized_subtype",
    "validate_definition",
]
