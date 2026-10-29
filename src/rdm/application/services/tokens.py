"""Opaque credential helpers shared by every token flow (§16.53)."""

from __future__ import annotations

import hashlib
import secrets


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)
