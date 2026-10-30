"""`rdm doctor`: environment/database/webhook/attachment diagnostics.

Check functions are pure-ish (inject settings, return results) so they are
easy to unit-test. Thresholds are fixed in architecture §16.50:
- outbox pending >= 50 or oldest pending older than 1h -> WARN; >= 200 -> FAIL
- any failed outbox row -> WARN
- live attachment row with missing file -> FAIL
- on-disk file without any attachment row (incl. deleted) -> WARN
- server endpoint unreachable -> WARN; everything else failing -> FAIL
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from rdm.config import Settings
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_spec
from rdm.infrastructure.files.local_store import LocalFileStore

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

PENDING_WARN, PENDING_FAIL = 50, 200
PENDING_AGE_WARN = dt.timedelta(hours=1)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _alembic_config(settings: Settings) -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = settings.db_sync_url
    return cfg


def check_data_dir(settings: Settings) -> CheckResult:
    data_dir = settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, delete=True) as probe:
            probe.write(b"ok")
            probe.flush()
        projects = settings.projects_dir
        projects.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CheckResult("data-dir", FAIL, f"{data_dir} 不可写：{exc}")
    return CheckResult("data-dir", OK, str(data_dir))


def check_database(settings: Settings) -> CheckResult:
    db_path: Path = settings.db_path
    if not db_path.exists():
        return CheckResult("database", FAIL, "rdm.db 不存在（先运行 rdm init）")
    cfg = _alembic_config(settings)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(settings.db_sync_url)
    try:
        with engine.connect() as conn:
            if "alembic_version" not in inspect(conn).get_table_names():
                return CheckResult("database", FAIL, "缺少 alembic_version（先运行 rdm init）")
            current = MigrationContext.configure(conn).get_current_heads()
    except Exception as exc:  # noqa: BLE001 - corrupt file is a diagnostic FAIL
        return CheckResult("database", FAIL, f"数据库无法读取：{str(exc)[:160]}")
    finally:
        engine.dispose()
    current_label = ", ".join(current) if current else "(empty)"
    if tuple(current) != (head,):
        return CheckResult(
            "database", FAIL, f"current={current_label} head={head}（需要 db upgrade）"
        )
    return CheckResult("database", OK, f"revision {current_label}")


def check_bootstrap(settings: Settings) -> CheckResult:
    """Organization bootstrap state (no secret files any more, §17)."""
    if not settings.db_path.exists():
        return CheckResult("bootstrap", OK, "数据库不存在，跳过")

    engine = create_engine(settings.db_sync_url)
    try:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            if "organization" not in tables:
                return CheckResult("bootstrap", FAIL, "数据库结构过旧：需要 rdm db upgrade")
            org = conn.execute(text("select count(*) from organization")).scalar()
            if not org:
                return CheckResult("bootstrap", OK, "尚未 bootstrap（首次 rdm serve 生成）")
            owners = conn.execute(
                text(
                    "select id, name, password_hash, must_reset_password, is_active "
                    "from users where deleted_at is null and type = 'human' "
                    "and org_roles like '%org_owner%'"
                )
            ).all()
            if len(owners) != 1:
                return CheckResult(
                    "bootstrap", FAIL, f"应有且仅有 1 个 Org Owner，实际 {len(owners)} 个"
                )
            owner = owners[0]
            if not owner.is_active:
                return CheckResult("bootstrap", FAIL, "Org Owner 已停用")
            if owner.password_hash is None or owner.must_reset_password:
                pending = conn.execute(
                    text(
                        "select count(*) from password_set_token "
                        "where user_id = :u and kind = 'bootstrap' "
                        "and consumed_at is null and expires_at > CURRENT_TIMESTAMP"
                    ),
                    {"u": owner.id},
                ).scalar()
                if pending:
                    return CheckResult(
                        "bootstrap", WARN, "Org Owner 尚未设置密码（bootstrap-url 应在日志中）"
                    )
                return CheckResult(
                    "bootstrap",
                    WARN,
                    "Org Owner 尚未设置密码且 bootstrap-url 已失效；执行 rdm account recover-owner",
                )
            return CheckResult("bootstrap", OK, f"Org Owner {owner.name} 已就绪")
    finally:
        engine.dispose()


def check_workflow(_settings: Settings) -> CheckResult:
    try:
        spec = load_spec()
    except Exception as exc:  # noqa: BLE001 - any parse failure is a hard FAIL
        return CheckResult("workflow", FAIL, f"workflow.json5 校验失败：{exc}")
    kinds = ", ".join(sorted(spec.kinds))
    return CheckResult(
        "workflow", OK, f"version {spec.version} revision {spec.revision}（{kinds}）"
    )


def check_workflow_data(settings: Settings) -> CheckResult:
    """In-flight items and active steps must still exist in the current definition."""
    try:
        spec = load_spec()
        engine = WorkflowEngine(spec)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("workflow-data", FAIL, f"workflow.json5 校验失败：{exc}")
    if not settings.db_path.exists():
        return CheckResult("workflow-data", OK, "数据库不存在，跳过")
    engine = WorkflowEngine(spec)
    issues: list[str] = []
    engine_conn = create_engine(settings.db_sync_url)
    try:
        with engine_conn.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            if "work_item" not in tables:
                return CheckResult("workflow-data", OK, "工作项表不存在，跳过")
            rows = conn.execute(
                text(
                    "select distinct w.kind, w.status, t.task_type from work_item w "
                    "left join work_item_task t on t.work_item_id = w.id "
                    "where w.deleted_at is null"
                )
            ).all()
            for kind, status, task_type in rows:
                try:
                    engine.resolve(kind, task_type)
                    engine.allowed(kind, status, task_type=task_type)
                except Exception:  # noqa: BLE001
                    issues.append(f"{kind}/{task_type or '-'} 状态 {status} 不在当前定义")
            if "work_item_step" in tables:
                steps = conn.execute(
                    text(
                        "select s.step_key, s.from_status, w.kind, t.task_type, "
                        "w.display_no, p.key "
                        "from work_item_step s join work_item w on w.id = s.work_item_id "
                        "left join work_item_task t on t.work_item_id = w.id "
                        "join project p on p.id = w.project_id "
                        "where s.status in ('PENDING','BLOCKED') and w.deleted_at is null"
                    )
                ).all()
                for step_key, from_status, kind, task_type, display_no, project_key in steps:
                    try:
                        keys = {
                            step.key
                            for step in engine.steps_from(kind, from_status, task_type=task_type)
                        }
                    except Exception:  # noqa: BLE001
                        keys = set()
                    if step_key not in keys:
                        issues.append(
                            f"{project_key}-{display_no} 的活动步骤 {step_key} 在当前定义中不存在"
                        )
            stale = conn.execute(
                text(
                    "select count(*) from work_item "
                    "where deleted_at is null and workflow_version <> :rev"
                ),
                {"rev": spec.revision},
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("workflow-data", FAIL, f"工作流数据校验失败：{str(exc)[:160]}")
    finally:
        engine_conn.dispose()
    if issues:
        return CheckResult(
            "workflow-data",
            FAIL,
            f"revision {spec.revision}；" + "；".join(issues[:8]),
        )
    detail = f"revision {spec.revision}；活动步骤均存在于当前定义"
    if stale:
        detail += f"；{stale} 个工作项停留在旧修订（可继续操作）"
    return CheckResult("workflow-data", OK, detail)


def check_endpoint(settings: Settings) -> CheckResult:
    url = f"http://{settings.host}:{settings.port}/healthz"
    try:
        response = httpx.get(url, trust_env=False, timeout=3)
        if response.status_code == 200:
            return CheckResult("endpoint", OK, url)
        return CheckResult("endpoint", WARN, f"{url} 返回 {response.status_code}")
    except httpx.HTTPError as exc:
        return CheckResult("endpoint", WARN, f"{url} 不可达：{str(exc)[:160]}")


def check_oauth_metadata(settings: Settings) -> CheckResult:
    url = f"http://{settings.host}:{settings.port}/.well-known/oauth-protected-resource/mcp"
    try:
        response = httpx.get(url, trust_env=False, timeout=3)
        if response.status_code == 200:
            return CheckResult("oauth", OK, url)
        return CheckResult("oauth", WARN, f"{url} 返回 {response.status_code}")
    except httpx.HTTPError as exc:
        return CheckResult("oauth", WARN, f"{url} 不可达：{str(exc)[:120]}")


def check_outbox(settings: Settings) -> CheckResult:
    if not settings.db_path.exists():
        return CheckResult("outbox", WARN, "数据库不存在，跳过")
    engine = create_engine(settings.db_sync_url)
    try:
        with engine.connect() as conn:
            counts = dict(
                conn.execute(
                    text("select status, count(*) from webhook_outbox group by status")
                ).all()
            )
            oldest = conn.execute(
                text("select min(created_at) from webhook_outbox where status='pending'")
            ).scalar()
    finally:
        engine.dispose()
    pending = int(counts.get("pending", 0))
    failed = int(counts.get("failed", 0))
    delivered = int(counts.get("delivered", 0))
    detail = f"pending={pending} failed={failed} delivered={delivered}"

    oldest_dt = dt.datetime.fromisoformat(oldest) if oldest else None
    if oldest_dt is not None and oldest_dt.tzinfo is None:
        oldest_dt = oldest_dt.replace(tzinfo=dt.UTC)
    age = dt.datetime.now(dt.UTC) - oldest_dt if oldest_dt else None

    status = OK
    if pending >= PENDING_FAIL:
        status = FAIL
    elif pending >= PENDING_WARN or (age is not None and age > PENDING_AGE_WARN) or failed:
        status = WARN
    return CheckResult("outbox", status, detail)


def check_attachments(settings: Settings) -> CheckResult:
    if not settings.db_path.exists():
        return CheckResult("attachments", WARN, "数据库不存在，跳过")
    store = LocalFileStore(settings.projects_dir)
    engine = create_engine(settings.db_sync_url)
    try:
        inspector = inspect(engine)
        if not inspector.has_table("attachment"):
            return CheckResult("attachments", WARN, "attachment 表不存在，跳过")
        columns = {col["name"] for col in inspector.get_columns("attachment")}
        state_expr = "state" if "state" in columns else "'active'"
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "select rel_path, deleted_at is not null, "
                    f"{state_expr}, created_at from attachment"
                )
            ).all()
    finally:
        engine.dispose()

    missing_live: list[str] = []
    known = set()
    for rel_path, deleted, _state, _created in rows:
        known.add(rel_path)
        if not deleted and not store.exists(rel_path):
            missing_live.append(rel_path)
    if missing_live:
        sample = ", ".join(Path(p).name for p in missing_live[:3])
        return CheckResult(
            "attachments",
            FAIL,
            f"{len(missing_live)} 条有效附件记录的文件缺失（如 {sample}）",
        )
    on_disk = {rel for _pid, rel in store.iter_attachment_relpaths()}
    dangling = sorted(on_disk - known)
    if dangling:
        return CheckResult(
            "attachments",
            WARN,
            f"{len(dangling)} 个磁盘文件无附件记录（如 {Path(dangling[0]).name}）",
        )
    temp_rows = [
        (created, rel_path)
        for rel_path, deleted, state, created in rows
        if not deleted and state == "temp"
    ]
    if temp_rows:
        oldest = min(str(created) for created, _rel in temp_rows)

        def _stale(value: object) -> bool:
            try:
                parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return False
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return dt.datetime.now(dt.UTC) - parsed > dt.timedelta(hours=24)

        stale = [row for row in temp_rows if _stale(row[0])]
        if stale:
            return CheckResult(
                "attachments",
                WARN,
                f"{len(stale)} 个编辑器草稿图片超过 24h 未提交（最早 {oldest}），等待后续 GC",
            )
        return CheckResult(
            "attachments",
            OK,
            f"{len(rows)} 条记录，{len(on_disk)} 个文件一致；{len(temp_rows)} 个 temp 草稿待提交",
        )
    return CheckResult("attachments", OK, f"{len(rows)} 条记录，{len(on_disk)} 个文件一致")


def run_checks(settings: Settings, *, include_endpoint: bool = True) -> list[CheckResult]:
    checks = [
        check_data_dir(settings),
        check_database(settings),
        check_bootstrap(settings),
        check_workflow(settings),
        check_workflow_data(settings),
        check_outbox(settings),
        check_attachments(settings),
    ]
    if include_endpoint:
        checks.insert(3, check_endpoint(settings))
        checks.insert(4, check_oauth_metadata(settings))
    return checks


def run_doctor(settings: Settings, *, as_json: bool = False, include_endpoint: bool = True) -> int:
    results = run_checks(settings, include_endpoint=include_endpoint)
    if as_json:
        payload: dict[str, Any] = {
            "data_dir": str(settings.data_dir),
            "checks": [asdict(r) for r in results],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"rdm doctor — {settings.data_dir}")
        for result in results:
            print(f"{result.status:4s} {result.name:<12s} {result.detail}")
        ok_n = sum(1 for r in results if r.status == OK)
        warn_n = sum(1 for r in results if r.status == WARN)
        fail_n = sum(1 for r in results if r.status == FAIL)
        print(f"summary: {ok_n} OK, {warn_n} WARN, {fail_n} FAIL")
    return 1 if any(r.status == FAIL for r in results) else 0
