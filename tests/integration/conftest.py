"""Integration tests run against the dedicated test workflow contract."""

from __future__ import annotations

import pytest

from tests.workflow_support import install_test_engine


@pytest.fixture(autouse=True)
def _test_workflow_definition(monkeypatch):
    install_test_engine(monkeypatch)
