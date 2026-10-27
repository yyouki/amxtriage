"""Dependency-free translations for user-facing labels.

Log text, source code, plugin identifiers and JSON schema keys remain untranslated.
"""
from __future__ import annotations

import json
from importlib.resources import files

SUPPORTED_LANGUAGES = ("en", "id", "es")
LANGUAGE_NAMES = {"en": "English", "id": "Bahasa Indonesia", "es": "Español"}

with files("amxtriage").joinpath("locales.json").open("r", encoding="utf-8") as source:
    _MESSAGES: dict[str, dict[str, str]] = json.load(source)


def translate(language: str, key: str) -> str:
    """Return a translated label, falling back to English for unknown keys/locales."""
    catalog = _MESSAGES.get(language, _MESSAGES["en"])
    return catalog.get(key, _MESSAGES["en"].get(key, key))
