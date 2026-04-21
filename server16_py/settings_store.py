from __future__ import annotations

import json
from pathlib import Path


class SettingsStore:
    DEFAULTS = {
        "FIFAEXE": "default",
        "CAMERAPACKAGE": "",
        "SHOW_STADIUM_LOADING_NOTIFICATION": True,
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
                raise ValueError("Settings file must contain an object")
            self.data = {**self.DEFAULTS, **loaded}
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
