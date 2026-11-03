"""Start a throwaway `rdm serve` subprocess on a free port."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Server:
    process: subprocess.Popen
    base_url: str
    data_dir: Path
    owner_token: str
    port: int

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def _rdm_argv(data_dir: Path, port: int) -> list[str]:
    rdm = shutil.which("rdm")
    if rdm:
        return [rdm]
    return [sys.executable, "-m", "rdm.interfaces.cli.main"]


REPO_ROOT = Path(__file__).resolve().parents[2]


def start_server(root: Path, *, log_path: Path | None = None) -> Server:
    # Absolute paths keep the subprocess independent of the caller's cwd.
    root = root.resolve()
    data_dir = root / "data"
    port = free_port()
    argv = [
        *_rdm_argv(data_dir, port),
        "serve",
        "--data-dir",
        str(data_dir),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    log = log_path.open("w") if log_path else subprocess.DEVNULL
    process = subprocess.Popen(  # noqa: S603
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=REPO_ROOT,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/healthz", timeout=1)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        process.kill()
        raise RuntimeError("test server did not become healthy in 30s")

    owner_token = _bootstrap_owner_token(base_url, process)
    return Server(process, base_url, data_dir, owner_token, port)


def _bootstrap_owner_token(base_url: str, process: subprocess.Popen) -> str:
    """Set the owner password through the bootstrap URL, then mint a PAT."""
    from e2e.harness.rest import PASSWORD, RestClient

    # Health can answer before the lifespan bootstrap flushed; retry briefly.
    ticket = None
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.post(f"{base_url}/api/v1/local/owner-recovery", timeout=2, trust_env=False)
            if r.status_code == 200:
                path = r.json()["data"]["set_password_url"]
                ticket = parse_qs(urlparse(path).query)["ticket"][0]
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    if ticket is None:
        process.kill()
        raise RuntimeError("owner recovery endpoint did not become ready")
    r = httpx.post(
        f"{base_url}/api/v1/auth/set-password",
        json={"ticket": ticket, "new_password": PASSWORD},
        timeout=10,
        trust_env=False,
    )
    if r.status_code != 200:
        process.kill()
        raise RuntimeError(f"setting owner password failed: {r.text}")
    client = RestClient(base_url, token="")
    try:
        return client.login_pat("owner")
    finally:
        client.close()
