"""Tiny authenticated REST client for deterministic setup steps."""

from __future__ import annotations

import httpx


class RestClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=30)
        self.token = token

    def headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.token}"}

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self.headers(kwargs.pop("token", None)))
        return self.http.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json=None, **kwargs) -> httpx.Response:
        return self.request("POST", path, json=json, **kwargs)

    def patch(self, path: str, json=None, **kwargs) -> httpx.Response:
        return self.request("PATCH", path, json=json, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    # -- provisioning helpers ---------------------------------------------

    def create_project(self, key: str, name: str | None = None) -> dict:
        r = self.post("/projects", {"key": key, "name": name or key})
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def create_member(
        self,
        project: str,
        name: str,
        *,
        type_: str = "human",
        roles: list[str] | None = None,
        manager: str | None = None,
        webhook: str | None = None,
        fmt: str = "generic",
    ) -> tuple[str, str]:
        payload = {
            "name": name,
            "type": type_,
            "roles": roles or ["worker"],
            "notify_webhook": webhook,
            "notify_webhook_format": fmt,
        }
        if manager:
            payload["manager_member_id"] = manager
        r = self.post(f"/projects/{project}/members", payload)
        assert r.status_code == 201, r.text
        mid = r.json()["data"]["id"]
        r = self.post(f"/members/{mid}/tokens", {"label": "e2e"})
        assert r.status_code == 201, r.text
        return mid, r.json()["data"]["token"]

    def create_item(self, project: str, payload: dict, token: str | None = None) -> dict:
        r = self.post(f"/projects/{project}/work-items", payload, token=token)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def close(self) -> None:
        self.http.close()
