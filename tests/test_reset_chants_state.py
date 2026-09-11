from __future__ import annotations

import ast
import unittest
from pathlib import Path


class ResetChantsStateTests(unittest.TestCase):
    """Static check on app.py's source, not a live import.

    Several other test files in this suite stub `sys.modules["tkinter"]`
    with a bare-bones fake (only a `Label` attribute) so they can import
    app_game.GameMixin without a real display -- pytest's collection order
    makes that stub, once installed by whichever such file runs first,
    stick for the rest of the session (`sys.modules.setdefault` never
    overwrites it again). server16_py.app pulls in the FULL app (dialogs,
    kit_mixer, settings_editor, ...), which needs far more of tkinter
    (`tkinter.messagebox` among others) than that minimal stub provides --
    importing Server16App here would fail or pass by accident depending on
    which other test files already ran in this same session. A static
    check on the method's own source is immune to that ordering fragility
    and just as precise for what this test needs to prove: which calls
    `_reset_chants_state` does and does not make.
    """

    def test_does_not_reset_the_stadium_db_name_patcher(self) -> None:
        # Real bug found live 2026-09-11: _reset_chants_state() fires on
        # every KickOffHub visit (a new match), and used to also call
        # stadium_db_name_patcher.reset() there -- wiping
        # get_current_name()'s cache every single match even though the
        # FIFA process (and the loaded DB table buffer it tracks) never
        # changed. The NEXT match's request_db_name_patch() then resolved
        # old_name back to the vanilla DB name ("Waldstadion"/"Sanderson
        # Park") instead of whatever the previous match had actually
        # renamed the buffer to -- searching for text no longer in memory,
        # finding 0 candidates, and silently leaving the previous match's
        # custom name stuck on screen. StadiumDbNamePatchCoordinator is
        # explicitly designed (see its own class docstring in
        # match_string_patcher.py) to stay valid for the whole FIFA process
        # lifetime, keyed by process id -- it must not be reset per match.
        source = Path(__file__).resolve().parent.parent.joinpath("server16_py", "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_reset_chants_state"
        )

        called_attrs: set[str] = set()
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
            ):
                called_attrs.add(f"{node.func.value.attr}.{node.func.attr}")

        self.assertIn("entrance_runtime.reset", called_attrs)
        self.assertIn("chants_runtime.reset_chants_state", called_attrs)
        self.assertIn("match_string_patcher.reset", called_attrs)
        self.assertNotIn("stadium_db_name_patcher.reset", called_attrs)


if __name__ == "__main__":
    unittest.main()
