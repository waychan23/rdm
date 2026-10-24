"""Application composition root (wiring lives only here)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from rdm.application.services.bootstrap import bootstrap_if_empty
from rdm.config import Settings
from rdm.interfaces.http.comments import router as comments_router
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.errors import install_exception_handlers
from rdm.interfaces.http.logging import RequestContextMiddleware, configure_logging
from rdm.interfaces.http.mailbox import router as mailbox_router
from rdm.interfaces.http.routers import (
    members_router,
    projects_router,
    system_router,
)
from rdm.interfaces.http.spa import RootDispatch
from rdm.interfaces.http.sprint import router as sprints_router
from rdm.interfaces.http.workflow import router as workflow_router
from rdm.interfaces.http.workitem import router as work_items_router
from rdm.interfaces.mcp.auth_guard import McpBearerGuard
from rdm.interfaces.mcp.server import build_mcp

logger = logging.getLogger("rdm.app")

WEB_DIST = Path(__file__).resolve().parent / "resources" / "web-dist"


def create_app(settings: Settings, *, bootstrap: bool = True) -> FastAPI:
    configure_logging()
    container = Container(settings)
    mcp = build_mcp(container)
    # streamable-http only; no stdio (architecture §1).
    mcp_http = mcp.http_app(transport="streamable-http")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Compose FastMCP's lifespan into ours.
        async with mcp_http.lifespan(mcp_http):
            if bootstrap:
                async with container.uow() as uow:
                    token = await bootstrap_if_empty(uow, settings.bootstrap_token_path)
                if token:
                    logger.warning(
                        "first start: owner member created; bootstrap token written to %s",
                        settings.bootstrap_token_path,
                    )
            yield
            await container.aclose()

    app = FastAPI(title="rd-manager", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)

    app.include_router(system_router)
    app.include_router(projects_router)
    app.include_router(members_router)
    app.include_router(work_items_router)
    app.include_router(sprints_router)
    app.include_router(mailbox_router)
    app.include_router(comments_router)
    app.include_router(workflow_router)

    # FastMCP's http_app serves /mcp; RootDispatch splits /mcp (guarded) from
    # the static SPA, while API routers above win route matching first.
    app.mount(
        "/",
        RootDispatch(McpBearerGuard(mcp_http, container.authenticator), WEB_DIST),
    )
    return app
