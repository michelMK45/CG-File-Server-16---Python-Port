from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server16_py.ini_file import SessionIniFile, import_sections


class ImportSectionsTests(unittest.TestCase):
    """import_sections() backs the settings-import "Replace or Add?" prompt: "merge" must never
    touch an existing key, "replace" must fully mirror the imported section (dropping whatever
    the destination had that the import doesn't mention)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest_path = Path(self._tmp.name) / "dest.ini"
        self.source_path = Path(self._tmp.name) / "source.ini"

    def _write(self, path: Path, text: str) -> SessionIniFile:
        path.write_text(text, encoding="utf-8")
        return SessionIniFile(path)

    def test_merge_only_adds_missing_keys_and_never_overwrites(self) -> None:
        dest = self._write(
            self.dest_path,
            "[stadium]\nkeep=original\nchange_me=original\n",
        )
        source = self._write(
            self.source_path,
            "[stadium]\nchange_me=imported\nnew_key=imported\n",
        )

        written, skipped = import_sections(dest, source, ["stadium"], "merge")
        dest.save()

        self.assertEqual(written, 1)
        self.assertEqual(skipped, 1)
        reloaded = SessionIniFile(self.dest_path)
        self.assertEqual(reloaded.as_dict("stadium"), {
            "keep": "original",
            "change_me": "original",
            "new_key": "imported",
        })

    def test_replace_clears_keys_the_import_does_not_mention(self) -> None:
        dest = self._write(
            self.dest_path,
            "[stadium]\nold_only=original\nchange_me=original\n",
        )
        source = self._write(
            self.source_path,
            "[stadium]\nchange_me=imported\nnew_key=imported\n",
        )

        written, removed = import_sections(dest, source, ["stadium"], "replace")
        dest.save()

        self.assertEqual(written, 2)
        self.assertEqual(removed, 2)
        reloaded = SessionIniFile(self.dest_path)
        self.assertEqual(reloaded.as_dict("stadium"), {
            "change_me": "imported",
            "new_key": "imported",
        })

    def test_replace_on_a_section_the_destination_never_had(self) -> None:
        dest = self._write(self.dest_path, "[other]\nfoo=bar\n")
        source = self._write(self.source_path, "[stadium]\nnew_key=imported\n")

        written, removed = import_sections(dest, source, ["stadium"], "replace")
        dest.save()

        self.assertEqual(written, 1)
        self.assertEqual(removed, 0)
        reloaded = SessionIniFile(self.dest_path)
        self.assertEqual(reloaded.as_dict("stadium"), {"new_key": "imported"})
        self.assertEqual(reloaded.as_dict("other"), {"foo": "bar"})

    def test_merge_across_multiple_sections_counts_each_independently(self) -> None:
        dest = self._write(
            self.dest_path,
            "[a]\nshared=old\n[b]\nshared=old\n",
        )
        source = self._write(
            self.source_path,
            "[a]\nshared=new\nonly_in_a=x\n[b]\nshared=new\nonly_in_b=y\n",
        )

        written, skipped = import_sections(dest, source, ["a", "b"], "merge")
        dest.save()

        self.assertEqual(written, 2)
        self.assertEqual(skipped, 2)
        reloaded = SessionIniFile(self.dest_path)
        self.assertEqual(reloaded.as_dict("a"), {"shared": "old", "only_in_a": "x"})
        self.assertEqual(reloaded.as_dict("b"), {"shared": "old", "only_in_b": "y"})


if __name__ == "__main__":
    unittest.main()
