from __future__ import annotations

import json
from pathlib import Path

from .locales_data import LOCALE_CATALOGS


SUPPORTED_LANGUAGES = ("en", "pt", "es")
LANGUAGE_LABELS = {
    "en": "English",
    "pt": "Português",
    "es": "Español",
}


class LocalizationManager:
    def __init__(self, locales_dir: Path, language: str = "en") -> None:
        self.locales_dir = locales_dir
        self._catalogs: dict[str, dict[str, str]] = {}
        self.language = "en"
        self.set_language(language)

    def set_language(self, language: str) -> str:
        normalized = (language or "en").strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            normalized = "en"
        self.language = normalized
        self._load_catalog("en")
        self._load_catalog(normalized)
        return normalized

    def translate(self, msg_key: str, **kwargs) -> str:
        text = self._catalogs.get(self.language, {}).get(msg_key)
        if text is None:
            text = self._catalogs.get("en", {}).get(msg_key, msg_key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def _load_catalog(self, language: str) -> None:
        if language in self._catalogs:
            return
        path = self.locales_dir / f"{language}.json"
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self._catalogs[language] = loaded if isinstance(loaded, dict) else {}
        except Exception:
            fallback = LOCALE_CATALOGS.get(language, {})
            self._catalogs[language] = dict(fallback) if isinstance(fallback, dict) else {}
