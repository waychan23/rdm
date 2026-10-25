"""Unit tests for attachment filename/MIME policy (§16.45)."""

from __future__ import annotations

import pytest

from rdm.domain.attachment_policy import (
    BLOCKED_EXTENSIONS,
    ensure_allowed_type,
    extension_of,
    sanitize_filename,
)
from rdm.domain.errors import UnsupportedMime


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.md", "report.md"),
        ("/etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\evil.dll.bak", "evil.dll.bak"),
        ("a/b:c?d*.txt", "b_c_d_.txt"),
        ("  spaced  name .pdf ", "spaced  name .pdf".replace("  ", " ")),
        ("设计稿 v2.fig", "设计稿 v2.fig"),
        ("\x00\x01name", "__name"),
        ("", "attachment"),
        ("   ", "attachment"),
        ("...", "attachment"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_long_filename_keeps_extension() -> None:
    name = "a" * 200 + ".pdf"
    out = sanitize_filename(name)
    assert len(out) <= 120
    assert out.endswith(".pdf")


def test_sanitize_filename_has_no_path_separators() -> None:
    out = sanitize_filename("../x/y/z.patch")
    assert "/" not in out
    assert "\\" not in out


def test_extension_of() -> None:
    assert extension_of("a.tar.gz") == "gz"
    assert extension_of("noext") == ""


@pytest.mark.parametrize("ext", sorted(BLOCKED_EXTENSIONS))
def test_blocked_extensions_rejected(ext: str) -> None:
    with pytest.raises(UnsupportedMime):
        ensure_allowed_type(f"payload.{ext}", None)


@pytest.mark.parametrize(
    "mime",
    [
        "application/x-executable",
        "application/x-sh",
        "application/x-msdownload",
        "application/x-shellscript",
    ],
)
def test_blocked_mime_rejected(mime: str) -> None:
    with pytest.raises(UnsupportedMime):
        ensure_allowed_type("artifact.bin", mime)


@pytest.mark.parametrize(
    ("filename", "mime"),
    [
        ("debug.log", "text/plain"),
        ("bundle.zip", "application/zip"),
        ("screenshot.png", "image/png"),
        ("patch.diff", "text/x-patch"),
        ("README", None),
    ],
)
def test_allowed_types_pass(filename: str, mime: str | None) -> None:
    ensure_allowed_type(filename, mime)
