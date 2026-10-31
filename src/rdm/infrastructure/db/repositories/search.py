"""Full-text search adapter.

SQLite uses FTS5 (migration 0019); PostgreSQL uses ParadeDB `pg_search`
BM25 + jieba over the same unified `search_index` table (§17.114). This
module is the only place allowed to use dialect-specific search SQL;
callers go through SearchService.
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


def _pg_query_terms(query: str) -> str:
    """Strip punctuation that would otherwise become stray matched tokens."""
    return " ".join(re.sub(r"[^\w]+", " ", query).split())


def _dialect(session: AsyncSession) -> str:
    bind = session.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


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
        if _dialect(self._s) == "postgresql":
            params, sql = self._postgres_sql(project_ids, query, types, limit, offset)
        else:
            params, sql = self._sqlite_sql(project_ids, query, types, limit, offset)
        if sql is None:
            return []
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

    @staticmethod
    def _filters(
        project_ids: Sequence[str],
        types: Sequence[str] | None,
        params: dict[str, object],
        *,
        prefix: str = "",
    ) -> str:
        placeholders = []
        for i, project_id in enumerate(project_ids):
            key = f"p{i}"
            placeholders.append(f":{key}")
            params[key] = project_id
        filters = [f"{prefix}project_id IN ({', '.join(placeholders)})"]
        if types:
            type_placeholders = []
            for i, entity_type in enumerate(types):
                key = f"t{i}"
                type_placeholders.append(f":{key}")
                params[key] = entity_type
            filters.append(f"{prefix}entity_type IN ({', '.join(type_placeholders)})")
        return " AND ".join(filters)

    def _sqlite_sql(
        self,
        project_ids: Sequence[str],
        query: str,
        types: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> tuple[dict[str, object], str | None]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        where = self._filters(project_ids, types, params)
        q = query.strip()
        if len(q) >= 3:
            params["match"] = _match_expression(query)
            sql = (
                "SELECT entity_type, entity_id, project_id, ref, title, body "
                "FROM search_index WHERE search_index MATCH :match AND "
                f"{where} ORDER BY rank LIMIT :limit OFFSET :offset"
            )
        else:
            params["like"] = f"%{q}%"
            sql = (
                "SELECT entity_type, entity_id, project_id, ref, title, body "
                "FROM search_index WHERE (title LIKE :like OR body LIKE :like) AND "
                f"{where} ORDER BY rowid DESC LIMIT :limit OFFSET :offset"
            )
        return params, sql

    def _postgres_sql(
        self,
        project_ids: Sequence[str],
        query: str,
        types: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> tuple[dict[str, object], str | None]:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        q = query.strip()
        if len(q) >= 3:
            where = self._filters(project_ids, types, params, prefix="si.")
            cleaned = _pg_query_terms(q)
            if not cleaned:
                return params, None
            params["q"] = cleaned
            # ParadeDB Top-K requires LIMIT; OFFSET is applied by the outer page
            # over an inner LIMIT of offset + page size.
            params["inner_limit"] = offset + limit
            sql = (
                "WITH top_results AS ("
                " SELECT si.id, si.entity_type, si.entity_id, si.project_id, si.ref, "
                "si.title, si.body, pdb.score(si.id) AS score"
                " FROM search_index si"
                f" WHERE si.content &&& :q AND {where}"
                " ORDER BY pdb.score(si.id) DESC, si.id DESC"
                " LIMIT :inner_limit"
                ") SELECT entity_type, entity_id, project_id, ref, title, body"
                " FROM top_results ORDER BY score DESC, id DESC"
                " LIMIT :limit OFFSET :offset"
            )
        else:
            # jieba cannot match 1–2 character fragments reliably; keep the
            # same substring fallback as SQLite (sequential scan).
            where = self._filters(project_ids, types, params)
            params["like"] = f"%{q}%"
            sql = (
                "SELECT entity_type, entity_id, project_id, ref, title, body "
                "FROM search_index WHERE (title ILIKE :like OR body ILIKE :like) AND "
                f"{where} ORDER BY id DESC LIMIT :limit OFFSET :offset"
            )
        return params, sql
