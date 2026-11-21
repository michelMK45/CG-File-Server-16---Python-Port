"""Text-preserving editing of third-party plugin inis (plugin_ini.py)."""
from __future__ import annotations

import pytest

from server16_py.plugin_ini import BACKUP_SUFFIX, IniChangedOnDisk, IniDocument, load, save

ADBOARDS = (
    "; adboards.ini\r\n"
    "[adboard club]\r\n"
    "; carteles del club\r\n"
    "activo = 1\r\n"
    "[adboard competition]\r\n"
    "148 = 1          ; UEFA Champions League (copa 223)\r\n"
    "; 435 = 1          ; League One Play-offs\r\n"
    "148 = 0\r\n"
)


def test_roundtrip_unchanged_is_byte_identical():
    for raw in (
        ADBOARDS.encode(),
        b"\xef\xbb\xbf" + ADBOARDS.encode(),
        "x = Trophée\n".encode("cp1252"),
        b"a=1\nb=2\n",
        b"a=1\nno newline at end",
    ):
        assert IniDocument.from_bytes(raw).to_bytes() == raw


def test_encoding_detection():
    assert IniDocument.from_bytes("x = Trophée\n".encode("cp1252")).encoding == "cp1252"
    doc = IniDocument.from_bytes(b"\xef\xbb\xbfa=1\r\n")
    assert (doc.encoding, doc.bom, doc.newline) == ("utf-8", True, "\r\n")
    assert IniDocument.from_bytes(b"a=1\n").newline == "\n"


def test_fields_skip_comments_and_keep_repeated_keys():
    fields = IniDocument.from_bytes(ADBOARDS.encode()).fields()
    assert [(f.section, f.key, f.value) for f in fields] == [
        ("adboard club", "activo", "1"),
        ("adboard competition", "148", "1"),
        ("adboard competition", "148", "0"),
    ]
    assert fields[0].help == "carteles del club"
    assert fields[1].help == "UEFA Champions League (copa 223)"
    assert fields[2].help == ""   # the commented-out "; 435 = 1 ; ..." above is not its help


def test_help_joins_comment_above_and_inline_comment():
    fields = IniDocument.from_bytes(b"[s]\n; line one\n# line two\nk = 2 ; inline\n").fields()
    assert fields[0].help == "line one\nline two\ninline"


def test_commented_out_entry_is_not_help_of_the_next_key():
    raw = (
        b"[c]\n"
        b"475 = 1          ; Championship Play-offs\n"
        b"; 435 = 1          ; League One Play-offs   ; CGFS16: not found\n"
        b"483 = 1          ; Emirates FA Cup\n"
        b"; 1 = angosto, 2 = ancho\n"
        b"tipo = 2\n"
    )
    fields = IniDocument.from_bytes(raw).fields()
    assert [f.help for f in fields] == ["Championship Play-offs", "Emirates FA Cup", "1 = angosto, 2 = ancho"]


def test_blank_line_breaks_help_block():
    fields = IniDocument.from_bytes(b"; far away\n\nk=1\n").fields()
    assert fields[0].help == ""


def test_slash_comments_and_sectionless_keys():
    fields = IniDocument.from_bytes(b"// SKIP=1\nUCC = 1\n[POW]\nX=2\n").fields()
    assert [(f.section, f.key) for f in fields] == [("", "UCC"), ("POW", "X")]


def test_set_value_keeps_spacing_comment_and_line_end():
    doc = IniDocument.from_bytes(ADBOARDS.encode())
    doc.set_value(doc.fields()[1].line_index, "0")
    assert "148 = 0          ; UEFA Champions League (copa 223)\r\n" in doc.text
    assert doc.text.count("\r\n") == ADBOARDS.count("\r\n")


def test_repeated_keys_edit_independently():
    doc = IniDocument.from_bytes(ADBOARDS.encode())
    doc.set_value(doc.fields()[2].line_index, "1")
    assert [f.value for f in doc.fields()] == ["1", "1", "1"]
    assert doc.text.endswith("148 = 1\r\n")


