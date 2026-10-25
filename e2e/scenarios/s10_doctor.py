"""S10: rdm doctor 全绿；破坏附件后报错；workflow REST/MCP 同源。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from e2e.harness.context import Harness
from e2e.scenarios._helpers import agent_expect

REPO_ROOT = Path(__file__).resolve().parents[2]


def _doctor(h: Harness) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "rdm.interfaces.cli.main",
            "doctor",
            "--data-dir",
            str(h.server.data_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return proc.returncode, proc.stdout


def run(h: Harness) -> None:
    h.project("S10")

    code, out = _doctor(h)
    assert code == 0, out
    payload = json.loads(out)
    by_name = {c["name"]: c["status"] for c in payload["checks"]}
    assert by_name["database"] == "OK"
    assert by_name["workflow"] == "OK"
    assert by_name["endpoint"] == "OK"

    # Break an attachment record -> FAIL exit code.
    h.member("S10", "tl", roles=["manager"])
    item = h.item("S10", {"kind": "task", "title": "doctor 任务", "task_type": "qa"})
    up = h.rest.post(
        "/projects/S10/attachments",
        files={"file": ("a.txt", b"abc", "text/plain")},
        data={"owner_type": "work_item", "owner_ref": item["display_id"]},
    )
    assert up.status_code == 201
    rel = h.db.query("select rel_path from attachment")[0]["rel_path"]
    target = h.server.data_dir / "projects" / rel
    target.unlink()
    code, out = _doctor(h)
    assert code == 1, out
    broken = next(c for c in json.loads(out)["checks"] if c["name"] == "attachments")
    assert broken["status"] == "FAIL"

    # workflow REST and MCP share one producer: an agent reads workflow_get.
    rest_wf = h.rest.get("/workflow?kind=task").json()["data"]
    agent_expect(
        h,
        "tl",
        "调用 workflow_get（kind=task），报告 version 与初始状态。",
        lambda out_: (
            str(rest_wf["version"]) in out_
            and rest_wf["kinds"]["task"]["initial"] in out_
        ),
    )
