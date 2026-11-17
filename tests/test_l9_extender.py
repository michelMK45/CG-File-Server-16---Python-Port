from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from server16_py import l9_extender as l9

INI = (
    "; header comment [Wechsel] in a comment must not count\n"
    "[Saisonziele]\n"
    "Aktiv=1\n"
    "A=1     ; Denmark\n"
    "A=4     ; Belgium\n"
    "\n"
    "; ====\n"
    "; [Ersatzbank] - L9-38 docs, Bank = 7..12\n"
    "; ====\n"
    "\n"
    "[Ersatzbank]\n"
    "Aktiv=0\n"
    "Bank=12   ; keep this comment\n"
    "MinSpieler=18\n"
    "\n"
    "[Wechsel]\n"
    "Aktiv=1\n"
    "Anzahl=5\n"
    "Erzwingen=1\n"
    "\n"
    "[Einlaufhilfe]\n"
    "Aktiv=1\n"
)

LOG_OK = (
    "[19:38:04.426] ==== FIFA 16 dinput8 L9.120 (Stand 2026-10-25) ====\n"
    "[19:38:04.895] [L9] Stand: L9-39 Wechsel @ exe+4B89094 gesetzt: 5 je Team und Spiel, in jedem Spiel\n"
    "[19:38:05.212] [L9-38] ant.cbac: 141909975 Byte (wie SubsOn v3), sub_home_11_Config/sub_away_11_Config vorhanden\n"
    "[19:38:05.213] [L9] Stand: L9-38 Ersatzbank 12 gesetzt: Bankgrenze exe+44B434A 7 -> 12\n"
)

LOG_NO_CBAC = (
    "[16:12:50.000] ==== FIFA 16 dinput8 L9.120 (Stand 2026-10-25) ====\n"
    "[16:12:50.843] [L9] Stand: L9-39 Wechsel @ exe+4B89094 gesetzt: 4 je Team und Spiel\n"
    "[16:12:51.144] [L9-38] ant.cbac: 139792915 Byte, sub_home_11_Config/sub_away_11_Config FEHLEN\n"
    "[16:12:51.144] [L9-38] Bank 12 NICHT gesetzt - Bankplaetze in data\\ant.cbac fehlen (Bank bleibt 7)\n"
)


def _game(tmp_path: Path, ini: str = INI, crlf: bool = False) -> Path:
    text = ini.replace("\n", "\r\n") if crlf else ini
    (tmp_path / l9.L9_INI_NAME).write_bytes(text.encode("utf-8"))
    (tmp_path / l9.L9_DLL_NAME).write_bytes(b"MZ....dinput8_L9.ini....")
    return tmp_path


def test_detect_requires_l9_dll_and_ini(tmp_path):
    assert l9.detect(tmp_path).l9_installed is False
    (tmp_path / l9.L9_INI_NAME).write_text(INI)
    (tmp_path / l9.L9_DLL_NAME).write_bytes(b"MZ windows dinput8")   # not the L9 proxy
    assert l9.detect(tmp_path).l9_installed is False
    _game(tmp_path)
    status = l9.detect(tmp_path)
    assert status.l9_installed is True and status.l9_version is None
    (tmp_path / l9.L9_LOG_NAME).write_text(LOG_OK)
    assert l9.detect(tmp_path).l9_version == "L9.120"
    assert l9.detect(None).l9_installed is False


def test_detect_gameplay_extender(tmp_path):
    assert l9.detect(tmp_path).gameplay_extender_installed is False
    (tmp_path / l9.GAMEPLAY_EXTENDER_DLL_NAME).write_bytes(b"MZ")
    (tmp_path / l9.GAMEPLAY_EXTENDER_LOG_NAME).write_text(
        "19:38:04 GAMEPLAY EXTENDER 0.3.5 (v17 wide players) STANDALONE PLUGIN starting\n")
    status = l9.detect(tmp_path)
    assert status.gameplay_extender_installed and status.gameplay_extender_version == "0.3.5"


def test_read_values(tmp_path):
    values = l9.read_values(_game(tmp_path) / l9.L9_INI_NAME)
    assert values == l9.L9Values(subs_active=True, subs_count=5, bench_active=False, bench_count=12)
    assert l9.read_values(tmp_path / "missing.ini") is None


