"""Start a throwaway `rdm serve` subprocess on a free port."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

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


def start_server(root: Path, *, log_path: Path | None = None) -> Server:
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
        cwd=Path(__file__).parents[3],
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=1)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        process.kill()
        raise RuntimeError("test server did not become healthy in 30s")

    # Lifespan bootstrap writes the token on first start. Health can answer
    # before the lifespan context finishes flushing, so poll for the file.
    token_path = data_dir / "bootstrap-token"
    deadline = time.time() + 15
    while time.time() < deadline:
        if token_path.exists():
            break
        time.sleep(0.1)
    if not token_path.exists():
        process.kill()
        raise RuntimeError("bootstrap token was not written")
    owner_token = token_path.read_text(encoding="utf-8").strip()
    return Server(process, base_url, data_dir, owner_token, port)