def test_set_value_strips_the_typed_value_and_keeps_the_comment():
    doc = IniDocument.from_bytes(b"148 = 1          ; UEFA\n")
    doc.set_value(0, " 2 ")
    doc.set_value(0, "2 ")
    assert doc.to_bytes() == b"148 = 2          ; UEFA\n"


def test_set_value_refuses_values_the_reader_would_misparse():
    doc = IniDocument.from_bytes(b"148 = 1          ; UEFA\nname = x\n")
    for bad in ("", "a ;b", "a #b", "x\ny", "x\r"):
        with pytest.raises(ValueError):
            doc.set_value(0, bad)
    assert doc.to_bytes() == b"148 = 1          ; UEFA\nname = x\n"
    doc.set_value(1, "")            # no inline comment: an empty value is unambiguous
    assert doc.to_bytes() == b"148 = 1          ; UEFA\nname = \n"


def test_from_text_keeps_each_lines_own_ending():
    raw = b"[s]\r\na = 1\nb = 2\r\n"
    doc = IniDocument.from_bytes(raw)
    shown = doc.text.replace("\r\n", "\n")      # what the Tk Text widget holds
    assert IniDocument.from_text(shown, like=doc).to_bytes() == raw
    edited = IniDocument.from_text(shown.replace("a = 1", "a = 5"), like=doc)
    assert edited.to_bytes() == b"[s]\r\na = 5\nb = 2\r\n"
    added = IniDocument.from_text(shown + "c = 3\n", like=doc)
    assert added.to_bytes() == raw + b"c = 3\r\n"


def test_set_value_on_non_field_line_raises():
    doc = IniDocument.from_bytes(ADBOARDS.encode())
    with pytest.raises(ValueError):
        doc.set_value(0, "x")


def test_hash_or_semicolon_inside_value_is_not_a_comment():
    doc = IniDocument.from_bytes(b"color=#ff0000\nname=abc#1\nother=abc;1\nz=1\n")
    assert [f.value for f in doc.fields()] == ["#ff0000", "abc#1", "abc;1", "1"]
    doc.set_value(doc.fields()[3].line_index, "2")
    assert doc.to_bytes() == b"color=#ff0000\nname=abc#1\nother=abc;1\nz=2\n"


def test_set_value_on_cp1252_file_keeps_accents():
    raw = "[c]\nname = Trophée des Champions\nn = 1\n".encode("cp1252")
    doc = IniDocument.from_bytes(raw)
    doc.set_value(doc.fields()[1].line_index, "2")
    assert doc.to_bytes() == "[c]\nname = Trophée des Champions\nn = 2\n".encode("cp1252")


def test_from_text_keeps_encoding_and_bom():
    doc = IniDocument.from_bytes(b"\xef\xbb\xbf" + "a = Trophée\n".encode())
    again = IniDocument.from_text(doc.text + "b = 2\n", like=doc)
    assert again.to_bytes() == b"\xef\xbb\xbf" + "a = Trophée\nb = 2\n".encode()


def test_save_writes_backup_and_is_noop_when_unchanged(tmp_path):
    path = tmp_path / "adboards.ini"
    original = ADBOARDS.encode()
    path.write_bytes(original)
    doc, raw = load(path)
    assert save(path, doc, raw) is False
    assert not (tmp_path / ("adboards.ini" + BACKUP_SUFFIX)).exists()

    doc.set_value(doc.fields()[0].line_index, "0")
    assert save(path, doc, raw) is True
    assert b"activo = 0\r\n" in path.read_bytes()
    assert (tmp_path / ("adboards.ini" + BACKUP_SUFFIX)).read_bytes() == original
    assert not (tmp_path / "adboards.ini.cgfs16.tmp").exists()


def test_save_refuses_when_file_changed_on_disk(tmp_path):
    path = tmp_path / "adboards.ini"
    path.write_bytes(ADBOARDS.encode())
    doc, raw = load(path)
    path.write_bytes(b"[x]\nchanged=1\n")
    doc.set_value(doc.fields()[0].line_index, "0")
    with pytest.raises(IniChangedOnDisk):
        save(path, doc, raw)
    assert path.read_bytes() == b"[x]\nchanged=1\n"