@pytest.mark.parametrize("crlf", [False, True])
def test_write_values_changes_only_target_keys(tmp_path, crlf):
    ini_path = _game(tmp_path, crlf=crlf) / l9.L9_INI_NAME
    original = ini_path.read_bytes()
    l9.write_values(ini_path, 3, 9)
    newline = "\r\n" if crlf else "\n"
    expected = (INI.replace("[Ersatzbank]\nAktiv=0\nBank=12   ;", "[Ersatzbank]\nAktiv=1\nBank=9   ;")
                .replace("Anzahl=5", "Anzahl=3").replace("\n", newline))
    assert ini_path.read_bytes().decode("utf-8") == expected
    assert (tmp_path / (l9.L9_INI_NAME + l9.L9_BACKUP_SUFFIX)).read_bytes() == original
    assert not (tmp_path / (l9.L9_INI_NAME + ".cgfs16.tmp")).exists()
    assert l9.read_values(ini_path) == l9.L9Values(True, 3, True, 9)


def test_write_values_adds_missing_keys_and_sections(tmp_path):
    ini_path = _game(tmp_path, ini="[Wechsel]\nErzwingen=0\n[Other]\nX=1") / l9.L9_INI_NAME
    l9.write_values(ini_path, 4, 8)
    text = ini_path.read_text(encoding="utf-8")
    assert text == "[Wechsel]\nAktiv=1\nAnzahl=4\nErzwingen=0\n[Other]\nX=1\n\n[Ersatzbank]\nAktiv=1\nBank=8\n"


def test_write_values_keeps_utf8_bom_and_non_ascii(tmp_path):
    ini_path = tmp_path / l9.L9_INI_NAME
    ini_path.write_bytes(b"\xef\xbb\xbf" + "; Primera Divisi\u00f3n\n[Wechsel]\nAnzahl=5\n".encode("utf-8"))
    l9.write_values(ini_path, 6, 10)
    raw = ini_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "Divisi\u00f3n" in raw[3:].decode("utf-8")
    assert l9.read_values(ini_path).subs_count == 6


def test_write_values_no_change_writes_nothing(tmp_path):
    ini_path = _game(tmp_path, ini="[Wechsel]\nAktiv=1\nAnzahl=5\n[Ersatzbank]\nAktiv=1\nBank=10\n") / l9.L9_INI_NAME
    l9.write_values(ini_path, 5, 10)
    assert not (tmp_path / (l9.L9_INI_NAME + l9.L9_BACKUP_SUFFIX)).exists()


@pytest.mark.parametrize(
    ("subs", "bench", "code"),
    [(0, 7, "subs_range"), (13, 12, "subs_range"), (3, 6, "bench_range"), (3, 13, "bench_range"),
     (8, 7, "subs_over_bench"), (7, 7, None), (12, 12, None)],
)
def test_validate(subs, bench, code, tmp_path):
    assert l9.validate(subs, bench) == code
    if code is not None:
        ini_path = _game(tmp_path) / l9.L9_INI_NAME
        before = ini_path.read_bytes()
        with pytest.raises(ValueError, match=code):
            l9.write_values(ini_path, subs, bench)
        assert ini_path.read_bytes() == before


def test_read_applied(tmp_path):
    _game(tmp_path)
    assert l9.read_applied(tmp_path) is None
    log = tmp_path / l9.L9_LOG_NAME
    log.write_text(LOG_OK)
    ini_time = os.stat(tmp_path / l9.L9_INI_NAME).st_mtime
    os.utime(log, (ini_time + 10, ini_time + 10))
    assert l9.read_applied(tmp_path) == l9.L9Applied(subs=5, bench=12, bench_requested_not_set=None,
                                                     cbac_ok=True, stale=False)
    log.write_text(LOG_NO_CBAC)
    os.utime(log, (ini_time - 10, ini_time - 10))
    assert l9.read_applied(tmp_path) == l9.L9Applied(subs=4, bench=None, bench_requested_not_set=12,
                                                     cbac_ok=False, stale=True)


REAL_INSTALL = Path(r"E:\Fifa\FIFA 16 test\fip")


@pytest.mark.skipif(not (REAL_INSTALL / l9.L9_INI_NAME).is_file(), reason="maintainer's FIP install only")
def test_round_trip_on_real_l9_ini(tmp_path):
    shutil.copy(REAL_INSTALL / l9.L9_INI_NAME, tmp_path / l9.L9_INI_NAME)
    ini_path = tmp_path / l9.L9_INI_NAME
    before = ini_path.read_bytes()
    values = l9.read_values(ini_path)
    assert values is not None and values.subs_count is not None and values.bench_count is not None
    l9.write_values(ini_path, 4, 9)
    after = ini_path.read_bytes()
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert len(before.splitlines()) == len(after.splitlines())
    assert all(b.startswith((b"Anzahl=", b"Bank=", b"Aktiv=")) for _a, b in changed)
    assert l9.read_values(ini_path) == l9.L9Values(True, 4, True, 9)
