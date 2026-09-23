from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "server16_py"
_LANGUAGES = ("en", "es", "pt")

# Every literal translation key the Gamepads tab / test dialog can ask for,
# e.g. "status.gamepads.busy", "button.gamepad_test.close",
# "dialog.gamepad_test.title", "tooltip.gamepads.remove".
_KEY_PATTERN = re.compile(r"""["']((?:status|button|label|toggle|tooltip|dialog|card)\.gamepad[a-z_]*\.[a-z_]+)["']""")


def _keys_used_in_code() -> dict[str, str]:
    used: dict[str, str] = {}
    for path in sorted(_PACKAGE.glob("*.py")):
        for key in _KEY_PATTERN.findall(path.read_text(encoding="utf-8")):
            used.setdefault(key, path.name)
    return used


class GamepadLocaleKeyTests(unittest.TestCase):
    """A key the code asks for but a locale file lacks is shown to the user
    as the raw key (that's how "status.gamepads.busy" appeared on a slot whose
    pad Steam was holding). Every gamepad key used in code must exist in all
    three languages."""

    def test_found_some_keys_to_check(self) -> None:
        self.assertGreater(len(_keys_used_in_code()), 20)

    def test_every_gamepad_key_used_in_code_exists_in_every_language(self) -> None:
        used = _keys_used_in_code()
        for language in _LANGUAGES:
            strings = json.loads((_PACKAGE / "locales" / f"{language}.json").read_text(encoding="utf-8"))
            missing = sorted(f"{key} (used in {used[key]})" for key in used if key not in strings)
            self.assertEqual(missing, [], f"{language}.json is missing gamepad keys")


if __name__ == "__main__":
    unittest.main()
