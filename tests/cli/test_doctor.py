"""Tests for `rdm doctor` (M2-7)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from rdm.config import Settings
from rdm.interfaces.cli.doctor import (
    FAIL,
    OK,
    WARN,
    check_attachments,
    check_database,
    check_outbox,
    run_checks,
)
from rdm.interfaces.cli.main import app

runner = CliRunner()


def _seed_project(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "insert into organization(id,name,event_seq,created_at) "
            "values ('01J00000000000000000000000','默认组织',0,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into project(id,org_id,key,name,status,item_seq,created_at) "
            "values ('p1','01J00000000000000000000000','DEMO','DEMO','active',0,"
            "'2026-10-25 00:00:00')"
        )


def test_doctor_happy_path_cli(tmp_path) -> None:
    data_dir = tmp_path / "data"
    assert runner.invoke(app, ["init", "--data-dir", str(data_dir)]).exit_code == 0
    result = runner.invoke(
        app,
        ["doctor", "--data-dir", str(data_dir), "--skip-endpoint"],
    )
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "summary:" in result.output
    assert not any(line.startswith("FAIL") for line in result.output.splitlines())


def test_doctor_json_output(tmp_path) -> None:
    data_dir = tmp_path / "data"
    runner.invoke(app, ["init", "--data-dir", str(data_dir)])
    result = runner.invoke(
        app, ["doctor", "--data-dir", str(data_dir), "--skip-endpoint", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {c["name"] for c in payload["checks"]}
    assert {"data-dir", "database", "workflow", "outbox", "attachments"} <= names


def test_database_check_detects_missing_and_old_revision(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    missing = check_database(settings)
    assert missing.status == FAIL

    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "rdm.db").write_bytes(b"not a db")
    # A garbage sqlite file surfaces as a FAIL, never an exception.
    result = check_database(settings)
    assert result.status == FAIL


def test_attachment_checks_missing_and_dangling(tmp_path) -> None:
    data_dir = tmp_path / "data"
    runner.invoke(app, ["init", "--data-dir", str(data_dir)])
    settings = Settings(data_dir=data_dir)
    _seed_project(settings.db_path)

    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "insert into event(id,org_id,project_id,seq,aggregate_type,aggregate_id,"
            "aggregate_version,event_type,actor_user_id,payload,occurred_at) "
            "values (1,'01J00000000000000000000000','p1',1,'work_item','i1',0,"
            "'work_item.created',null,'{}',"
            "'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into attachment(id,project_id,owner_type,owner_id,"
            "uploader_user_id,filename,mime,size_bytes,sha256,rel_path,created_at) "
            "values ('a1','p1','work_item','i1','m','x.txt','text/plain',1,'h',"
            "'p1/attachments/2026/missing.txt','2026-10-25 00:00:00')"
        )

    missing = check_attachments(settings)
    assert missing.status == FAIL
    assert "missing.txt" in missing.detail

    # Add the file -> healthy; then an unregistered file -> WARN.
    target = settings.projects_dir / "p1" / "attachments" / "2026" / "missing.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    assert check_attachments(settings).status == OK

    orphan = settings.projects_dir / "p1" / "attachments" / "2026" / "orphan.txt"
    orphan.write_bytes(b"y")
    dangling = check_attachments(settings)
    assert dangling.status == WARN
    assert "orphan.txt" in dangling.detail


def test_outbox_thresholds(tmp_path) -> None:
    data_dir = tmp_path / "data"
    runner.invoke(app, ["init", "--data-dir", str(data_dir)])
    settings = Settings(data_dir=data_dir)
    assert check_outbox(settings).status == OK

    # Project row is required by the deferred FK; init leaves no project.
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "insert into organization(id,name,event_seq,created_at) "
            "values ('01J00000000000000000000000','默认组织',0,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into project(id,org_id,key,name,status,item_seq,created_at) "
            "values ('p1','01J00000000000000000000000','DEMO','D','active',0,"
            "'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into event(id,org_id,project_id,seq,aggregate_type,aggregate_id,"
            "aggregate_version,event_type,actor_user_id,payload,occurred_at) "
            "values (2,'01J00000000000000000000000','p1',1,'x','z',0,"
            "'work_item.assigned',null,'{}','2020-01-01 00:00:00')"
        )
        for i in range(3, 53):
            conn.execute(
                "insert into webhook_outbox(id,project_id,event_id,target_url,"
                "format,payload,status,attempts,created_at) values (?,?,1,"
                "'https://x','generic','{}','pending',0,'2020-01-01 00:00:00')",
                (f"o{i}", "p1"),
            )
    warn = check_outbox(settings)
    assert warn.status == WARN and "pending=50" in warn.detail

    # Endpoint probe against a closed port is a WARN, never a FAIL.
    checks = run_checks(Settings(data_dir=data_dir, port=1), include_endpoint=True)
    endpoint = next(c for c in checks if c.name == "endpoint")
    assert endpoint.status == WARN


def test_workflow_validate_cli(tmp_path) -> None:
    data_dir = tmp_path / "data"
    assert runner.invoke(app, ["init", "--data-dir", str(data_dir)]).exit_code == 0
    result = runner.invoke(app, ["workflow", "validate", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "revision 17" in result.output
    assert "workflow-data" in result.output


def test_workflow_validate_rejects_unknown_active_step(tmp_path) -> None:
    data_dir = tmp_path / "data"
    assert runner.invoke(app, ["init", "--data-dir", str(data_dir)]).exit_code == 0
    db = data_dir / "rdm.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "insert into organization(id,name,event_seq,created_at) "
            "values ('org1','默认组织',0,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into project(id,org_id,key,name,status,item_seq,created_at) "
            "values ('p1','org1','DEMO','DEMO','active',1,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into work_item(id,project_id,display_no,kind,status,title,priority,rank,"
            "workflow_version,row_version,created_at,custom_fields) "
            "values ('w1','p1',1,'task','TODO','t',3,0,1,0,'2026-10-25 00:00:00','{}')"
        )
        conn.execute(
            "insert into work_item_step(id,project_id,work_item_id,step_key,step_name,"
            "from_status,to_status,mode,status,required_count,row_version,config,created_at) "
            "values ('s1','p1','w1','GONE','Gone','TODO','IN_PROGRESS','direct','PENDING',"
            "1,0,'{}','2026-10-25 00:00:00')"
        )
    result = runner.invoke(app, ["workflow", "validate", "--data-dir", str(data_dir)])
    assert result.exit_code == 1, result.output
    assert "GONE" in result.output
