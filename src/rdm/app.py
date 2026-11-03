"""Application composition root (wiring lives only here)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from rdm import __version__
from rdm.application.services.bootstrap import bootstrap_if_empty
from rdm.config import Settings
from rdm.infrastructure.webhook.worker import WebhookWorker
from rdm.interfaces.http.artifacts import router as artifacts_router
from rdm.interfaces.http.attachments import router as attachments_router
from rdm.interfaces.http.auth import router as auth_router
from rdm.interfaces.http.comments import router as comments_router
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.dispatch import OAUTH_PREFIX, OAuthRoutesOnly, RootDispatch
from rdm.interfaces.http.email_settings import router as email_settings_router
from rdm.interfaces.http.errors import install_exception_handlers
from rdm.interfaces.http.local import router as local_router
from rdm.interfaces.http.logging import RequestContextMiddleware, configure_logging
from rdm.interfaces.http.mailbox import router as mailbox_router
from rdm.interfaces.http.me import router as me_router
from rdm.interfaces.http.notifications import router as notifications_router
from rdm.interfaces.http.overview import router as overview_router
from rdm.interfaces.http.release import router as releases_router
from rdm.interfaces.http.routers import (
    members_router,
    projects_router,
    system_router,
)
from rdm.interfaces.http.search import router as search_router
from rdm.interfaces.http.sprint import router as sprints_router
from rdm.interfaces.http.stream import router as stream_router
from rdm.interfaces.http.todos import router as todos_router
from rdm.interfaces.http.users import router as users_router
from rdm.interfaces.http.workflow import router as workflow_router
from rdm.interfaces.http.workflow_config import router as workflow_config_router
from rdm.interfaces.http.workitem import router as work_items_router
from rdm.interfaces.http.workspaces import router as workspaces_router
from rdm.interfaces.mcp.oauth_provider import RdmOAuthProvider
from rdm.interfaces.mcp.request_scope import RequestScopeMiddleware
from rdm.interfaces.mcp.server import build_mcp

logger = logging.getLogger("rdm.app")


def create_app(settings: Settings, *, bootstrap: bool = True) -> FastAPI:
    configure_logging()
    container = Container(settings)
    # Public origin drives OAuth metadata/issuer, web_url and attachment links;
    # the internal origin is only used for the loopback bind/redirect aliases.
    public_base = settings.base_url
    oauth_base = f"{public_base}{OAUTH_PREFIX}"
    oauth_provider = RdmOAuthProvider(
        base_url=oauth_base,
        issuer_url=public_base,
        resource_base_url=public_base,
        container=container,
    )
    mcp = build_mcp(container, oauth_provider)
    # streamable-http only; no stdio (architecture §1). host_origin_protection
    # is disabled: rdm binds loopback only (§16.59) and serves test hosts too.
    mcp_http = mcp.http_app(transport="streamable-http", host_origin_protection=False)
    # OAuth endpoints (/authorize, /.well-known/*) read the ASGI scope so the
    # provider can see the original request; wrap the whole FastMCP sub-app.
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
                        base_url=public_base,
                        extra_redirect_uris=settings.extra_redirect_uri_list,
                        internal_base_url=settings.internal_base_url,
                    )
                if ticket:
                    logger.warning(
                        "首次启动：请在本机打开设置 Org Owner 密码：%s/set-password?ticket=%s "
                        "（7 天内有效；丢失可执行 `rdm account recover-owner` 重新生成）",
                        public_base,
                        ticket,
                    )
            worker.start()
            try:
                yield
            finally:
                await worker.stop()
                await container.aclose()

    # Docs stay inside the /api namespace so an ingress only needs /api/.
    app = FastAPI(
        title="rd-manager",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    )
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
    app.include_router(releases_router)
    app.include_router(mailbox_router)
    app.include_router(comments_router)
    app.include_router(attachments_router)
    app.include_router(artifacts_router)
    app.include_router(workspaces_router)
    app.include_router(workflow_router)
    app.include_router(workflow_config_router)
    app.include_router(email_settings_router)
    app.include_router(overview_router)
    app.include_router(notifications_router)
    app.include_router(todos_router)
    app.include_router(search_router)
    app.include_router(stream_router)

    # FastMCP's http_app carries /mcp, the four OAuth routes and the well-known
    # discovery routes. Mount the OAuth routes under /api/oauth (they stay at
    # the sub-app root internally), then let RootDispatch own /mcp and
    # /.well-known; API routers above win route matching first. The Python
    # process serves no HTML: the Web UI comes from Vite/nginx (§17.160).
    app.mount(f"{OAUTH_PREFIX}", OAuthRoutesOnly(mcp_guarded))
    app.mount("/", RootDispatch(mcp_guarded))
    return app
