"""Locale negotiation and catalog fallbacks (§17.115)."""

from __future__ import annotations

from rdm.i18n import current_locale, locale_scope, parse_accept_language, tr, translate


def test_parse_accept_language_prefers_first_supported() -> None:
    assert parse_accept_language(None) == "zh-CN"
    assert parse_accept_language("") == "zh-CN"
    assert parse_accept_language("zh-CN,zh;q=0.9,en;q=0.8") == "zh-CN"
    assert parse_accept_language("en-US,en;q=0.9") == "en"
    assert parse_accept_language("fr,en;q=0.5") == "en"
    assert parse_accept_language("fr-FR") == "zh-CN"
    assert parse_accept_language("en;q=0, zh-CN") == "zh-CN"


def test_tr_uses_current_locale_and_falls_back() -> None:
    assert current_locale() == "zh-CN"
    with locale_scope("en"):
        assert current_locale() == "en"
        assert "Internal server error" in tr("errors.internal")
        # Missing in en falls back to the zh catalog, then the key.
        assert tr("does.not.exist", default="fallback") == "fallback"
        assert tr("does.not.exist") == "does.not.exist"
    assert current_locale() == "zh-CN"
    assert tr("errors.internal") == "服务器内部错误"


def test_translate_formats_placeholders_and_tolerates_bad_params() -> None:
    assert "nope" in translate("zh-CN", "errors.unknown_kind", kind="nope")
    # A missing placeholder must not raise from a user-facing path.
    assert "{ref!r}" in translate("en", "work_item.not_found")
