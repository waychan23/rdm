"""Password hashing for console login (argon2id, architecture §16.55).

Only human members hold a password; agents can never log in to the web
console. Verification is constant-time and reports a uniform failure so the
login endpoint cannot distinguish unknown user from wrong password.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# argon2id default parameters are tuned for interactive login; the encoded
# hash string is self-describing, so parameters can evolve without migration.
_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password(password: str) -> str:
    """Return the password or raise ValueError with a user-facing reason."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码长度至少 {MIN_PASSWORD_LENGTH} 位")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码长度不能超过 {MAX_PASSWORD_LENGTH} 位")
    return password


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def generate_password() -> str:
    """A URL-safe random initial password (32 chars, no whitespace)."""
    return secrets.token_urlsafe(24)


def needs_rehash(password_hash: str) -> bool:
    try:
        return bool(_hasher.check_needs_rehash(password_hash))
    except (InvalidHashError, ValueError):
        return False
