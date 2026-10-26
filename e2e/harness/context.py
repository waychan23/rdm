"""Shared context handed to every scenario."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from e2e.harness import cli_runner
from e2e.harness.binding import bind_member, cleanup, remove_claude_key
from e2e.harness.db import DB
from e2e.harness.poll import wait_until
from e2e.harness.rest import RestClient
from e2e.harness.server import Server


@dataclass
class AgentCall:
    member: str
    prompt: str
    outputs: dict[str, cli_runner.CliResult] = field(default_factory=dict)


@dataclass
class Harness:
    root: Path
    server: Server
    rest: RestClient
    db: DB
    cli: str
    output_dir: Path
    keep: bool = False
    model: str | None = None
    tokens: dict[str, str] = field(default_factory=dict)
    member_ids: dict[str, str] = field(default_factory=dict)
    workdirs: dict[str, Path] = field(default_factory=dict)
    transcript: list[AgentCall] = field(default_factory=list)

    # --- provisioning (deterministic, management actions go via REST) -----

    def project(self, key: str) -> dict:
        return self.rest.create_project(key)

    def member(
        self,
        project: str,
        name: str,
        *,
        type_: str = "human",
        roles: list[str] | None = None,
        manager: str | None = None,
        webhook: str | None = None,
        fmt: str = "generic",
    ) -> str:
        manager_id = self.member_ids.get(manager) if manager else None
        mid, token = self.rest.create_member(
            project,
            name,
            type_=type_,
            roles=roles,
            manager=manager_id,
            webhook=webhook,
            fmt=fmt,
        )
        self.member_ids[name] = mid
        self.tokens[name] = token
        cwd = self.root / "workdirs" / name
        bind_member(cwd, self.server.base_url + "/mcp", token)
        self.workdirs[name] = cwd
        return token

    def item(self, project: str, payload: dict, member: str | None = None) -> dict:
        return self.rest.create_item(
            project, payload, token=self.tokens[member] if member else None
        )

    # --- agent driving -----------------------------------------------------

    def agent(
        self,
        member: str,
        prompt: str,
        *,
        timeout: int = 180,
        expect_ok: bool = False,
    ) -> cli_runner.CliResult:
        """Drive one headless prompt as the bound member; archives output."""
        cwd = self.workdirs[member]
        result = cli_runner.run(
            self.cli,
            cwd,
            self.tokens[member],
            prompt,
            timeout=timeout,
            model=self.model,
        )
        call = AgentCall(member=member, prompt=prompt, outputs={self.cli: result})
        self.transcript.append(call)
        log_dir = self.output_dir / "prompts"
        log_dir.mkdir(parents=True, exist_ok=True)
        index = len(self.transcript)
        (log_dir / f"{index:02d}-{member}.txt").write_text(
            f"$ {prompt}\n\n{result.stdout}", encoding="utf-8"
        )
        if expect_ok and not result.ok:
            raise AssertionError(f"{member} CLI call failed:\n{result.stdout[-800:]}")
        return result

    def wait(self, predicate: Callable[[], object], message: str, **kw) -> None:
        wait_until(predicate, message=message, **kw)

    # --- teardown ----------------------------------------------------------

    def teardown(self) -> None:
        if not self.keep:
            for _name, cwd in self.workdirs.items():
                remove_claude_key(cwd)
                cleanup(cwd)

    def dump_events(self, project_key: str) -> None:
        types = sorted(self.db.event_types(project_key))
        (self.output_dir / f"events-{project_key}.json").write_text(
            json.dumps(types, ensure_ascii=False, indent=2), encoding="utf-8"
        )
