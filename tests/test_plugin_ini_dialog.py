"""PluginIniDialog: the Plugins tab's ⚙ editor (form + Text tab) over plugin_ini."""
from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server16_py.dialogs import PluginIniDialog

ADBOARDS = (
    "[adboard club]\r\n"
    "; carteles del club\r\n"
    "activo = 1\r\n"
    "[adboard competition]\r\n"
    "148 = 1          ; UEFA Champions League\r\n"
    "; 435 = 1          ; League One Play-offs\r\n"
)


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class PluginIniDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ini = Path(self._tmp.name) / "adboards.ini"
        self.ini.write_bytes(ADBOARDS.encode())
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tr = lambda key, **kwargs: key
        self.logged: list[str] = []
        self.root.log = lambda message, *args, **kwargs: self.logged.append(message)
        self.addCleanup(self.root.destroy)
        self.dialog = PluginIniDialog(self.root, "Adboards", self.ini)

    def _field_line(self, key: str) -> int:
        return next(f.line_index for f in self.dialog.doc.fields() if f.key == key)

    def test_form_lists_fields_by_line(self):
        assert sorted(self.dialog.entries) == [2, 4]
        assert self.dialog.entries[4].get() == "1"

    def test_form_edit_then_save_changes_only_that_value(self):
        self.dialog.entries[self._field_line("148")].set("0")
        assert self.dialog.save() is True
        assert self.ini.read_bytes() == ADBOARDS.replace("148 = 1 ", "148 = 0 ").encode()
        assert self.dialog.result is True
        assert any("adboards.ini" in line for line in self.logged)

    def test_save_without_changes_closes_without_writing(self):
        assert self.dialog.save() is True
        assert not (self.ini.parent / "adboards.ini.cgfs16.bak").exists()

    def test_text_edit_roundtrips_into_form(self):
        self.dialog._show_text()
        content = self.dialog.text.get("1.0", "end-1c")
        assert "\r" not in content
        self.dialog.text.delete("1.0", "end")
        self.dialog.text.insert("1.0", content.replace("; 435 = 1", "435 = 1"))
        self.dialog._show_form()
        assert any(f.key == "435" for f in self.dialog.doc.fields())
        assert self.dialog.save() is True
        assert self.ini.read_bytes() == ADBOARDS.replace("; 435 = 1", "435 = 1").encode()

    def test_save_from_text_tab_takes_the_text(self):
        self.dialog._show_text()
        content = self.dialog.text.get("1.0", "end-1c")
        self.dialog.text.delete("1.0", "end")
        self.dialog.text.insert("1.0", content.replace("activo = 1", "activo = 0"))
        assert self.dialog.save() is True
        assert b"activo = 0\r\n" in self.ini.read_bytes()

    def test_changed_on_disk_reload_keeps_dialog_open_with_disk_values(self):
        self.ini.write_bytes(ADBOARDS.replace("activo = 1", "activo = 7").encode())
        self.dialog.entries[self._field_line("148")].set("0")
        self.dialog._ask_changed_on_disk = lambda: "reload"
        assert self.dialog.save() is False
        assert self.dialog.winfo_exists()
        assert self.dialog.entries[self._field_line("activo")].get() == "7"
        assert self.dialog.entries[self._field_line("148")].get() == "1"

    def test_changed_on_disk_overwrite_writes_our_edit(self):
        self.ini.write_bytes(ADBOARDS.replace("activo = 1", "activo = 7").encode())
        self.dialog.entries[self._field_line("148")].set("0")
        self.dialog._ask_changed_on_disk = lambda: "overwrite"
        assert self.dialog.save() is True
        assert self.ini.read_bytes() == ADBOARDS.replace("148 = 1 ", "148 = 0 ").encode()

    def test_changed_on_disk_cancel_writes_nothing(self):
        external = ADBOARDS.replace("activo = 1", "activo = 7").encode()
        self.ini.write_bytes(external)
        self.dialog.entries[self._field_line("148")].set("0")
        self.dialog._ask_changed_on_disk = lambda: "cancel"
        assert self.dialog.save() is False
        assert self.ini.read_bytes() == external

    def test_cancel_with_changes_asks_confirmation(self):
        self.dialog.entries[self._field_line("148")].set("0")
        asked: list[str] = []
        self.dialog._confirm = lambda key: asked.append(key) or False
        self.dialog.cancel()
        assert asked == ["dialog.plugins.ini.discard"] and self.dialog.winfo_exists()
        self.dialog._confirm = lambda key: True
        self.dialog.cancel()
        assert not self.dialog.winfo_exists()
        assert self.ini.read_bytes() == ADBOARDS.encode()

    def test_applying_the_form_twice_is_idempotent(self):
        self.dialog.entries[self._field_line("148")].set("2 ")
        self.dialog._apply_form()
        self.dialog._apply_form()
        assert self.dialog.doc.text.count("148 = 2          ; UEFA Champions League\r\n") == 1

    def test_ambiguous_value_is_refused_and_dialog_stays_open(self):
        shown: list[str] = []
        self.dialog._show_error = lambda key, **kw: shown.append(key)
        self.dialog.entries[self._field_line("148")].set("")
        assert self.dialog.save() is False
        assert shown == ["dialog.plugins.ini.error_value"]
        assert self.dialog.winfo_exists()
        assert self.ini.read_bytes() == ADBOARDS.encode()
        self.dialog.entries[self._field_line("148")].set("0")
        assert self.dialog.save() is True
        assert b"148 = 0          ; UEFA Champions League\r\n" in self.ini.read_bytes()

    def test_viewing_text_without_edits_changes_nothing(self):
        mixed = b"[s]\r\na = 1\nb = 2\r\n"
        self.ini.write_bytes(mixed)
        dialog = PluginIniDialog(self.root, "Mixed", self.ini)
        dialog._show_text()
        dialog._show_form()
        dialog._confirm = lambda key: self.fail("nothing changed, should not ask")
        assert dialog.save() is True
        assert self.ini.read_bytes() == mixed

    def test_large_ini_opens_on_the_text_tab(self):
        self.ini.write_bytes(("[s]\n" + "".join(f"k{i} = {i}\n" for i in range(400))).encode())
        dialog = PluginIniDialog(self.root, "Big", self.ini)
        assert dialog._active == "text"
        assert dialog.notebook.index(dialog.notebook.select()) == 1
        assert dialog.entries == {}
        assert "k399 = 399" in dialog.text.get("1.0", "end-1c")
        dialog._show_form()
        assert len(dialog.entries) == 400

    def test_cancel_without_changes_does_not_ask(self):
        self.dialog._confirm = lambda key: self.fail("should not ask")
        self.dialog.cancel()
        assert not self.dialog.winfo_exists()
