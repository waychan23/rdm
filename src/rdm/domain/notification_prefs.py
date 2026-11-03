"""Notification channel preferences (RDM-131).

Preferences are stored per channel: ``inapp`` (the notification/todo inbox),
``email`` and ``webhook``. Missing keys mean "enabled", preserving the
pre-RDM-131 behaviour. The legacy flat shape (``{"assignment": False}``) is
still honoured as in-app preferences so existing rows keep their meaning.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

INAPP_TYPES: tuple[str, ...] = (
    "assignment",
    "step",
    "comment",
    "mention",
    "system",
)
# The mailbox is already in-app by definition, so "mail" only exists for the
# outbound channels.
OUTBOUND_TYPES: tuple[str, ...] = ("mail", *INAPP_TYPES)
CHANNEL_TYPES: dict[str, tuple[str, ...]] = {
    "inapp": INAPP_TYPES,
    "email": OUTBOUND_TYPES,
    "webhook": OUTBOUND_TYPES,
}


def channel_enabled(prefs: Mapping[str, Any], channel: str, kind: str) -> bool:
    """Whether ``kind`` is enabled on ``channel``; unknown/missing = enabled."""
    types = CHANNEL_TYPES.get(channel)
    if types is None or kind not in types:
        return False
    nested = prefs.get(channel)
    if isinstance(nested, Mapping) and isinstance(nested.get(kind), bool):
        return bool(nested[kind])
    if channel == "inapp":
        legacy = prefs.get(kind)
        if isinstance(legacy, bool):
            return legacy
    return True


def normalized_prefs(prefs: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
    """Expand any stored/legacy shape into the full channel matrix."""
    return {
        channel: {kind: channel_enabled(prefs, channel, kind) for kind in types}
        for channel, types in CHANNEL_TYPES.items()
    }


def merge_prefs(
    existing: Mapping[str, Any], patch: Mapping[str, Mapping[str, bool]]
) -> dict[str, dict[str, bool]]:
    merged = {channel: dict(values) for channel, values in normalized_prefs(existing).items()}
    for channel, values in patch.items():
        merged[channel].update(values)
    return merged
