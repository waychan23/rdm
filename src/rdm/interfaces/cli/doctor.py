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


def _check_secret_file(path: Path, label: str) -> tuple[str, str]:
    """Return (status, detail) for a bootstrap token/password file."""
    if not path.exists():
        return WARN, f"{label} 缺失（{path}）"
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        return WARN, f"{label} 权限为 {mode:03o}，应为 0600"
    return OK, f"{label} 存在且权限 0600"


def check_bootstrap_credentials(settings: Settings) -> CheckResult:
    """bootstrap-token/bootstrap-password files and their DB consistency."""
    if not settings.db_path.exists():
        return CheckResult("bootstrap", OK, "数据库不存在，跳过")

    engine = create_engine(settings.db_sync_url)
    try:
        with engine.connect() as conn:
            project_count = conn.execute(
                text("select count(*) from project where deleted_at is null")
            ).scalar()
            if not project_count:
                return CheckResult("bootstrap", OK, "尚未 bootstrap（首次 rdm serve 生成）")
            row = conn.execute(
                text(
                    "select p.owner_member_id from project p "
                    "where lower(p.key) = 'rdm' and p.deleted_at is null"
                )
            ).first()
            token_status, token_detail = _check_secret_file(
                settings.bootstrap_token_path, "bootstrap-token"
            )
            pw_status, pw_detail = _check_secret_file(
                settings.bootstrap_password_path, "bootstrap-password"
            )
            db_detail = ""
            if row is not None and row[0]:
                import hashlib

                raw_token = (
                    settings.bootstrap_token_path.read_text(encoding="utf-8").strip()
                    if settings.bootstrap_token_path.exists()
                    else ""
                )
                token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                valid_pat = conn.execute(
                    text(
                        "select 1 from member_token where member_id = :m "
                        "and token_hash = :h and kind = 'pat' and revoked_at is null limit 1"
                    ),
                    {"m": row[0], "h": token_hash},
                ).first()
                if raw_token and valid_pat is None:
                    token_status = WARN
                    db_detail = "；bootstrap-token 与库中有效 PAT 不一致（建议轮换）"
    finally:
        engine.dispose()

    status = (
        FAIL
        if FAIL in (token_status, pw_status)
        else (WARN if WARN in (token_status, pw_status) else OK)
    )
    detail = f"{token_detail}；{pw_detail}{db_detail}"
    return CheckResult("bootstrap", status, detail)


def check_workflow(_settings: Settings) -> CheckResult:
    try:
        spec = load_spec()
    except Exception as exc:  # noqa: BLE001 - any parse failure is a hard FAIL
        return CheckResult("workflow", FAIL, f"workflow.yml 校验失败：{exc}")
    kinds = ", ".join(sorted(spec.kinds))
    return CheckResult("workflow", OK, f"version {spec.version}（{kinds}）")


def check_endpoint(settings: Settings) -> CheckResult:
    url = f"http://{settings.host}:{settings.port}/healthz"
    try:
        response = httpx.get(url, trust_env=False, timeout=3)
        if response.status_code == 200:
            return CheckResult("endpoint", OK, url)
        return CheckResult("endpoint", WARN, f"{url} 返回 {response.status_code}")
    except httpx.HTTPError as exc:
        return CheckResult("endpoint", WARN, f"{url} 不可达：{str(exc)[:160]}")


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
        with engine.connect() as conn:
            rows = conn.execute(
                text("select rel_path, deleted_at is not null from attachment")
            ).all()
    finally:
        engine.dispose()

    missing_live: list[str] = []
    known = set()
    for rel_path, deleted in rows:
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
    return CheckResult("attachments", OK, f"{len(rows)} 条记录，{len(on_disk)} 个文件一致")


def run_checks(settings: Settings, *, include_endpoint: bool = True) -> list[CheckResult]:
    checks = [
        check_data_dir(settings),
        check_database(settings),
        check_bootstrap_credentials(settings),
        check_workflow(settings),
        check_outbox(settings),
        check_attachments(settings),
    ]
    if include_endpoint:
        checks.insert(3, check_endpoint(settings))
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
