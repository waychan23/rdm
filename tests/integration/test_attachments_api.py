"""Integration: attachment upload/download/list/soft-delete (M2-2)."""

from __future__ import annotations

import hashlib

import httpx
from asgi_lifespan import LifespanManager

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _project(client: httpx.AsyncClient, token: str) -> None:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text


async def _item(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "附件任务", "task_type": "backend"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _member(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str] | None = None
) -> tuple[str, str]:
    from tests.support import make_member

    return await make_member(client, owner, "DEMO", name, roles or ["worker"])


async def test_upload_download_list_delete_flow(server, owner_token, tmp_path) -> None:
    client, settings, _app = server
    await _project(client, owner_token)
    item = await _item(client, owner_token)
    payload = chr(35).encode() + b" report " + bytes([0])
    files = {"file": ("季度报告.md", payload, "text/markdown")}

    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files=files,
        data={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    att = r.json()["data"]
    assert att["filename"] == "季度报告.md"
    assert att["size_bytes"] == len(payload)
    assert att["sha256"] == hashlib.sha256(payload).hexdigest()
    assert att["download_url"].startswith("/api/v1/attachments/")
    assert att["uploader"]["name"] == "owner"

    # The DB rel_path matches a real file under the data dir.
    on_disk = list((settings.projects_dir).glob("*/attachments/*/*"))
    on_disk = [p for p in on_disk if p.is_file()]
    assert len(on_disk) == 1
    assert on_disk[0].read_bytes() == payload

    r = await client.get(
        f"{API}/projects/DEMO/attachments",
        params={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 200
    assert [a["id"] for a in r.json()["data"]] == [att["id"]]

    r = await client.get(att["download_url"], headers=auth(owner_token))
    assert r.status_code == 200
    assert r.content == payload
    cd = r.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd

    r = await client.delete(f"{API}/attachments/{att['id']}", headers=auth(owner_token))
    assert r.status_code == 204
    # Soft delete: row hidden, file retained on disk.
    r = await client.get(att["download_url"], headers=auth(owner_token))
    assert r.status_code == 404
    assert on_disk[0].exists()


async def test_reject_executable_type(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    item = await _item(client, owner_token)
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/x-msdownload")},
        data={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_MIME"


async def test_unknown_owner_is_404(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("a.txt", b"a", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": "DEMO-999"},
        headers=auth(owner_token),
    )
    assert r.status_code == 404


async def test_only_uploader_or_privileged_can_delete(server, owner_token) -> None:
    client, _settings, _app = server
    await _project(client, owner_token)
    item = await _item(client, owner_token)
    _alice_id, alice = await _member(client, owner_token, "alice")
    _bob_id, bob = await _member(client, owner_token, "bob")

    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("a.txt", b"a", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(alice),
    )
    assert r.status_code == 201, r.text
    att_id = r.json()["data"]["id"]

    r = await client.delete(f"{API}/attachments/{att_id}", headers=auth(bob))
    assert r.status_code == 403

    r = await client.delete(f"{API}/attachments/{att_id}", headers=auth(alice))
    assert r.status_code == 204


async def test_size_limit_enforced(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "tiny",
        public_base_url="",
        attachment_max_bytes=10,
        extra_redirect_uris="http://test/auth/callback",
    )
    initialize_data_dir(settings.data_dir)
    run_upgrade(settings.data_dir)
    app = create_app(settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            from tests.conftest import auth as _auth
            from tests.conftest import ensure_owner_access

            access = await ensure_owner_access(client, app)
            r = await client.post("/api/v1/me/tokens", json={"label": "att"}, headers=_auth(access))
            token = r.json()["data"]["token"]
            await _project(client, token)
            item = await _item(client, token)
            r = await client.post(
                f"{API}/projects/DEMO/attachments",
                files={"file": ("big.bin", b"x" * 11, "application/octet-stream")},
                data={"owner_type": "work_item", "owner_ref": item["display_id"]},
                headers=auth(token),
            )
            assert r.status_code == 413
            assert r.json()["error"]["code"] == "ATTACHMENT_TOO_LARGE"


async def test_project_scoped_temp_image_commit_and_signed_url(server, owner_token) -> None:
    from urllib.parse import urlparse

    client, _settings, app = server
    await _project(client, owner_token)
    payload = b"\x89PNG\r\n\x1a\nfake"

    # Editor upload: project-scoped and temp.
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("pasted.png", payload, "image/png")},
        data={"owner_type": "project", "owner_ref": "DEMO", "state": "temp"},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    temp_att = r.json()["data"]
    assert temp_att["state"] == "temp"

    # A second temp upload that is never referenced stays temp.
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("orphan.png", b"orphan", "image/png")},
        data={"owner_type": "project", "state": "temp"},
        headers=auth(owner_token),
    )
    orphan_id = r.json()["data"]["id"]

    # Saving markdown that references the image promotes it.
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={
            "kind": "task",
            "title": "带图任务",
            "description_md": f"看图 ![x]({temp_att['download_url']})",
        },
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        f"{API}/projects/DEMO/attachments",
        params={"owner_type": "project"},
        headers=auth(owner_token),
    )
    assert r.status_code == 200, r.text
    states = {a["id"]: a["state"] for a in r.json()["data"]}
    assert states[temp_att["id"]] == "active"
    assert states[orphan_id] == "temp"

    # Default (non-editor) uploads remain active.
    item = await _item(client, owner_token)
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": ("report.txt", b"r", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert r.json()["data"]["state"] == "active"

    # Short-lived signed URL downloads without a Bearer token.
    signer = app.state.container.attachment_signer
    signed = signer.signed_url(app.state.container.settings.base_url, temp_att["id"])
    parsed = urlparse(signed)
    r = await client.get(parsed.path + "?" + parsed.query)
    assert r.status_code == 200, r.text
    assert r.content == payload

    # Tampered signature / missing signature is rejected.
    r = await client.get(parsed.path + "?exp=9999999999&sig=bad")
    assert r.status_code == 401
    r = await client.get(parsed.path)
    assert r.status_code == 401
