"""Integration: comment attachments and deletion (M2-1)."""

from __future__ import annotations

import sqlite3

import httpx

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.post(
        f"{API}/projects", json={"key": "DEMO", "name": "DEMO"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{API}/projects/DEMO/work-items",
        json={"kind": "task", "title": "评论任务", "task_type": "backend"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _member(
    client: httpx.AsyncClient, owner: str, name: str, roles: list[str] | None = None
) -> str:
    from tests.support import make_member

    return (await make_member(client, owner, "DEMO", name, roles or ["worker"]))[1]


async def _upload(client: httpx.AsyncClient, token: str, display_id: str, name: str) -> dict:
    r = await client.post(
        f"{API}/projects/DEMO/attachments",
        files={"file": (name, b"data-bytes", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": display_id},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_comment_with_attachment_ids_rebinds(server, owner_token) -> None:
    client, settings, _app = server
    item = await _setup(client, owner_token)
    att = await _upload(client, owner_token, item["display_id"], "notes.txt")

    r = await client.post(
        f"{API}/work-items/{item['display_id']}/comments",
        json={"body_md": "见附件", "attachment_ids": [att["id"]]},
        headers=auth(owner_token),
    )
    assert r.status_code == 201, r.text
    comment = r.json()["data"]
    assert [a["id"] for a in comment["attachments"]] == [att["id"]]

    # Attachment now hangs on the comment; item-level listing is empty,
    # comment listing carries it, download still works.
    r = await client.get(
        f"{API}/projects/DEMO/attachments",
        params={"owner_type": "work_item", "owner_ref": item["display_id"]},
        headers=auth(owner_token),
    )
    assert r.json()["data"] == []
    r = await client.get(
        f"{API}/work-items/{item['display_id']}/comments", headers=auth(owner_token)
    )
    comments = r.json()["data"]
    assert [a["id"] for a in comments[0]["attachments"]] == [att["id"]]
    r = await client.get(f"{API}/attachments/{att['id']}/download", headers=auth(owner_token))
    assert r.status_code == 200
    assert r.content == b"data-bytes"

    with sqlite3.connect(settings.db_path) as conn:
        row = conn.execute(
            "select owner_type, owner_id from attachment where id=?", (att["id"],)
        ).fetchone()
        assert row == ("comment", comment["id"])
        payload = conn.execute(
            "select payload from event where event_type='comment.created' order by seq desc limit 1"
        ).fetchone()[0]
        assert att["id"] in payload  # JSON text contains the id


async def test_comment_with_bad_attachment_ids_rejected(server, owner_token) -> None:
    client, _settings, _app = server
    item = await _setup(client, owner_token)
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/comments",
        json={"body_md": "坏附件", "attachment_ids": ["01HX0000000000000000000000"]},
        headers=auth(owner_token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    # No comment was created on the failed transaction.
    r = await client.get(
        f"{API}/work-items/{item['display_id']}/comments", headers=auth(owner_token)
    )
    assert r.json()["data"] == []


async def test_comment_delete_permissions_and_cascade(server, owner_token, tmp_path) -> None:
    client, settings, _app = server
    item = await _setup(client, owner_token)
    alice = await _member(client, owner_token, "alice")
    bob = await _member(client, owner_token, "bob")

    att = await _upload(client, alice, item["display_id"], "a.txt")
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/comments",
        json={"body_md": "alice 的评论", "attachment_ids": [att["id"]]},
        headers=auth(alice),
    )
    assert r.status_code == 201, r.text
    comment_id = r.json()["data"]["id"]

    r = await client.delete(f"{API}/comments/{comment_id}", headers=auth(bob))
    assert r.status_code == 403

    r = await client.delete(f"{API}/comments/{comment_id}", headers=auth(alice))
    assert r.status_code == 204

    r = await client.get(
        f"{API}/work-items/{item['display_id']}/comments", headers=auth(owner_token)
    )
    assert r.json()["data"] == []
    # Cascade soft-deleted the attachment row; the file stays on disk.
    r = await client.get(f"{API}/attachments/{att['id']}/download", headers=auth(owner_token))
    assert r.status_code == 404
    on_disk = [p for p in settings.projects_dir.glob("*/attachments/*/*") if p.is_file()]
    assert on_disk and on_disk[0].exists()

    with sqlite3.connect(settings.db_path) as conn:
        types = {
            row[0]
            for row in conn.execute(
                "select distinct event_type from event where aggregate_id=?", (comment_id,)
            )
        }
        assert "comment.deleted" in types
        cascade = conn.execute(
            "select payload from event where event_type='comment.deleted'"
        ).fetchone()[0]
        assert att["id"] in cascade


async def test_owner_can_delete_others_comments(server, owner_token) -> None:
    client, _settings, _app = server
    item = await _setup(client, owner_token)
    alice = await _member(client, owner_token, "alice")
    r = await client.post(
        f"{API}/work-items/{item['display_id']}/comments",
        json={"body_md": "待删"},
        headers=auth(alice),
    )
    comment_id = r.json()["data"]["id"]
    r = await client.delete(f"{API}/comments/{comment_id}", headers=auth(owner_token))
    assert r.status_code == 204
