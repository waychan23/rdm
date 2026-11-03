"""Shared fixtures: full HTTP+MCP server app on a tmp data dir (§17).

Backend selection (§17.114): SQLite by default. `RDM_TEST_BACKEND=postgres`
or `both` (or `--db-backend`) runs the same suite on ParadeDB's PostgreSQL
image via testcontainers. Each PostgreSQL test gets its own database.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from rdm.app import create_app
from rdm.config import Settings, normalize_database_url
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

# Ryuk needs to mount the Docker socket; that fails on some Docker Desktop
# setups (macOS non-standard socket path). The session fixture stops the
# container explicitly, so the reaper is not needed.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

PG_IMAGE = os.environ.get("RDM_TEST_PG_IMAGE", "paradedb/paradedb:0.26.4-pg18")

OWNER_PASSWORD = "OwnerPass123"
WEB_REDIRECT = "http://test/auth/callback"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--db-backend",
        default=os.environ.get("RDM_TEST_BACKEND", "sqlite"),
        choices=("sqlite", "postgres", "both"),
        help="Database backend(s) for integration/contract tests.",
    )
    parser.addoption(
        "--require-postgres",
        action="store_true",
        default=False,
        help="Fail instead of skipping when the postgres backend is unavailable.",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "db_backend" not in metafunc.fixturenames:
        return
    choice = metafunc.config.getoption("--db-backend")
    metafunc.parametrize("db_backend", ["sqlite", "postgres"] if choice == "both" else [choice])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        callspec = getattr(item, "callspec", None)
        backend = callspec.params.get("db_backend") if callspec is not None else None
        if backend == "postgres" and item.get_closest_marker("sqlite_only"):
            item.add_marker(pytest.mark.skip(reason="sqlite-only test"))
        if backend == "sqlite" and item.get_closest_marker("postgres_only"):
            item.add_marker(pytest.mark.skip(reason="postgres-only test"))


@pytest.fixture
def db_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="session")
def pg_base_url(request: pytest.FixtureRequest) -> Iterator[str | None]:
    choice = request.config.getoption("--db-backend")
    if choice not in ("postgres", "both"):
        yield None
        return
    override = os.environ.get("RDM_TEST_DB_URL")
    if override:
        yield normalize_database_url(override)
        return
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer(
            PG_IMAGE,
            driver="psycopg",
            username="postgres",
            password="postgres",
            dbname="postgres",
        )
        container.start()
    except Exception as exc:  # noqa: BLE001 - missing docker/testcontainers is a skip
        if request.config.getoption("--require-postgres"):
            pytest.fail(f"postgres backend requested but unavailable: {exc}")
        pytest.skip(f"postgres backend unavailable: {exc}")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture
def pg_database_url(pg_base_url: str | None, db_backend: str) -> Iterator[str | None]:
    if db_backend != "postgres":
        yield None
        return
    assert pg_base_url is not None
    name = "rdm_test_" + uuid.uuid4().hex[:12]
    admin = create_engine(pg_base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        url = make_url(pg_base_url).set(database=name)
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest_asyncio.fixture
async def server(
    tmp_path, db_backend: str, pg_database_url: str | None
) -> AsyncIterator[tuple[httpx.AsyncClient, Settings, object]]:
    settings = Settings(
        data_dir=tmp_path / "data",
        public_base_url="",
        extra_redirect_uris=WEB_REDIRECT,
        **({"database_url": pg_database_url} if db_backend == "postgres" else {}),
    )
    initialize_data_dir(settings.data_dir)
    run_upgrade(settings.data_dir, database_url=settings.database_url or None)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, settings, app


async def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


async def web_login(
    client: httpx.AsyncClient, name: str, password: str, *, remember: bool = True
) -> tuple[str, str]:
    """Full first-party OAuth flow; returns (access_token, refresh_token)."""
    verifier, challenge = await pkce()
    r = await client.get(
        "/api/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "rdm-web",
            "redirect_uri": WEB_REDIRECT,
            "state": "s",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "web",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
    r = await client.post(
        "/api/v1/auth/login",
        json={"auth_key": auth_key, "name": name, "password": password, "remember": remember},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["must_reset"] is False, data
    code = parse_qs(urlparse(data["redirect_to"]).query)["code"][0]
    r = await client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "rdm-web",
            "redirect_uri": WEB_REDIRECT,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The browser audience is REST, never MCP (§17.79).
    assert body["scope"] == "web"
    return body["access_token"], body["refresh_token"]


async def ensure_owner_access(client: httpx.AsyncClient, app) -> str:
    """Set the initial owner password once and return an access token."""
    cached = getattr(app.state, "owner_access", None)
    if cached:
        return cached
    r = await client.post("/api/v1/local/owner-recovery")
    assert r.status_code == 200, r.text
    url = r.json()["data"]["set_password_url"]
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    r = await client.post(
        "/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": OWNER_PASSWORD},
    )
    assert r.status_code == 200, r.text
    access, _refresh = await web_login(client, "owner", OWNER_PASSWORD)
    app.state.owner_access = access
    return access


@pytest_asyncio.fixture
async def owner_access(server) -> str:
    client, _settings, app = server
    return await ensure_owner_access(client, app)


@pytest_asyncio.fixture
async def owner_token(server) -> str:
    client, _settings, app = server
    access = await ensure_owner_access(client, app)
    r = await client.post(
        "/api/v1/me/tokens",
        json={"label": "test"},
        headers=auth(access),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
