from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server16_py.assignment_runtime import AssignmentRuntime
from server16_py.ini_file import SessionIniFile


class WriteStadiumGoalpostOverridesTests(unittest.TestCase):
    """Regression tests for the 2026-09-11 bug: goalpost overrides (and,
    worse, other pending writes) were silently never reaching disk.
    SessionIniFile.delete_key() unconditionally reloads from disk before
    deleting (see ini_file.py's own "Force reload from disk" comment),
    which discards any write() made earlier in the same save cycle that
    hasn't been persisted via save() yet. The old
    _write_stadium_goalpost_overrides interleaved write()/delete_key() calls
    across a loop before a single trailing save() -- whichever category
    happened to need a delete_key() (the common case: most stadiums only
    override ONE of model/texture, leaving the other "None") wiped out
    every write() made earlier in that same call. These tests use the REAL
    SessionIniFile (not a toy fake) specifically because a fake without its
    force-reload semantics would hide this exact bug -- which is exactly
    how it shipped unnoticed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ini_path = Path(self._tmp.name) / "settings.ini"

    def make_runtime(self) -> tuple[AssignmentRuntime, SessionIniFile]:
        ini = SessionIniFile(self.ini_path)
        app = SimpleNamespace(settings_ini=ini)
        return AssignmentRuntime(app), ini

    def test_a_model_only_override_actually_reaches_disk(self) -> None:
        # The exact reported scenario: one stadium, model set, texture left
        # at "None" -- the "None" category's delete_key() used to wipe out
        # the model write() made just before it in the same call.
        runtime, ini = self.make_runtime()
        runtime._write_stadium_goalpost_overrides(
            ["Anfield"], {"stadiumgoalpost": "1", "stadiumgoalposttexture": "None"},
        )
        ini.save()
        reloaded = SessionIniFile(self.ini_path)
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalposttexture"))

    def test_a_texture_only_override_actually_reaches_disk(self) -> None:
        # Same bug, opposite category order -- model's delete_key() used to
        # wipe out the texture write() made just before it.
        runtime, ini = self.make_runtime()
        runtime._write_stadium_goalpost_overrides(
            ["Anfield"], {"stadiumgoalpost": "None", "stadiumgoalposttexture": "Azul"},
        )
        ini.save()
        reloaded = SessionIniFile(self.ini_path)
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalposttexture"), "Azul")
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))

    def test_multiple_stadiums_each_keep_their_own_override(self) -> None:
        # A second stadium's delete_key() (Old Trafford has no texture
        # override) used to wipe out the first stadium's already-written
        # model override too, since they share the same save cycle.
        runtime, ini = self.make_runtime()
        runtime._write_stadium_goalpost_overrides(
            ["Anfield", "Old Trafford"],
            {"stadiumgoalpost": "1", "stadiumgoalposttexture": "None"},
        )
        ini.save()
        reloaded = SessionIniFile(self.ini_path)
        self.assertEqual(reloaded.read("Anfield", "stadiumgoalpost"), "1")
        self.assertEqual(reloaded.read("Old Trafford", "stadiumgoalpost"), "1")

    def test_an_already_saved_earlier_write_this_session_is_unaffected(self) -> None:
        # Mirrors assign_stadium()'s real call order: the [stadium]/[comp]
        # value is written AND SAVED (assignstadium_value/assign_with_delete
        # always calls settings_ini.save() before returning) before
        # _write_stadium_goalpost_overrides is ever called -- so its own
        # delete_key() calls' forced reloads just reload the same
        # already-correct, already-on-disk state, nothing pending to lose.
        # _write_stadium_goalpost_overrides is NOT safe to call with a
        # not-yet-saved write still pending from earlier in the same cycle
        # -- see assign_stadium()'s own comment on why it deliberately calls
        # this only after the main assignment write has already been saved.
        runtime, ini = self.make_runtime()
        ini.write("176", "Anfield,4,0,0", "stadium")
        ini.save()
        runtime._write_stadium_goalpost_overrides(
            ["Anfield"], {"stadiumgoalpost": "None", "stadiumgoalposttexture": "None"},
        )
        reloaded = SessionIniFile(self.ini_path)
        self.assertEqual(reloaded.read("176", "stadium"), "Anfield,4,0,0")

    def test_clearing_a_previously_set_override_actually_persists(self) -> None:
        runtime, ini = self.make_runtime()
        runtime._write_stadium_goalpost_overrides(["Anfield"], {"stadiumgoalpost": "1"})
        ini.save()
        runtime2, ini2 = self.make_runtime()
        runtime2._write_stadium_goalpost_overrides(["Anfield"], {"stadiumgoalpost": "None"})
        ini2.save()
        reloaded = SessionIniFile(self.ini_path)
        self.assertFalse(reloaded.key_exists("Anfield", "stadiumgoalpost"))


if __name__ == "__main__":
    unittest.main()
