#!/usr/bin/env python3
"""Run the S1–S10 acceptance scenarios through real agent CLIs.

Each CLI run gets a fresh data dir and server subprocess; management actions
(project/member/token setup) are deterministic REST calls, agentic actions
are headless CLI prompts (claude -p / opencode run), and every assertion lands
on sqlite state/events. Missing CLIs SKIP the whole run instead of failing.

Usage:
    python e2e/run_e2e.py --cli claude,opencode [--scenarios S1,S2]
        [--no-cleanup] [--strict]
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

# Allow `python e2e/run_e2e.py` from the repo root without packaging.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e.harness import cli_runner  # noqa: E402
from e2e.harness.context import Harness  # noqa: E402
from e2e.harness.db import DB  # noqa: E402
from e2e.harness.rest import RestClient  # noqa: E402
from e2e.harness.server import start_server  # noqa: E402

SCENARIOS = [
    ("S1", "s01_identity"),
    ("S2", "s02_hierarchy"),
    ("S3", "s03_sprint"),
    ("S4", "s04_agent_handoff"),
    ("S5", "s05_mailbox"),
    ("S6", "s06_story_gate"),
    ("S7", "s07_issue"),
    ("S8", "s08_illegal_matrix"),
    ("S9", "s09_webhook"),
    ("S10", "s10_doctor"),
]


@dataclass
class ScenarioResult:
    key: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


@dataclass
class RunReport:
    cli: str
    results: list[ScenarioResult] = field(default_factory=list)


def run_one_cli(cli: str, scenarios: list[str], out_root: Path, keep: bool) -> RunReport:
    root = out_root / cli
    root.mkdir(parents=True, exist_ok=True)
    report = RunReport(cli=cli)
    server = None
    h = None
    try:
        server = start_server(root, log_path=root / "server.log")
        rest = RestClient(server.base_url, server.owner_token)
        h = Harness(
            root=root,
            server=server,
            rest=rest,
            db=DB(server.data_dir / "rdm.db"),
            cli=cli,
            output_dir=root,
            keep=keep,
        )
        for key, module_name in SCENARIOS:
            if scenarios and key not in scenarios:
                continue
            started = time.time()
            try:
                module = importlib.import_module(f"e2e.scenarios.{module_name}")
                module.run(h)
                h.dump_events(key)
                report.results.append(ScenarioResult(key, "PASS", f"{time.time() - started:.0f}s"))
                print(f"  {key} PASS ({time.time() - started:.0f}s)")
            except Exception as exc:  # noqa: BLE001 - record and continue
                traceback.print_exc()
                report.results.append(ScenarioResult(key, "FAIL", str(exc)[:300]))
                print(f"  {key} FAIL: {exc}")
    finally:
        if h is not None:
            h.rest.close()
            h.teardown()
        if server is not None:
            server.stop()
        if not keep:
            # Keep server.log and transcripts, drop the bulky data dir.
            shutil.rmtree(root / "data", ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cli",
        default="claude,opencode",
        help="Comma-separated CLIs to exercise (claude/opencode)",
    )
    parser.add_argument("--scenarios", default="", help="Comma subset, e.g. S1,S10")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reserved for CI: treat SKIPPED runs as failures",
    )
    args = parser.parse_args()

    wanted = [c.strip() for c in args.cli.split(",") if c.strip()]
    detected = cli_runner.detect()
    print("detected CLIs:", {k: v.version for k, v in detected.items()})
    selected = [c for c in wanted if c in detected]
    missing = [c for c in wanted if c not in detected]
    if missing:
        print(f"SKIP: CLI not found: {', '.join(missing)}")
    if not selected:
        print("no runnable CLI; nothing to do")
        return 1 if args.strict else 0

    scenarios = {s.strip().upper() for s in args.scenarios.split(",") if s.strip()}
    out_root = Path("e2e/out") / time.strftime("%Y%m%d-%H%M%S")
    out_root.mkdir(parents=True, exist_ok=True)

    reports = [run_one_cli(cli, sorted(scenarios), out_root, args.no_cleanup) for cli in selected]
    print("\n=== e2e summary ===")
    failed = 0
    for report in reports:
        for r in report.results:
            print(f"{report.cli:9s} {r.key:4s} {r.status:5s} {r.detail}")
            if r.status == "FAIL":
                failed += 1
    print(f"\nartifacts: {out_root}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
