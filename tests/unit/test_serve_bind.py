"""Bind validation for `rdm serve` (loopback default, enterprise binds)."""

from __future__ import annotations

import pytest
import typer

from rdm.interfaces.cli.server import build_serve_settings, is_loopback


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_is_loopback(host: str) -> None:
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.5", "rdm.internal"])
def test_is_not_loopback(host: str) -> None:
    assert not is_loopback(host)


def test_loopback_bind_needs_no_public_origin(tmp_path) -> None:
    settings = build_serve_settings(tmp_path, "127.0.0.1", 8765)
    assert settings.host == "127.0.0.1"
    assert settings.public_base_url == ""


def test_non_loopback_bind_requires_public_origin(tmp_path) -> None:
    with pytest.raises(typer.Exit) as exc:
        build_serve_settings(tmp_path, "0.0.0.0", 8765)
    assert exc.value.exit_code == 2


def test_non_loopback_bind_allowed_with_https_origin(tmp_path) -> None:
    settings = build_serve_settings(
        tmp_path, "0.0.0.0", 8765, public_base_url="https://rdm.example.com"
    )
    assert settings.host == "0.0.0.0"
    assert settings.base_url == "https://rdm.example.com"


def test_non_loopback_bind_rejects_plain_http_origin(tmp_path) -> None:
    with pytest.raises(ValueError):
        build_serve_settings(tmp_path, "10.0.0.5", 8765, public_base_url="http://10.0.0.5:8765")
