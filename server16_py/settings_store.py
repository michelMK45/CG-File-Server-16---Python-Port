from __future__ import annotations

import json
from pathlib import Path

from .substitution_runtime import SUBSTITUTION_MAX, SUBSTITUTION_MIN

# UI zoom range for app_ui.py's zoom buttons/popup, applied on top of the
# fixed 96-DPI tk-scaling base (see app.py's __init__ comment on
# _base_tk_scaling — that base never moves with the real monitor DPI).
# UI_ZOOM_DEFAULT is what "100%" in the zoom popup actually renders at: the
# app's original 1024x680/point-size design was judged too small on its own
# (users found the 96-DPI baseline cramped even before any monitor-DPI
# concerns), so the *default* is deliberately set above the legacy 1:1 value
# rather than leaving 100% == the old tiny baseline. MIN/MAX keep the same
# 0.8x-1.6x range *relative to this new default*, not to the old baseline.
UI_ZOOM_DEFAULT = 1.15
UI_ZOOM_MIN = round(UI_ZOOM_DEFAULT * 0.8, 4)
UI_ZOOM_MAX = round(UI_ZOOM_DEFAULT * 1.6, 4)


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
        "SHOW_OVERLAY": True,
        "KIT_HOTKEYS_ENABLED": True,
        "KEEP_OPEN_ON_GAME_CLOSE": True,
        "OVERLAY_PERFORMANCE_MODE": False,
        "LANGUAGE": "en",
        "UI_ZOOM": UI_ZOOM_DEFAULT,
        "CUSTOM_KIT_NUMBERS": False,
        # FIFA's own vanilla default (3), not the last CE-tested value (5) — a fresh install
        # should show a familiar baseline rather than an arbitrary number.
        "SUBSTITUTION_COUNT": 3,
        "AUTO_APPLY_SUBSTITUTION_COUNT": False,
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
    def show_overlay(self) -> bool:
        return bool(self.data.get("SHOW_OVERLAY", True))

    @show_overlay.setter
    def show_overlay(self, value: bool) -> None:
        self.data["SHOW_OVERLAY"] = bool(value)
        self.save()

    @property
    def kit_hotkeys_enabled(self) -> bool:
        return bool(self.data.get("KIT_HOTKEYS_ENABLED", True))

    @kit_hotkeys_enabled.setter
    def kit_hotkeys_enabled(self, value: bool) -> None:
        self.data["KIT_HOTKEYS_ENABLED"] = bool(value)
        self.save()

    @property
    def keep_open_on_game_close(self) -> bool:
        return bool(self.data.get("KEEP_OPEN_ON_GAME_CLOSE", True))

    @keep_open_on_game_close.setter
    def keep_open_on_game_close(self, value: bool) -> None:
        self.data["KEEP_OPEN_ON_GAME_CLOSE"] = bool(value)
        self.save()

    @property
    def overlay_performance_mode(self) -> bool:
        return bool(self.data.get("OVERLAY_PERFORMANCE_MODE", False))

    @overlay_performance_mode.setter
    def overlay_performance_mode(self, value: bool) -> None:
        self.data["OVERLAY_PERFORMANCE_MODE"] = bool(value)
        self.save()

    @property
    def custom_kit_numbers(self) -> bool:
        return bool(self.data.get("CUSTOM_KIT_NUMBERS", False))

    @custom_kit_numbers.setter
    def custom_kit_numbers(self, value: bool) -> None:
        self.data["CUSTOM_KIT_NUMBERS"] = bool(value)
        self.save()

    @property
    def substitution_count(self) -> int:
        value = int(self.data.get("SUBSTITUTION_COUNT", 3))
        return max(SUBSTITUTION_MIN, min(SUBSTITUTION_MAX, value))

    @substitution_count.setter
    def substitution_count(self, value: int) -> None:
        self.data["SUBSTITUTION_COUNT"] = max(SUBSTITUTION_MIN, min(SUBSTITUTION_MAX, int(value)))
        self.save()

    @property
    def auto_apply_substitution_count(self) -> bool:
        return bool(self.data.get("AUTO_APPLY_SUBSTITUTION_COUNT", False))

    @auto_apply_substitution_count.setter
    def auto_apply_substitution_count(self, value: bool) -> None:
        self.data["AUTO_APPLY_SUBSTITUTION_COUNT"] = bool(value)
        self.save()

    @property
    def ui_zoom(self) -> float:
        value = float(self.data.get("UI_ZOOM", UI_ZOOM_DEFAULT))
        return max(UI_ZOOM_MIN, min(UI_ZOOM_MAX, value))

    @ui_zoom.setter
    def ui_zoom(self, value: float) -> None:
        self.data["UI_ZOOM"] = max(UI_ZOOM_MIN, min(UI_ZOOM_MAX, float(value)))
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
