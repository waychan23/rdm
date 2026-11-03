"""M1-9: OpenAPI surfaces tags and the workflow definition endpoint."""

from __future__ import annotations

API = "/api/v1"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_all_api_paths_have_tags(server, owner_token: str) -> None:
    client, _settings, _app = server
    schema = (await client.get("/api/openapi.json")).json()
    paths = schema["paths"]
    missing = [
        path
        for path, methods in paths.items()
        if path.startswith(API)
        and any("tags" not in op for op in methods.values() if isinstance(op, dict))
    ]
    assert missing == []
    # M1 endpoint families present
    asserted = {
        f"{API}/workflow",
        f"{API}/projects/{{key}}/work-items",
        f"{API}/projects/{{key}}/mailbox",
        f"{API}/projects/{{key}}/sprints",
        f"{API}/projects/{{key}}/releases",
        f"{API}/releases/{{release_id}}",
        f"{API}/work-items/{{ref}}/comments",
    }
    assert asserted <= set(paths)


async def test_workflow_endpoint_shape(server, owner_token: str) -> None:
    client, _settings, _app = server
    r = await client.get(f"{API}/workflow", headers=auth(owner_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["version"] == 3
    assert data["kinds"]["issue"]["gates"]["CLOSED_DONE"]["min_children"] == 1
