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
) -> CliResult:
    """Run one headless prompt. The directory is pre-bound to an rdm member."""
    if cli == "claude":
        argv = [
            "claude",
            "-p",
            prompt,
            "--dangerously-skip-permissions",
        ]
    elif cli == "opencode":
        argv = ["opencode", "run", prompt]
    else:
        raise ValueError(f"unknown cli {cli}")

    env = dict(os.environ)
    env["RDM_TOKEN"] = token
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CliResult(False, f"TIMEOUT after {timeout}s: {exc}", 124)
    out = f"{proc.stdout}\n{proc.stderr}".strip()
    return CliResult(proc.returncode == 0, out, proc.returncode)
