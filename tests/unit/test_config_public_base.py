"""RDM_PUBLIC_BASE_URL normalization (architecture §17.160)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rdm.config import Settings


def test_empty_falls_back_to_bind_origin(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, public_base_url="")
    assert settings.internal_base_url == "http://127.0.0.1:8765"
    assert settings.base_url == settings.internal_base_url


def test_trailing_slash_is_stripped(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, public_base_url="https://rdm.example.com/")
    assert settings.base_url == "https://rdm.example.com"


def test_loopback_http_is_allowed(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, public_base_url="http://127.0.0.1:5173")
    assert settings.base_url == "http://127.0.0.1:5173"
    assert settings.internal_base_url == "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "value",
    [
        "https://rdm.example.com/app",
        "https://rdm.example.com?x=1",
        "https://rdm.example.com#frag",
        "http://rdm.internal:8080",
        "ftp://rdm.example.com",
    ],
)
def test_invalid_public_origins_are_rejected(tmp_path, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, public_base_url=value)
