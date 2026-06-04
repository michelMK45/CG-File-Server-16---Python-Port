from __future__ import annotations

import json
from pathlib import Path


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*.

    Nested dicts are merged key-by-key so that keys present only in *base*
    are preserved even when *override* contains a partial version of the
    same nested dict.  Non-dict values in *override* always win.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class SettingsStore:
    DEFAULTS = {
        "FIFAEXE": "default",
        "CAMERAPACKAGE": "",
        # Backward-compatible: keep this key available even if current UI
        # does not expose it yet.
        "SHOW_STADIUM_LOADING_NOTIFICATION": True,
        "LANGUAGE": "en",
        # Discord Rich Presence defaults.  Users can override any key in their
        # runtime/settings.json; missing keys fall back to these values so the
        # feature works out-of-the-box in the compiled EXE without needing to
        # manually edit the generated settings file.
        "discord_rpc": {
            "enabled": True,
            "client_id": "1495719449700077630",
            "update_interval_ms": 1000,
            "stadium_preview_provider": "imgbb",
            "stadium_preview_imgbb_api_key": "af421c8d5d14de2bbefc9697cbe5cae9",
            "stadium_preview_mode": "url"
        },
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.save()
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Settings file must contain a JSON object")
            # Deep-merge so nested dicts (e.g. discord_rpc) get their missing
            # keys filled in from DEFAULTS rather than the whole block being
            # replaced by whatever partial dict the user file contains.
            self.data = _deep_merge(self.DEFAULTS, loaded)
        except Exception:
            self.data = dict(self.DEFAULTS)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def fifa_exe(self) -> str:
        return self.data.get("FIFAEXE", "default")

    @fifa_exe.setter
    def fifa_exe(self, value: str) -> None:
        self.data["FIFAEXE"] = value
        self.save()

    @property
    def camera_package(self) -> str:
        return self.data.get("CAMERAPACKAGE", "")

    @camera_package.setter
    def camera_package(self, value: str) -> None:
        self.data["CAMERAPACKAGE"] = value
        self.save()

    @property
    def show_stadium_loading_notification(self) -> bool:
        return bool(self.data.get("SHOW_STADIUM_LOADING_NOTIFICATION", True))

    @show_stadium_loading_notification.setter
    def show_stadium_loading_notification(self, value: bool) -> None:
        self.data["SHOW_STADIUM_LOADING_NOTIFICATION"] = bool(value)
        self.save()

    @property
    def language(self) -> str:
        value = str(self.data.get("LANGUAGE", "en")).strip().lower()
        return value if value in {"en", "pt", "es"} else "en"

    @language.setter
    def language(self, value: str) -> None:
        normalized = str(value or "en").strip().lower()
        self.data["LANGUAGE"] = normalized if normalized in {"en", "pt", "es"} else "en"
        self.save()
