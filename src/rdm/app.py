"""Application composition root (wiring lives only here)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from rdm.application.services.bootstrap import bootstrap_if_empty
from rdm.config import Settings
from rdm.infrastructure.webhook.worker import WebhookWorker
from rdm.interfaces.http.artifacts import router as artifacts_router
from rdm.interfaces.http.attachments import router as attachments_router
from rdm.interfaces.http.auth import router as auth_router
from rdm.interfaces.http.comments import router as comments_router
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.errors import install_exception_handlers
from rdm.interfaces.http.local import router as local_router
from rdm.interfaces.http.logging import RequestContextMiddleware, configure_logging
from rdm.interfaces.http.mailbox import router as mailbox_router
from rdm.interfaces.http.me import router as me_router
from rdm.interfaces.http.notifications import router as notifications_router
from rdm.interfaces.http.overview import router as overview_router
from rdm.interfaces.http.routers import (
    members_router,
    projects_router,
    system_router,
)
from rdm.interfaces.http.search import router as search_router
from rdm.interfaces.http.spa import RootDispatch
from rdm.interfaces.http.sprint import router as sprints_router
from rdm.interfaces.http.todos import router as todos_router
from rdm.interfaces.http.users import router as users_router
from rdm.interfaces.http.workflow import router as workflow_router
from rdm.interfaces.http.workitem import router as work_items_router
from rdm.interfaces.http.workspaces import router as workspaces_router
from rdm.interfaces.mcp.oauth_provider import RdmOAuthProvider
from rdm.interfaces.mcp.request_scope import RequestScopeMiddleware
from rdm.interfaces.mcp.server import build_mcp

logger = logging.getLogger("rdm.app")

_RESOURCES = Path(__file__).resolve().parent / "resources"
# Single SPA bundle (§17): the legacy Vue app was removed together with the
# --web-ui switch when web-next became the only frontend.
WEB_DIST = _RESOURCES / "web-next-dist"


def create_app(settings: Settings, *, bootstrap: bool = True) -> FastAPI:
    configure_logging()
    container = Container(settings)
    base_url = f"http://{settings.host}:{settings.port}"
    oauth_provider = RdmOAuthProvider(base_url=base_url, container=container)
    mcp = build_mcp(container, oauth_provider)
    # streamable-http only; no stdio (architecture §1). host_origin_protection
    # is disabled: rdm binds loopback only (§16.59) and serves test hosts too.
    mcp_http = mcp.http_app(transport="streamable-http", host_origin_protection=False)
    # OAuth endpoints (/authorize, /.well-known/*) need the ASGI scope to
    # read the session cookie, so wrap the whole FastMCP sub-app.
    mcp_guarded = RequestScopeMiddleware(mcp_http)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        worker = WebhookWorker(container, settings)
        # Compose FastMCP's lifespan into ours.
        async with mcp_http.lifespan(mcp_http):
            if bootstrap:
                async with container.uow() as uow:
                    ticket = await bootstrap_if_empty(
                        uow,
                        base_url=base_url,
                        extra_redirect_uris=settings.extra_redirect_uri_list,
                    )
                if ticket:
                    logger.warning(
                        "首次启动：请在本机打开设置 Org Owner 密码：%s/set-password?ticket=%s "
                        "（7 天内有效；丢失可执行 `rdm account recover-owner` 重新生成）",
                        base_url,
                        ticket,
                    )
            worker.start()
            try:
                yield
            finally:
                await worker.stop()
                await container.aclose()

    app = FastAPI(title="rd-manager", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(local_router)
    app.include_router(projects_router)
    app.include_router(users_router)
    app.include_router(me_router)
    app.include_router(members_router)
    app.include_router(work_items_router)
    app.include_router(sprints_router)
    app.include_router(mailbox_router)
    app.include_router(comments_router)
    app.include_router(attachments_router)
    app.include_router(artifacts_router)
    app.include_router(workspaces_router)
    app.include_router(workflow_router)
    app.include_router(overview_router)
    app.include_router(notifications_router)
    app.include_router(todos_router)
    app.include_router(search_router)

    # FastMCP's http_app serves /mcp and the OAuth 2.1 endpoints (§16.54);
    # RootDispatch splits those from the static SPA, while API routers above
    # win route matching first. Authentication is FastMCP's bearer middleware
    # (RdmOAuthProvider accepts both PAT and OAuth access tokens).
    app.mount("/", RootDispatch(mcp_guarded, WEB_DIST))
    return app
