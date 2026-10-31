"""CLI/upgrade: seed effective definition versions and backfill items (§17.120)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from rdm.config import Settings
from rdm.domain.workflow.loader import load_spec
from rdm.interfaces.cli.db import run_upgrade
from rdm.interfaces.cli.main import app

runner = CliRunner()


def _db(data_dir: Path) -> Path:
    return Settings(data_dir=data_dir).db_path


def _seed(data_dir: Path) -> None:
    with sqlite3.connect(_db(data_dir)) as conn:
        conn.execute(
            "insert into organization(id,name,event_seq,created_at) "
            "values ('01J00000000000000000000000','默认组织',0,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into project(id,org_id,key,name,status,item_seq,created_at) "
            "values ('p1','01J00000000000000000000000','DEMO','DEMO','active',0,"
            "'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into work_item(id,project_id,display_no,kind,title,status,priority,"
            "rank,workflow_version,custom_fields,row_version,created_at) "
            "values ('w1','p1',1,'task','legacy','TODO',2,0,1,'{}',0,"
            "'2026-10-25 00:00:00')"
        )
        conn.execute("insert into work_item_task(work_item_id,task_type) values ('w1','qa')")


def _count_versions(data_dir: Path) -> int:
    with sqlite3.connect(_db(data_dir)) as conn:
        return conn.execute("select count(*) from work_item_workflow_version").fetchone()[0]


def _bound(data_dir: Path) -> tuple[str | None, int]:
    with sqlite3.connect(_db(data_dir)) as conn:
        return conn.execute(
            "select workflow_def_id, workflow_version from work_item where id='w1'"
        ).fetchone()


def test_init_seeds_current_definitions(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = runner.invoke(app, ["init", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output

    spec = load_spec()
    expected = len(spec.kinds) + len(spec.kinds["task"].subtypes)
    assert _count_versions(data_dir) == expected

    # Idempotent: another upgrade creates no new rows.
    run_upgrade(data_dir)
    assert _count_versions(data_dir) == expected


def test_upgrade_backfills_legacy_items(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    # Stop at 0022 so the new table does not exist yet.
    run_upgrade(data_dir, "0022")
    _seed(data_dir)

    run_upgrade(data_dir)

    def_id, version = _bound(data_dir)
    assert def_id is not None
    assert version == 1
    spec = load_spec()
    with sqlite3.connect(_db(data_dir)) as conn:
        subtype, schema_version, config_version = conn.execute(
            "select subtype, config_schema_version, config_version "
            "from work_item_workflow_version where id=?",
            (def_id,),
        ).fetchone()
    # Alias normalization: raw 'qa' pins to the canonical 'testing' subtype.
    assert subtype == "testing"
    assert schema_version == spec.version
    assert config_version == spec.revision
