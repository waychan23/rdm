"""Attachment safety policy: filename sanitization and executable blacklist.

Pure functions (no I/O) so the rules are trivially unit-testable.
Ruling §16.45: 20MB hard cap; executable-type extension/MIME blacklist,
everything else allowed; client-declared MIME is recorded but never trusted.
"""

from __future__ import annotations

import os
import re

from rdm.domain.errors import UnsupportedMime

# Executable / installer types rejected on a loopback single-user deployment.
BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "exe",
        "dll",
        "so",
        "dylib",
        "dmg",
        "app",
        "bat",
        "cmd",
        "ps1",
        "vbs",
        "scr",
        "msi",
        "com",
        "sh",
        "run",
    }
)

_BLOCKED_MIME_MARKERS = (
    "x-executable",
    "x-dosexec",
    "x-msdownload",
    "x-msi",
    "x-sh",
    "x-shellscript",
)

_FORBIDDEN_CHARS_RE = re.compile(r'[\x00-\x1f/\\:*?"<>|]')
_WHITESPACE_RE = re.compile(r"\s+")

# Markdown image links produced by the web editor point at the authenticated
# download endpoint. Only these ids are promoted temp -> active on save.
_ATTACHMENT_URL_RE = re.compile(
    r"/api/v1/attachments/(?P<id>[A-Za-z0-9]{10,32})/(?:download|content)"
)

MAX_FILENAME_LEN = 120


def extract_attachment_ids(*texts: str | None) -> set[str]:
    """Collect attachment ids referenced by markdown/HTML content."""
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        found.update(match.group("id") for match in _ATTACHMENT_URL_RE.finditer(text))
    return found


def sanitize_filename(name: str) -> str:
    """Return a safe single-path-component filename (Unicode preserved)."""
    # Strip any directory component from both POSIX and Windows-style paths.
    name = os.path.basename(str(name).replace("\\", "/"))
    name = _FORBIDDEN_CHARS_RE.sub("_", name)
    name = _WHITESPACE_RE.sub(" ", name).strip(" .")
    if len(name) > MAX_FILENAME_LEN:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_FILENAME_LEN - len(ext)] + ext
    if not name or name in {".", ".."}:
        return "attachment"
    return name


def extension_of(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def ensure_allowed_type(filename: str, mime: str | None) -> None:
    """Raise UnsupportedMime for blacklisted extensions or declared MIME types."""
    ext = extension_of(filename)
    if ext in BLOCKED_EXTENSIONS:
        raise UnsupportedMime(
            f"扩展名 .{ext} 属于可执行类型，v1 禁止上传；请打包为允许的归档格式。",
            details={"filename": filename, "extension": ext},
        )
    if mime:
        declared = mime.lower().split(";", 1)[0].strip()
        if declared.startswith("application/") and any(
            marker in declared for marker in _BLOCKED_MIME_MARKERS
        ):
            raise UnsupportedMime(
                f"声明的 MIME 类型 {mime} 属于可执行类型，禁止上传。",
                details={"filename": filename, "mime": mime},
            )
