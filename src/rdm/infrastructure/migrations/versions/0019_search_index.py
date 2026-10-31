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


PG_TABLE = """
CREATE EXTENSION IF NOT EXISTS pg_search CASCADE;

CREATE TABLE search_index (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type varchar(16) NOT NULL,
    entity_id   varchar(32) NOT NULL,
    project_id  varchar(32) NOT NULL,
    ref         varchar(32) NOT NULL DEFAULT '',
    title       text        NOT NULL DEFAULT '',
    body        text        NOT NULL DEFAULT '',
    content     text GENERATED ALWAYS AS (
        coalesce(title, '') || ' ' || coalesce(body, '')
    ) STORED,
    CONSTRAINT ux_search_index_entity UNIQUE (entity_type, entity_id)
);

CREATE INDEX ix_search_index_bm25 ON search_index
USING paradedb (
    id,
    (content::pdb.jieba),
    (entity_type::pdb.literal),
    (project_id::pdb.literal)
);
"""

PG_SYNC_FUNCTIONS = {
    "work_item": """
CREATE OR REPLACE FUNCTION search_work_item_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    DELETE FROM search_index WHERE entity_type = 'work_item' AND entity_id = OLD.id;
    RETURN OLD;
  END IF;
  DELETE FROM search_index WHERE entity_type = 'work_item' AND entity_id = NEW.id;
  IF NEW.deleted_at IS NULL THEN
    INSERT INTO search_index (entity_type, entity_id, project_id, ref, title, body)
    VALUES (
      'work_item', NEW.id, NEW.project_id, NEW.display_no::text, NEW.title,
      coalesce(NEW.description_md, '') || ' ' || coalesce(NEW.review_content_md, '')
    );
  END IF;
  RETURN NEW;
END $$;
""",
    "comment": """
CREATE OR REPLACE FUNCTION search_comment_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    DELETE FROM search_index WHERE entity_type = 'comment' AND entity_id = OLD.id;
    RETURN OLD;
  END IF;
  DELETE FROM search_index WHERE entity_type = 'comment' AND entity_id = NEW.id;
  IF NEW.deleted_at IS NULL THEN
    INSERT INTO search_index (entity_type, entity_id, project_id, ref, title, body)
    SELECT 'comment', NEW.id, NEW.project_id, w.display_no::text, '', NEW.body_md
    FROM work_item w
    WHERE w.id = NEW.work_item_id AND w.deleted_at IS NULL;
  END IF;
  RETURN NEW;
END $$;
""",
    "message": """
CREATE OR REPLACE FUNCTION search_message_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    DELETE FROM search_index WHERE entity_type = 'message' AND entity_id = OLD.id;
    RETURN OLD;
  END IF;
  DELETE FROM search_index WHERE entity_type = 'message' AND entity_id = NEW.id;
  IF NEW.deleted_at IS NULL THEN
    INSERT INTO search_index (entity_type, entity_id, project_id, ref, title, body)
    VALUES ('message', NEW.id, NEW.project_id, '', NEW.subject, NEW.body_md);
  END IF;
  RETURN NEW;
END $$;
""",
    "artifact": """
CREATE OR REPLACE FUNCTION search_artifact_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    DELETE FROM search_index WHERE entity_type = 'artifact' AND entity_id = OLD.id;
    RETURN OLD;
  END IF;
  DELETE FROM search_index WHERE entity_type = 'artifact' AND entity_id = NEW.id;
  IF NEW.deleted_at IS NULL THEN
    INSERT INTO search_index (entity_type, entity_id, project_id, ref, title, body)
    VALUES (
      'artifact', NEW.id, NEW.project_id, '', NEW.label,
      coalesce(NEW.description_md, '') || ' ' || NEW.url
    );
  END IF;
  RETURN NEW;
END $$;
""",
}

