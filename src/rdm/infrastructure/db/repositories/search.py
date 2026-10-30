"""SQLite FTS5 search adapter (§17 M7).

The virtual table and its triggers are created by migration 0019. This module
is the only place allowed to use FTS5 SQL; callers go through SearchService.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SearchRow:
    entity_type: str
    entity_id: str
    project_id: str
    ref: str
    title: str
    body: str


def _match_expression(query: str) -> str:
    # Phrase each whitespace-separated term; trigram needs >=3 chars, so the
    # caller falls back to LIKE for shorter queries.
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def search(
        self,
        project_ids: Sequence[str],
        query: str,
        *,
        types: Sequence[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchRow]:
        if not project_ids or not query.strip():
            return []
        params: dict[str, object] = {
            "limit": limit,
            "offset": offset,
        }
        placeholders = []
        for i, project_id in enumerate(project_ids):
            key = f"p{i}"
            placeholders.append(f":{key}")
            params[key] = project_id
        filters = [f"project_id IN ({', '.join(placeholders)})"]
        if types:
            type_placeholders = []
            for i, entity_type in enumerate(types):
                key = f"t{i}"
                type_placeholders.append(f":{key}")
                params[key] = entity_type
            filters.append(f"entity_type IN ({', '.join(type_placeholders)})")
        where = " AND ".join(filters)
        if len(query.strip()) >= 3:
            params["match"] = _match_expression(query)
            sql = (
                "SELECT entity_type, entity_id, project_id, ref, title, body "
                "FROM search_index WHERE search_index MATCH :match AND "
                f"{where} ORDER BY rank LIMIT :limit OFFSET :offset"
            )
        else:
            params["like"] = f"%{query.strip()}%"
            sql = (
                "SELECT entity_type, entity_id, project_id, ref, title, body "
                "FROM search_index WHERE (title LIKE :like OR body LIKE :like) AND "
                f"{where} ORDER BY rowid DESC LIMIT :limit OFFSET :offset"
            )
        rows = (await self._s.execute(text(sql), params)).all()
        return [
            SearchRow(
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                project_id=row.project_id,
                ref=row.ref or "",
                title=row.title or "",
                body=row.body or "",
            )
            for row in rows
        ]
