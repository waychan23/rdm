"""CLI tests: a real uvicorn server on an ephemeral port."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, str]]:
    data_dir = tmp_path / "data"
    initialize_data_dir(data_dir)
    run_upgrade(data_dir)
    settings = Settings(data_dir=data_dir)
    app = create_app(settings)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    token = settings.bootstrap_token_path.read_text(encoding="utf-8").strip()
    try:
        yield f"http://127.0.0.1:{port}", token
    finally:
        server.should_exit = True
        thread.join(timeout=5)