PG_TRIGGERS = [
    """CREATE TRIGGER search_work_item_ai AFTER INSERT ON work_item
       FOR EACH ROW EXECUTE FUNCTION search_work_item_sync()""",
    """CREATE TRIGGER search_work_item_au AFTER UPDATE OF
       title, description_md, review_content_md, deleted_at, display_no ON work_item
       FOR EACH ROW EXECUTE FUNCTION search_work_item_sync()""",
    """CREATE TRIGGER search_work_item_ad AFTER DELETE ON work_item
       FOR EACH ROW EXECUTE FUNCTION search_work_item_sync()""",
    """CREATE TRIGGER search_comment_ai AFTER INSERT ON comment
       FOR EACH ROW EXECUTE FUNCTION search_comment_sync()""",
    """CREATE TRIGGER search_comment_au AFTER UPDATE OF body_md, deleted_at ON comment
       FOR EACH ROW EXECUTE FUNCTION search_comment_sync()""",
    """CREATE TRIGGER search_comment_ad AFTER DELETE ON comment
       FOR EACH ROW EXECUTE FUNCTION search_comment_sync()""",
    """CREATE TRIGGER search_message_ai AFTER INSERT ON message
       FOR EACH ROW EXECUTE FUNCTION search_message_sync()""",
    """CREATE TRIGGER search_message_au AFTER UPDATE OF subject, body_md, deleted_at ON message
       FOR EACH ROW EXECUTE FUNCTION search_message_sync()""",
    """CREATE TRIGGER search_message_ad AFTER DELETE ON message
       FOR EACH ROW EXECUTE FUNCTION search_message_sync()""",
    """CREATE TRIGGER search_artifact_ai AFTER INSERT ON artifact
       FOR EACH ROW EXECUTE FUNCTION search_artifact_sync()""",
    """CREATE TRIGGER search_artifact_au AFTER UPDATE OF label, description_md, url, deleted_at
       ON artifact FOR EACH ROW EXECUTE FUNCTION search_artifact_sync()""",
    """CREATE TRIGGER search_artifact_ad AFTER DELETE ON artifact
       FOR EACH ROW EXECUTE FUNCTION search_artifact_sync()""",
]

PG_BACKFILL = [
    "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
    "SELECT 'work_item', id, project_id, display_no::text, title, "
    "coalesce(description_md, '') || ' ' || coalesce(review_content_md, '') "
    "FROM work_item WHERE deleted_at IS NULL",
    "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
    "SELECT 'comment', c.id, c.project_id, w.display_no::text, '', c.body_md "
    "FROM comment c JOIN work_item w ON w.id = c.work_item_id "
    "WHERE c.deleted_at IS NULL AND w.deleted_at IS NULL",
    "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
    "SELECT 'message', id, project_id, '', subject, body_md "
    "FROM message WHERE deleted_at IS NULL",
    "INSERT INTO search_index(entity_type, entity_id, project_id, ref, title, body) "
    "SELECT 'artifact', id, project_id, '', label, "
    "coalesce(description_md, '') || ' ' || url "
    "FROM artifact WHERE deleted_at IS NULL",
]


def _upgrade_sqlite() -> None:
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


def _upgrade_postgres() -> None:
    """ParadeDB pg_search: one BM25 index with jieba over the unified table."""
    op.execute(PG_TABLE)
    for sql in PG_SYNC_FUNCTIONS.values():
        op.execute(sql)
    for sql in PG_TRIGGERS:
        op.execute(sql)
    for sql in PG_BACKFILL:
        op.execute(sql)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _upgrade_postgres()
    else:
        _upgrade_sqlite()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for source in ("work_item", "comment", "message", "artifact"):
            op.execute(f"DROP TRIGGER IF EXISTS search_{source}_ai ON {source}")
            op.execute(f"DROP TRIGGER IF EXISTS search_{source}_au ON {source}")
            op.execute(f"DROP TRIGGER IF EXISTS search_{source}_ad ON {source}")
            op.execute(f"DROP FUNCTION IF EXISTS search_{source}_sync() CASCADE")
        op.execute("DROP TABLE IF EXISTS search_index")
        return
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
