"""Map domain errors to the unified {"error": {...}} envelope."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from rdm.domain.errors import ErrorCode, RdmError
from rdm.i18n import tr

logger = logging.getLogger("rdm.errors")


def _json_error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RdmError)
    async def _handle_rdm(_request: Request, exc: RdmError) -> JSONResponse:
        return _json_error(exc.http_status, str(exc.code), exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _json_error(
            422,
            str(ErrorCode.VALIDATION_ERROR),
            tr("errors.validation", locale=_request_locale(request)),
            {"fields": fields},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error: %s", exc)
        return _json_error(
            500,
            "INTERNAL_ERROR",
            tr("errors.internal", locale=_request_locale(request)),
        )


def _request_locale(request: Request) -> str | None:
    # The middleware resets its ContextVar before Starlette's outermost
    # ServerErrorMiddleware renders a 500, so read the scope copy.
    return getattr(request.state, "locale", None)
