"""Workflow config file validation shared by startup sync and the web editor.

A workflow config document is a complete ``WorkflowSpec`` JSON5 object plus two
envelope fields required by RDM-84:

* ``key`` — stable identifier shared by all versions of one config;
* ``name`` — display name shown when selecting a workflow for a project.

Only the newest schema version supported by this server may be imported or
saved. Older schemas stay readable for already-pinned work items, but they are
never accepted as a *new* config version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pyjson5

from rdm.domain.workflow.loader import parse_spec
from rdm.domain.workflow.schema import WorkflowSpec
from rdm.domain.workflow.schema_versions import latest_schema_version

CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,49}$")
CONFIG_NAME_MAX = 200


class WorkflowConfigDocumentError(ValueError):
    """A config document is structurally invalid or uses a stale schema."""


@dataclass(frozen=True)
class WorkflowConfigDocument:
    key: str
    name: str
    spec: WorkflowSpec
    raw: dict[str, Any]
    text: str = ""

    @property
    def schema_version(self) -> int:
        return self.spec.version

    @property
    def revision(self) -> int:
        return self.spec.revision


def validate_config_key(key: str) -> str:
    value = (key or "").strip()
    if not CONFIG_KEY_RE.fullmatch(value):
        raise WorkflowConfigDocumentError(
            "工作流 key 必须以小写字母开头，只能包含小写字母、数字、下划线和连字符，"
            f"长度 2-50：{key!r}"
        )
    return value


def validate_config_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise WorkflowConfigDocumentError("工作流展示名称不能为空")
    if len(value) > CONFIG_NAME_MAX:
        raise WorkflowConfigDocumentError(f"工作流展示名称不能超过 {CONFIG_NAME_MAX} 个字符")
    return value


def parse_config_document(text: str) -> WorkflowConfigDocument:
    """Parse, validate and freeze one JSON5 config document."""
    try:
        spec = parse_spec(text)
    except WorkflowConfigDocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize JSON5/Pydantic failures
        raise WorkflowConfigDocumentError(f"工作流配置无法解析或校验失败：{exc}") from exc

    try:
        raw = pyjson5.loads(text)
    except Exception as exc:  # noqa: BLE001 - source was already parsed above
        raise WorkflowConfigDocumentError(f"工作流配置不是合法 JSON5：{exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowConfigDocumentError("工作流配置顶层必须是对象")

    key = validate_config_key(raw.get("key", ""))
    name = validate_config_name(raw.get("name", ""))

    latest = latest_schema_version()
    if spec.version != latest:
        raise WorkflowConfigDocumentError(
            f"工作流配置 schema version={spec.version}，当前服务只接受最新版本 {latest}；"
            "请按最新 schema 适配文件后再启动。"
        )
    return WorkflowConfigDocument(key=key, name=name, spec=spec, raw=dict(raw), text=text)
