"""Threaded mock webhook receiver for S9."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class MockWebhook:
    url: str
    received: list[dict] = field(default_factory=list)
    fail_until: int = 0
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    def set_fail(self, count: int) -> None:
        self.fail_until = count

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)


def start_mock_webhook() -> MockWebhook:
    hook = MockWebhook(url="")
    hook.received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length)
            hook.received.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )
            if hook.fail_until > 0:
                hook.fail_until -= 1
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"err")
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    hook._server = server
    hook._thread = thread
    hook.url = f"http://127.0.0.1:{server.server_address[1]}/hook"
    return hook
