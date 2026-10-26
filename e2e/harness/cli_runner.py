"""Headless CLI invocation: claude -p / opencode run."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CliResult:
    ok: bool
    stdout: str
    returncode: int


@dataclass
class Cli:
    name: str
    available: bool
    version: str = ""


def detect() -> dict[str, Cli]:
    out: dict[str, Cli] = {}
    for name in ("claude", "opencode"):
        path = shutil.which(name)
        if path:
            try:
                proc = subprocess.run(
                    [name, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                version = (proc.stdout or proc.stderr).strip().splitlines()[0]
            except (OSError, subprocess.SubprocessError):
                version = ""
            out[name] = Cli(name, True, version)
    return out


def run(
    cli: str,
    cwd: Path,
    token: str,
    prompt: str,
    *,
    timeout: int = 180,
    model: str | None = None,
    stream_log: Path | None = None,
) -> CliResult:
    """Run one headless prompt. The directory is pre-bound to an rdm member."""
    if cli == "claude":
        argv = [
            "claude",
            "-p",
            prompt,
            "--dangerously-skip-permissions",
            "--verbose",
        ]
        # Explicit --model marks the alias as user-selected; print/SDK mode
        # otherwise rejects custom gateway aliases (unrecognized_model).
        if model:
            argv += ["--model", model]
    elif cli == "opencode":
        argv = ["opencode", "run", prompt]
        if model:
            argv += ["--model", model]
    else:
        raise ValueError(f"unknown cli {cli}")

    # Inherit the shell environment (ANTHROPIC_BASE_URL/TOKEN/MODEL live
    # there); harness bindings override.
    env = dict(os.environ)
    env["RDM_TOKEN"] = token
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"

    sink = stream_log.open("w", encoding="utf-8") if stream_log else subprocess.PIPE
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=sink,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            tail = _tail(stream_log)
            return CliResult(
                False,
                f"TIMEOUT after {timeout}s\n--- live log tail ---\n{tail}",
                124,
            )
        if stream_log is None:
            out = (proc.stdout.read() if proc.stdout else "").strip()
        else:
            out = _tail(stream_log)
    finally:
        if stream_log is not None:
            sink.close()
    return CliResult(rc == 0, out, rc)


def _tail(path: Path | None, limit: int = 4000) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]
