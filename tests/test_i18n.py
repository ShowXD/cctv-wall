"""Guards for the translation catalog and the constants that duplicate each other.

Fourteen unused keys and one untranslated string went unnoticed until a manual
audit found them. These tests make the same rot fail the build instead.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from cctv_wall.i18n import LANGUAGE_LABELS, _MESSAGES, Translator
from cctv_wall.models import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from cctv_wall.ui.camera_form import FIELD_LABEL_KEYS
from cctv_wall.ui.table_import import FIELD_LABEL_KEYS as TABLE_FIELD_LABEL_KEYS

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "cctv_wall"
# A whole `t(...)` argument list — `_text(raw.get("x"))` also ends in `t(`, so require a
# non-word character first. Matching the full list catches `t("a" if x else "b", n=1)`;
# one level of nesting covers arguments like `t("k", name=self._label(x))`.
TRANSLATION_CALL = re.compile(r"(?<![\w_])t\(((?:[^()]|\([^()]*\))*)\)")
KEY_LITERAL = re.compile(r"[\"']([a-z_0-9]+)[\"']")
# Keys chosen at runtime from a PlaybackState, never written literally.
DYNAMIC_KEYS = frozenset({"connection_waiting", "no_video", "vlc_error", "not_playing"})
# Form-field labels are looked up through a table, so the literal never appears in a call.
INDIRECT_KEYS = frozenset((*FIELD_LABEL_KEYS.values(), *TABLE_FIELD_LABEL_KEYS.values()))


def _keys_used_in_source() -> set[str]:
    used = set(INDIRECT_KEYS)
    for module in SOURCE_ROOT.rglob("*.py"):
        if module.name == "i18n.py":
            continue
        for arguments in TRANSLATION_CALL.findall(module.read_text(encoding="utf-8")):
            used |= set(KEY_LITERAL.findall(arguments))
    return used


class TestCatalog:
    def test_every_supported_language_has_a_catalog(self):
        assert set(_MESSAGES) == set(SUPPORTED_LANGUAGES) == set(LANGUAGE_LABELS)

    def test_catalogs_define_exactly_the_same_keys(self):
        english, chinese = set(_MESSAGES["en"]), set(_MESSAGES["zh_TW"])
        assert english - chinese == set(), "missing Chinese translations"
        assert chinese - english == set(), "missing English translations"

    def test_every_key_the_code_asks_for_exists(self):
        missing = _keys_used_in_source() - set(_MESSAGES["en"])
        assert missing == set(), f"code asks for undefined keys: {sorted(missing)}"

    def test_no_key_is_left_unused(self):
        unused = set(_MESSAGES["en"]) - _keys_used_in_source() - DYNAMIC_KEYS
        assert unused == set(), f"dead translation keys: {sorted(unused)}"

    def test_the_dynamic_keys_really_are_defined(self):
        assert DYNAMIC_KEYS <= set(_MESSAGES["en"])

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES - {"en"}))
    def test_placeholders_match_between_languages(self, language):
        """A translation that drops `{count}` would fail at runtime, not here."""
        for key, english in _MESSAGES["en"].items():
            expected = set(re.findall(r"\{(\w+)", english))
            actual = set(re.findall(r"\{(\w+)", _MESSAGES[language][key]))
            assert expected == actual, f"{language}/{key}: placeholders differ"


class TestTranslator:
    def test_an_unsupported_language_falls_back(self):
        assert Translator("klingon").language == DEFAULT_LANGUAGE

    def test_an_unknown_key_returns_itself_rather_than_raising(self):
        assert Translator().t("no_such_key") == "no_such_key"

