from __future__ import annotations

import tkinter as tk
import unittest

from server16_py.gamepad_test_dialog import GamepadTestDialog

_STRINGS = {
    "label.gamepads.slot": "Slot {n}",
    "dialog.gamepad_test.title": "Gamepad Test - {device}",
}


class FakeBridge:
    def __init__(self) -> None:
        self.reads: list[tuple[str, int | None]] = []

    def read_raw_state(self, device_guid: str, slot_index: int | None = None):
        self.reads.append((device_guid, slot_index))
        return None

    def is_device_busy(self, device_guid: str) -> bool:
        return False


def _all_label_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            texts.append(child.cget("text"))
        texts.extend(_all_label_texts(child))
    return texts


class GamepadTestDialogSlotTests(unittest.TestCase):
    """The dialog says which slot it is testing (two identical pads share a
    model name) and asks the bridge for THAT slot's pad."""

    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # no display available
            self.skipTest(f"Tk unavailable: {exc}")
        self.root.withdraw()
        self.root.tr = self._tr
        self.bridge = FakeBridge()
        self.dialogs: list[GamepadTestDialog] = []

    @staticmethod
    def _tr(key: str, **kwargs) -> str:
        # Like the app's own tr(): a placeholder with no value passed stays
        # as-is (BaseDialog.__init__ translates the title once without any).
        class _Keep(dict):
            def __missing__(self, name):
                return "{" + name + "}"

        return _STRINGS.get(key, key).format_map(_Keep(kwargs))

    def tearDown(self) -> None:
        for dialog in self.dialogs:
            if dialog.winfo_exists():
                dialog.destroy()
        self.root.destroy()

    def _open(self, slot_index):
        dialog = GamepadTestDialog(self.root, self.bridge, "guid-1", "Pro Controller", "standard", slot_index)
        self.dialogs.append(dialog)
        return dialog

    def test_title_and_heading_name_the_slot(self) -> None:
        dialog = self._open(1)
        self.assertEqual(dialog.title(), "Gamepad Test - Slot 2 - Pro Controller")
        self.assertIn("Slot 2 - Pro Controller", _all_label_texts(dialog))

    def test_without_a_slot_the_heading_is_just_the_device(self) -> None:
        dialog = self._open(None)
        self.assertEqual(dialog.title(), "Gamepad Test - Pro Controller")
        self.assertIn("Pro Controller", _all_label_texts(dialog))

    def test_reads_the_state_of_that_slots_pad(self) -> None:
        self._open(3)
        self.assertEqual(self.bridge.reads[0], ("guid-1", 3))


if __name__ == "__main__":
    unittest.main()
