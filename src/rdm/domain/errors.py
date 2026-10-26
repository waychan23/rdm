"""Unified error model — codes from docs/architecture.md §12.

Every interface (REST/MCP) maps RdmError to the shared envelope::

    {"error": {"code": ..., "message": ..., "details": {...}}}
"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_DELETED = "ALREADY_DELETED"
    FORBIDDEN = "FORBIDDEN"
    WORKFLOW_ILLEGAL_TRANSITION = "WORKFLOW_ILLEGAL_TRANSITION"
    WORKFLOW_GATE_BLOCKED = "WORKFLOW_GATE_BLOCKED"
    CONFLICT_VERSION = "CONFLICT_VERSION"
    ALREADY_ASSIGNED = "ALREADY_ASSIGNED"
    PROJECT_KEY_DUPLICATE = "PROJECT_KEY_DUPLICATE"
    SPRINT_ACTIVE_EXISTS = "SPRINT_ACTIVE_EXISTS"
    ATTACHMENT_TOO_LARGE = "ATTACHMENT_TOO_LARGE"
    UNSUPPORTED_MIME = "UNSUPPORTED_MIME"
    RDM_SERVER_UNREACHABLE = "RDM_SERVER_UNREACHABLE"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    RATE_LIMITED = "RATE_LIMITED"


class RdmError(Exception):
    code: ErrorCode = ErrorCode.VALIDATION_ERROR
    http_status: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details: dict[str, Any] = details or {}

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"code": str(self.code), "message": self.message, "details": self.details}}


class ValidationError(RdmError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 422


class NotFound(RdmError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class AlreadyDeleted(RdmError):
    code = ErrorCode.ALREADY_DELETED
    http_status = 404


class Forbidden(RdmError):
    code = ErrorCode.FORBIDDEN
    http_status = 403


class AuthInvalidToken(RdmError):
    code = ErrorCode.AUTH_INVALID_TOKEN
    http_status = 401


class AuthInvalidCredentials(RdmError):
    """Uniform login failure (unknown project/member or wrong password)."""

    code = ErrorCode.AUTH_INVALID_CREDENTIALS
    http_status = 401


class RateLimited(RdmError):
    code = ErrorCode.RATE_LIMITED
    http_status = 429


class WorkflowIllegalTransition(RdmError):
    code = ErrorCode.WORKFLOW_ILLEGAL_TRANSITION
    http_status = 409


class WorkflowGateBlocked(RdmError):
    code = ErrorCode.WORKFLOW_GATE_BLOCKED
    http_status = 409


class ConflictVersion(RdmError):
    code = ErrorCode.CONFLICT_VERSION
    http_status = 409


class AlreadyAssigned(RdmError):
    code = ErrorCode.ALREADY_ASSIGNED
    http_status = 409


class ProjectKeyDuplicate(RdmError):
    code = ErrorCode.PROJECT_KEY_DUPLICATE
    http_status = 409


class SprintActiveExists(RdmError):
    code = ErrorCode.SPRINT_ACTIVE_EXISTS
    http_status = 409


class AttachmentTooLarge(RdmError):
    code = ErrorCode.ATTACHMENT_TOO_LARGE
    http_status = 413


class UnsupportedMime(RdmError):
    code = ErrorCode.UNSUPPORTED_MIME
    http_status = 415
