"""RDM_WEB_UI selects the served SPA bundle (architecture §16.62)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport
from pydantic import ValidationError

from rdm import app as app_module
from rdm.config import Settings


def test_default_bundle_is_next() -> None:
    assert Settings().web_ui == "next"


def test_rejects_unknown_bundle() -> None:
    with pytest.raises(ValidationError):
        Settings(web_ui="classic")  # type: ignore[arg-type]


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDM_WEB_UI", "legacy")
    assert Settings().web_ui == "legacy"


async def test_app_serves_selected_bundle(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    next_dist = tmp_path / "web-next-dist"
    legacy_dist = tmp_path / "web-dist"
    (next_dist / "assets").mkdir(parents=True)
    (legacy_dist / "assets").mkdir(parents=True)
    (next_dist / "index.html").write_text("<html>next</html>")
    (legacy_dist / "index.html").write_text("<html>legacy</html>")
    monkeypatch.setattr(app_module, "WEB_DISTS", {"next": next_dist, "legacy": legacy_dist})

    async def get_root(web_ui: str) -> tuple[int, str]:
        application = app_module.create_app(
            Settings(data_dir=tmp_path, web_ui=web_ui), bootstrap=False
        )
        transport = ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/", headers={"Accept": "text/html"})
            return r.status_code, r.text

    status, text = await get_root("next")
    assert status == 200 and "next" in text

    status, text = await get_root("legacy")
    assert status == 200 and "legacy" in text

    # A missing bundle directory keeps the M0-era JSON 404 behavior.
    monkeypatch.setattr(
        app_module,
        "WEB_DISTS",
        {"next": tmp_path / "gone", "legacy": legacy_dist},
    )
    application = app_module.create_app(Settings(data_dir=tmp_path, web_ui="next"), bootstrap=False)
    transport = ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/", headers={"Accept": "text/html"})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"
