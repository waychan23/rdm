"""Direct sqlite assertions (events, projections, deliveries)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def scalar(self, sql: str, params: tuple = ()) -> Any:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def project_id(self, key: str) -> str:
        return self.scalar("select id from project where key=?", (key,))

    def event_types(self, project_key: str) -> set[str]:
        rows = self.query(
            "select distinct event_type from event where project_id="
            "(select id from project where key=?)",
            (project_key,),
        )
        return {r[0] for r in rows}

    def item(self, display_id: str) -> sqlite3.Row | None:
        key, _, no = display_id.partition("-")
        rows = self.query(
            "select wi.* from work_item wi join project p on p.id=wi.project_id "
            "where p.key=? and wi.display_no=?",
            (key, int(no)),
        )
        return rows[0] if rows else None
