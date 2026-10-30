"""Full-text search index (SQLite FTS5, trigram).

The FTS table is SQLite-specific and lives only in the infrastructure search
adapter (§17 M7). Triggers keep it in sync with the four searchable tables so
soft deletes and restores are reflected without application bookkeeping.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WORK_ITEM_INSERT = """
CREATE TRIGGER search_work_item_ai AFTER INSERT ON work_item BEGIN
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  VALUES (
    'work_item', NEW.id, NEW.project_id, CAST(NEW.display_no AS TEXT), NEW.title,
    COALESCE(NEW.description_md, '') || ' ' || COALESCE(NEW.review_content_md, '')
  );
END
"""

WORK_ITEM_UPDATE = """
CREATE TRIGGER search_work_item_au AFTER UPDATE OF
  title, description_md, review_content_md, deleted_at, display_no ON work_item BEGIN
  DELETE FROM search_index WHERE entity_type = 'work_item' AND entity_id = NEW.id;
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  SELECT
    'work_item', NEW.id, NEW.project_id, CAST(NEW.display_no AS TEXT), NEW.title,
    COALESCE(NEW.description_md, '') || ' ' || COALESCE(NEW.review_content_md, '')
  WHERE NEW.deleted_at IS NULL;
END
"""

COMMENT_INSERT = """
CREATE TRIGGER search_comment_ai AFTER INSERT ON comment BEGIN
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  SELECT
    'comment', NEW.id, NEW.project_id,
    CAST(w.display_no AS TEXT), '', NEW.body_md
  FROM work_item w WHERE w.id = NEW.work_item_id AND NEW.deleted_at IS NULL
    AND w.deleted_at IS NULL;
END
"""

COMMENT_UPDATE = """
CREATE TRIGGER search_comment_au AFTER UPDATE OF body_md, deleted_at ON comment BEGIN
  DELETE FROM search_index WHERE entity_type = 'comment' AND entity_id = NEW.id;
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  SELECT
    'comment', NEW.id, NEW.project_id,
    CAST(w.display_no AS TEXT), '', NEW.body_md
  FROM work_item w WHERE w.id = NEW.work_item_id AND NEW.deleted_at IS NULL
    AND w.deleted_at IS NULL;
END
"""

MESSAGE_INSERT = """
CREATE TRIGGER search_message_ai AFTER INSERT ON message BEGIN
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  VALUES ('message', NEW.id, NEW.project_id, '', NEW.subject, NEW.body_md);
END
"""

MESSAGE_UPDATE = """
CREATE TRIGGER search_message_au AFTER UPDATE OF subject, body_md, deleted_at ON message BEGIN
  DELETE FROM search_index WHERE entity_type = 'message' AND entity_id = NEW.id;
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  SELECT 'message', NEW.id, NEW.project_id, '', NEW.subject, NEW.body_md
  WHERE NEW.deleted_at IS NULL;
END
"""

ARTIFACT_INSERT = """
CREATE TRIGGER search_artifact_ai AFTER INSERT ON artifact BEGIN
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  VALUES (
    'artifact', NEW.id, NEW.project_id, '', NEW.label,
    COALESCE(NEW.description_md, '') || ' ' || NEW.url
  );
END
"""

ARTIFACT_UPDATE = """
CREATE TRIGGER search_artifact_au AFTER UPDATE OF
  label, description_md, url, deleted_at ON artifact BEGIN
  DELETE FROM search_index WHERE entity_type = 'artifact' AND entity_id = NEW.id;
  INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body)
  SELECT
    'artifact', NEW.id, NEW.project_id, '', NEW.label,
    COALESCE(NEW.description_md, '') || ' ' || NEW.url
  WHERE NEW.deleted_at IS NULL;
END
"""

DELETE_TRIGGERS = {
    "work_item": """
CREATE TRIGGER search_work_item_ad AFTER DELETE ON work_item BEGIN
  DELETE FROM search_index WHERE entity_type = 'work_item' AND entity_id = OLD.id;
END
""",
    "comment": """
CREATE TRIGGER search_comment_ad AFTER DELETE ON comment BEGIN
  DELETE FROM search_index WHERE entity_type = 'comment' AND entity_id = OLD.id;
END
""",
    "message": """
CREATE TRIGGER search_message_ad AFTER DELETE ON message BEGIN
  DELETE FROM search_index WHERE entity_type = 'message' AND entity_id = OLD.id;
END
""",
    "artifact": """
CREATE TRIGGER search_artifact_ad AFTER DELETE ON artifact BEGIN
  DELETE FROM search_index WHERE entity_type = 'artifact' AND entity_id = OLD.id;
END
""",
}

TRIGGERS = [
    WORK_ITEM_INSERT,
    WORK_ITEM_UPDATE,
    DELETE_TRIGGERS["work_item"],
    COMMENT_INSERT,
    COMMENT_UPDATE,
    DELETE_TRIGGERS["comment"],
    MESSAGE_INSERT,
    MESSAGE_UPDATE,
    DELETE_TRIGGERS["message"],
    ARTIFACT_INSERT,
    ARTIFACT_UPDATE,
    DELETE_TRIGGERS["artifact"],
]


def upgrade() -> None:
    op.execute(
        "CREATE VIRTUAL TABLE search_index USING fts5("
        "entity_type UNINDEXED, entity_id UNINDEXED, project_id UNINDEXED, "
        "ref UNINDEXED, title, body, tokenize='trigram')"
    )
    for sql in TRIGGERS:
        op.execute(sql)
    # Backfill rows that existed before the index was introduced.
    op.execute(
        "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
        "SELECT 'work_item', id, project_id, CAST(display_no AS TEXT), title, "
        "COALESCE(description_md, '') || ' ' || COALESCE(review_content_md, '') "
        "FROM work_item WHERE deleted_at IS NULL"
    )
    op.execute(
        "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
        "SELECT 'comment', c.id, c.project_id, CAST(w.display_no AS TEXT), '', c.body_md "
        "FROM comment c JOIN work_item w ON w.id = c.work_item_id "
        "WHERE c.deleted_at IS NULL AND w.deleted_at IS NULL"
    )
    op.execute(
        "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
        "SELECT 'message', id, project_id, '', subject, body_md "
        "FROM message WHERE deleted_at IS NULL"
    )
    op.execute(
        "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
        "SELECT 'artifact', id, project_id, '', label, "
        "COALESCE(description_md, '') || ' ' || url "
        "FROM artifact WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    for name in (
        "search_work_item_ai",
        "search_work_item_au",
        "search_work_item_ad",
        "search_comment_ai",
        "search_comment_au",
        "search_comment_ad",
        "search_message_ai",
        "search_message_au",
        "search_message_ad",
        "search_artifact_ai",
        "search_artifact_au",
        "search_artifact_ad",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS search_index")
