"""argon2 password helpers (architecture §16.55)."""

from __future__ import annotations

import pytest

from rdm.application.services.passwords import (
    generate_password,
    hash_password,
    validate_password,
    verify_password,
)


def test_hash_and_verify_roundtrip() -> None:
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password(h, "correct horse")
    assert not verify_password(h, "wrong horse")


def test_hashes_are_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_handles_garbage_hash() -> None:
    assert verify_password("not-an-argon2-hash", "whatever") is False


def test_generate_password_is_acceptable() -> None:
    raw = generate_password()
    assert len(raw) >= 8
    validate_password(raw)
    assert verify_password(hash_password(raw), raw)


def test_validate_length_bounds() -> None:
    with pytest.raises(ValueError):
        validate_password("short")
    with pytest.raises(ValueError):
        validate_password("x" * 200)
