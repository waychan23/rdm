"""Local filesystem attachment store.

Layout under the projects root (architecture §9):
    projects/<project_id>/attachments/<yyyy>/<ulid>-<sanitized-name>

Files are first written as ``<final>.part`` and atomically renamed on success,
shrinking the crash window between DB row and on-disk file. The DB stores only
data-dir-relative paths; every read resolves the path back inside the store
root (traversal protection, §16.45).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdm.domain.attachment_policy import sanitize_filename
from rdm.domain.errors import AttachmentTooLarge
from rdm.infrastructure.id import new_id

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class SavedFile:
    rel_path: str
    size_bytes: int
    sha256: str


class LocalFileStore:
    """Root is the data-dir ``projects`` directory."""

    def __init__(self, projects_root: Path) -> None:
        self._root = projects_root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, rel_path: str) -> Path:
        target = (self._root / rel_path).resolve()
        if self._root != target and self._root not in target.parents:
            # A relative path escaping the store root must never reach disk.
            raise ValueError(f"attachment path escapes the store root: {rel_path!r}")
        return target

    def abspath(self, rel_path: str) -> Path:
        return self._resolve(rel_path)

    def exists(self, rel_path: str) -> bool:
        try:
            return self._resolve(rel_path).is_file()
        except ValueError:
            return False

    async def save(
        self,
        project_id: str,
        filename: str,
        stream: Any,
        *,
        max_bytes: int,
    ) -> SavedFile:
        safe_name = sanitize_filename(filename)
        year = str(dt.datetime.now(dt.UTC).year)
        rel = Path(project_id) / "attachments" / year / f"{new_id()}-{safe_name}"
        final = self._resolve(rel.as_posix())
        final.parent.mkdir(parents=True, exist_ok=True)
        part = final.with_name(final.name + ".part")

        hasher = hashlib.sha256()
        size = 0
        try:
            with part.open("wb") as out:
                while True:
                    chunk = await stream.read(_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise AttachmentTooLarge(
                            f"附件超过大小上限 {max_bytes} 字节（20MB）；请压缩或拆分后再传。",
                            details={"limit": max_bytes, "size": size},
                        )
                    hasher.update(chunk)
                    out.write(chunk)
            os.replace(part, final)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                part.unlink()
            raise
        return SavedFile(rel_path=rel.as_posix(), size_bytes=size, sha256=hasher.hexdigest())

    def iter_attachment_relpaths(self, project_id: str | None = None) -> Iterable[tuple[str, str]]:
        """Yield (project_id, rel_path) for every non-.part file on disk."""
        if project_id is None:
            base, pattern = self._root, "*/attachments/*/*"
        else:
            base, pattern = self._root / project_id, "attachments/*/*"
        if not base.exists():
            return
        for path in sorted(base.glob(pattern)):
            if not path.is_file() or path.name.endswith(".part"):
                continue
            pid = path.relative_to(self._root).parts[0]
            yield pid, path.relative_to(self._root).as_posix()
