"""Request-scoped locale negotiation and message catalogs (§17.115).

User-visible backend text (error messages, workflow labels, notification
titles, webhook renders) is looked up here instead of being hard-coded. The
locale is negotiated once per HTTP request by ``RequestContextMiddleware``;
code without a request (CLI-internal callers, background workers) falls back
to ``zh-CN`` so previous behaviour is preserved.

Catalog layout: ``resources/i18n/<locale>.json`` holds a nested mapping. Keys
are dotted paths (``"work_item.not_found"``); values may use ``str.format``
placeholders (``"Work item {ref!r} not found"``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import cache
from importlib.resources import files
from typing import Any, Literal

Locale = Literal["zh-CN", "en"]

DEFAULT_LOCALE: Locale = "zh-CN"
SUPPORTED_LOCALES: tuple[Locale, ...] = ("zh-CN", "en")

_locale_var: ContextVar[Locale] = ContextVar("rdm_locale", default=DEFAULT_LOCALE)


def normalize_locale(value: str | None) -> Locale:
    """Map a language tag to a supported locale (default zh-CN)."""
    if not value:
        return DEFAULT_LOCALE
    tag = value.strip().lower()
    if tag.startswith("en"):
        return "en"
    if tag.startswith("zh"):
        return "zh-CN"
    return DEFAULT_LOCALE


def parse_accept_language(header: str | None) -> Locale:
    """Pick the first supported language from an Accept-Language header.

    ``zh-CN,zh;q=0.9,en;q=0.8`` -> ``zh-CN``; ``fr,en;q=0.5`` -> ``en``.
    Unsupported tags are skipped; no header falls back to zh-CN.
    """
    if not header:
        return DEFAULT_LOCALE
    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        for param in params.split(";"):
            name, _, raw = param.strip().partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(raw)
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        candidates.append((-quality, index, tag.strip()))
    for _negative, _index, tag in sorted(candidates):
        locale = normalize_locale(tag)
        if tag.lower().startswith(("zh", "en")):
            return locale
    return DEFAULT_LOCALE


def current_locale() -> Locale:
    return _locale_var.get()


def set_locale(locale: str | Locale | None) -> Token[Locale]:
    return _locale_var.set(normalize_locale(locale))


def reset_locale(token: Token[Locale]) -> None:
    _locale_var.reset(token)


@contextmanager
def locale_scope(locale: str | Locale | None) -> Iterator[Locale]:
    """Temporarily use ``locale`` (used by tests and background helpers)."""
    normalized = normalize_locale(locale)
    token = _locale_var.set(normalized)
    try:
        yield normalized
    finally:
        _locale_var.reset(token)


@cache
def _catalog(locale: Locale) -> Mapping[str, Any]:
    resource = files("rdm.resources").joinpath("i18n", f"{locale}.json")
    with resource.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _lookup(locale: Locale, key: str) -> str | None:
    node: Any = _catalog(locale)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def translate(
    locale: str | Locale | None, message_key: str, *, default: str | None = None, **params: Any
) -> str:
    """Render ``message_key`` in an explicit locale, falling back to zh-CN then default."""
    normalized = normalize_locale(locale)
    template = _lookup(normalized, message_key)
    if template is None and normalized != DEFAULT_LOCALE:
        template = _lookup(DEFAULT_LOCALE, message_key)
    if template is None:
        template = default if default is not None else message_key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        # A malformed catalog entry must not turn a user-facing error into a
        # 500; show the raw template instead.
        return template


def tr(
    message_key: str,
    *,
    default: str | None = None,
    locale: str | Locale | None = None,
    **params: Any,
) -> str:
    """Translate ``message_key`` in the current request locale."""
    return translate(
        locale if locale is not None else current_locale(),
        message_key,
        default=default,
        **params,
    )
