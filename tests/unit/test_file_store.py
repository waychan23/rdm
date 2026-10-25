"""Unit tests for LocalFileStore: streaming hash, size cap, layout, traversal."""

from __future__ import annotations

import hashlib
import io

import pytest

from rdm.domain.errors import AttachmentTooLarge
from rdm.infrastructure.files.local_store import LocalFileStore


class _Stream:
    def __init__(self, data: bytes) -> None:
        self._io = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._io.read(size)


async def test_save_streams_hashes_and_lays_out(tmp_path) -> None:
    store = LocalFileStore(tmp_path / "projects")
    payload = b"hello attachment\n" * 100
    saved = await store.save("pid1", "报告 v1.txt", _Stream(payload), max_bytes=10_000)

    assert saved.size_bytes == len(payload)
    assert saved.sha256 == hashlib.sha256(payload).hexdigest()
    parts = saved.rel_path.split("/")
    assert parts[0] == "pid1"
    assert parts[1] == "attachments"
    assert parts[2].isdigit()  # yyyy
    assert parts[3].endswith("-报告 v1.txt")

    path = store.abspath(saved.rel_path)
    assert path.read_bytes() == payload
    assert store.exists(saved.rel_path)
    # No leftover .part files.
    assert not list(path.parent.glob("*.part"))


async def test_save_over_limit_raises_and_removes_part(tmp_path) -> None:
    store = LocalFileStore(tmp_path / "projects")
    with pytest.raises(AttachmentTooLarge) as exc:
        await store.save("pid1", "big.bin", _Stream(b"x" * 100), max_bytes=10)
    assert exc.value.details["limit"] == 10
    assert list(store.iter_attachment_relpaths()) == []


async def test_traversal_rejected(tmp_path) -> None:
    store = LocalFileStore(tmp_path / "projects")
    with pytest.raises(ValueError):
        store.abspath("../../etc/passwd")
    assert store.exists("../../etc/passwd") is False


async def test_iter_attachment_relpaths(tmp_path) -> None:
    store = LocalFileStore(tmp_path / "projects")
    await store.save("pid1", "a.md", _Stream(b"a"), max_bytes=100)
    await store.save("pid2", "b.md", _Stream(b"bb"), max_bytes=100)
    found = {pid for pid, _rel in store.iter_attachment_relpaths()}
    assert found == {"pid1", "pid2"}
    only_pid1 = {pid for pid, _rel in store.iter_attachment_relpaths("pid1")}
    assert only_pid1 == {"pid1"}
