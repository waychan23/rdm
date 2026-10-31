"""Locale-aware step display names (§17.115).

Step rows and event payloads snapshot both the zh name and (from this change
on) ``name_en``. Old rows only have the zh value, so readers fall back to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rdm.i18n import current_locale


def localized_name(name: str, name_en: str | None = None) -> str:
    if current_locale() == "en" and name_en:
        return name_en
    return name


def step_display_name(name: str, config: Mapping[str, Any] | None = None) -> str:
    """Pick the name stored in a step row/config snapshot."""
    config = config or {}
    english = config.get("name_en")
    return localized_name(name, str(english) if english else None)
