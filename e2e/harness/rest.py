"""Tiny authenticated REST client for deterministic setup steps (§17)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import httpx

PASSWORD = "E2ePassw0rd"


class RestClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(base_url=self.base_url, timeout=30, trust_env=False)
        self.token = token
        self._users: dict[str, tuple[str, str]] = {}

    def headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.token}"}

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self.headers(kwargs.pop("token", None)))
        # OAuth protocol endpoints live under /api/oauth (architecture §17.160).
        url = path if path.startswith("/api/") else f"/api/v1{path}"
        return self.http.request(method, url, headers=headers, **kwargs)

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

    def create_user(
        self, name: str, *, webhook: str | None = None, fmt: str = "generic"
    ) -> tuple[str, str]:
        """Create a human, set a password through the reset link, return a PAT."""
        r = self.post("/users", {"name": name})
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        user_id = data["user"]["id"]
        ticket = parse_qs(urlparse(data["password_reset_url"]).query)["ticket"][0]
        r = self.post("/auth/set-password", {"ticket": ticket, "new_password": PASSWORD})
        assert r.status_code == 200, r.text
        token = self.login_pat(name)
        self._users[user_id] = (name, PASSWORD)
        if webhook:
            r = self.http.patch(
                "/api/v1/me",
                json={"notify_webhook": webhook, "notify_webhook_format": fmt},
                headers=self.headers(token),
            )
            assert r.status_code == 200, r.text
        return user_id, token

    def login_pat(self, name: str, *, act_as_user_id: str | None = None) -> str:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        redirect = f"{self.base_url}/auth/callback"
        r = self.http.get(
            f"{self.base_url}/api/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": "rdm-web",
                "redirect_uri": redirect,
                "state": "e2e",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "mcp",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        auth_key = parse_qs(urlparse(r.headers["location"]).query)["auth_key"][0]
        r = self.http.post(
            f"{self.base_url}/api/v1/auth/login",
            json={
                "auth_key": auth_key,
                "name": name,
                "password": PASSWORD,
                "remember": True,
            },
        )
        assert r.status_code == 200, r.text
        code = parse_qs(urlparse(r.json()["data"]["redirect_to"]).query)["code"][0]
        r = self.http.post(
            f"{self.base_url}/api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": "rdm-web",
                "redirect_uri": redirect,
            },
        )
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        payload: dict = {"label": "e2e"}
        if act_as_user_id:
            payload["act_as_user_id"] = act_as_user_id
        r = self.http.post(
            f"{self.base_url}/api/v1/me/tokens",
            json=payload,
            headers=self.headers(access),
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["token"]

    def create_member(
        self,
        project: str,
        name: str,
        *,
        type_: str = "human",
        roles: list[str] | None = None,
        manager: str | None = None,
        manager_name: str | None = None,
        manager_token: str | None = None,
        webhook: str | None = None,
        fmt: str = "generic",
    ) -> tuple[str, str]:
        if type_ == "agent":
            assert manager and manager_name and manager_token, "agents need their manager"
            r = self.post(
                "/me/agents",
                {"name": name, "notify_webhook": webhook, "notify_webhook_format": fmt},
                token=manager_token,
            )
            assert r.status_code == 201, r.text
            agent_id = r.json()["data"]["id"]
            token = self.login_pat(manager_name, act_as_user_id=agent_id)
            self._users[agent_id] = (manager_name, PASSWORD)
            return agent_id, token

        user_id, token = self.create_user(name, webhook=webhook, fmt=fmt)
        r = self.post(
            f"/projects/{project}/members",
            {"user_id": user_id, "roles": roles or ["worker"]},
        )
        assert r.status_code == 201, r.text
        return user_id, token

    def create_item(self, project: str, payload: dict, token: str | None = None) -> dict:
        r = self.post(f"/projects/{project}/work-items", payload, token=token)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def close(self) -> None:
        self.http.close()
