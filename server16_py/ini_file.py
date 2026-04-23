from __future__ import annotations

import configparser
import unicodedata
from pathlib import Path


def _normalize_key(key: str) -> str:
    """Normalize a key for comparison: NFC unicode + strip whitespace."""
    return unicodedata.normalize("NFC", key).strip()


class IniFile:
    def __init__(self, ini_path: str | Path) -> None:
        self.path = Path(ini_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _load(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        raw = self.path.read_bytes()
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                parser.read_string(raw.decode(encoding), source=str(self.path))
                return parser
            except UnicodeDecodeError:
                continue
            except configparser.Error:
                continue
        return parser

    @staticmethod
    def _resolve_section_name(parser: configparser.ConfigParser, section: str) -> str | None:
        if parser.has_section(section):
            return section
        section_lower = section.lower()
        for existing in parser.sections():
            if existing.lower() == section_lower:
                return existing
        return None

    def read(self, key: str, section: str) -> str:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section and parser.has_option(resolved_section, key):
            return parser.get(resolved_section, key)
        return ""

    def write(self, key: str, value: str, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if not resolved_section:
            parser.add_section(section)
            resolved_section = section
        parser.set(resolved_section, key, value)
        with self.path.open("w", encoding="utf-8", errors="replace") as handle:
            parser.write(handle)

    def delete_key(self, key: str, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section:
            parser.remove_option(resolved_section, key)
            with self.path.open("w", encoding="utf-8", errors="replace") as handle:
                parser.write(handle)

    def delete_section(self, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section:
            parser.remove_section(resolved_section)
        with self.path.open("w", encoding="utf-8", errors="replace") as handle:
            parser.write(handle)

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self.read(key, section))


class SessionIniFile:
    def __init__(self, ini_path: str | Path) -> None:
        self.path = Path(ini_path)
        self._sections: dict[str, dict[str, str]] = {}
        self._section_names: dict[str, str] = {}
        self._last_mtime_ns: int | None = None
        self._load()

    def _load(self) -> None:
        self._sections = {}
        self._section_names = {}
        if not self.path.exists():
            self._last_mtime_ns = None
            return
        raw = self.path.read_bytes()
        text = ""
        # Detect encoding: if file has UTF-8 BOM use utf-8-sig,
        # if bytes are valid UTF-8 (strict) use utf-8,
        # otherwise fall back to cp1252 (most common for FIFA modding tools on Windows).
        if raw.startswith(b"\xef\xbb\xbf"):
            # UTF-8 BOM present
            text = raw.decode("utf-8-sig", errors="replace")
        else:
            try:
                text = raw.decode("utf-8")
                # Extra check: if decoded text has replacement chars, likely not utf-8
                if "\ufffd" in text:
                    raise UnicodeDecodeError("utf-8", raw, 0, 1, "replacement chars found")
            except UnicodeDecodeError:
                try:
                    text = raw.decode("cp1252")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
        current_section: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1].strip()
                section_key = section_name.lower()
                canonical = self._section_names.setdefault(section_key, section_name)
                self._sections.setdefault(canonical, {})
                current_section = canonical
                continue
            if current_section is None or "=" not in line:
                continue
            key, value = line.split("=", 1)
            self._sections[current_section][_normalize_key(key)] = unicodedata.normalize("NFC", value.strip())
        try:
            self._last_mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns = None

    def _reload_if_needed(self, force: bool = False) -> None:
        if force:
            self._load()
            return
        try:
            current_mtime = self.path.stat().st_mtime_ns
        except OSError:
            current_mtime = None
        if current_mtime != self._last_mtime_ns:
            self._load()

    def _resolve_section_name(self, section: str) -> str | None:
        self._reload_if_needed()
        return self._section_names.get(section.lower())

    def read(self, key: str, section: str) -> str:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            return self._sections.get(resolved_section, {}).get(_normalize_key(key), "")
        return ""

    def write(self, key: str, value: str, section: str) -> None:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            resolved_section = section
            self._section_names[section.lower()] = section
            self._sections[section] = {}
        self._sections.setdefault(resolved_section, {})[_normalize_key(key)] = unicodedata.normalize("NFC", value)

    def save(self) -> None:
        # Before writing, merge any pending in-memory changes on top of the
        # current disk state. This prevents a race condition where _reload_if_needed
        # inside write() reloads from disk AFTER the caller already called write()
        # but BEFORE save() runs, causing the pending changes to be lost.
        pending: dict[str, dict[str, str]] = {}
        for section, values in self._sections.items():
            pending[section] = dict(values)
        try:
            current_mtime = self.path.stat().st_mtime_ns
        except OSError:
            current_mtime = None
        if current_mtime != self._last_mtime_ns:
            # Disk changed since last load — reload first, then re-apply pending
            self._load()
            for section, values in pending.items():
                section_key = section.lower()
                canonical = self._section_names.get(section_key)
                if not canonical:
                    canonical = section
                    self._section_names[section_key] = section
                    self._sections[section] = {}
                for key, value in values.items():
                    self._sections.setdefault(canonical, {})[key] = value
        lines: list[str] = []
        for section, values in self._sections.items():
            lines.append(f"[{section}]")
            for key, value in values.items():
                lines.append(f"{key}={value}")
            lines.append("")
        payload = "\n".join(lines).rstrip() + ("\n" if lines else "")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(payload, encoding="utf-8", errors="replace")
        try:
            self._last_mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns = None

    def delete_key(self, key: str, section: str) -> None:
        # Force reload from disk so we work with the latest state,
        # then remove the key. The caller must still call save() afterward.
        self._reload_if_needed(force=True)
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            self._sections.get(resolved_section, {}).pop(_normalize_key(key), None)

    def delete_section(self, section: str) -> None:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            self._sections.pop(resolved_section, None)
            self._section_names.pop(resolved_section.lower(), None)

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self.read(key, section))

    def sections(self) -> list[str]:
        self._reload_if_needed()
        return list(self._sections.keys())

    def items(self, section: str) -> list[tuple[str, str]]:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            return []
        return list(self._sections.get(resolved_section, {}).items())

    def as_dict(self, section: str) -> dict[str, str]:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            return {}
        return dict(self._sections.get(resolved_section, {}))

    def reload(self) -> None:
        self._reload_if_needed(force=True)
