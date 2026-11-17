"""Third-party FIFA 16 mods next to fifa16.exe that CGFS16 can work with ("extender" mods).

**dinput8 "Line 9" (L9)**: a dinput8.dll proxy that code-patches fifa16.exe at startup from
``dinput8_L9.ini``. Two of its sections replace CGFS16's own substitution hook
(``substitution_runtime.py``) when it is installed and the user has not chosen legacy mode:

- ``[Wechsel]`` (L9-39) ``Anzahl``: substitutions per team and match, set while FIFA builds the
  match (both teams, every mode). ``Erzwingen`` is left as the user's file has it.
- ``[Ersatzbank]`` (L9-38) ``Bank``: substitutes on the bench, 7 (original) .. 12. More than 7 needs
  SubsOn's ``data\\ant.cbac``; without it L9 keeps 7. ``MinSpieler`` is never touched.

L9 reads the ini ONCE, when FIFA starts, and writes what it applied to ``dinput8_L9.log`` (German),
so CGFS16 only edits the ini while FIFA is closed and reads the log back to show what was applied.
CGFS16 never writes FIFA memory for this.

The ini is hand-commented, has repeated keys (``A=1`` / ``A=4``...) and inline ``;`` comments, so it
is edited as text, line by line (configparser / SessionIniFile would reorder or reject it).

**Gameplay Extender** (``Gameplay_Extender.dll``, loaded by ``XInput9_1_0.dll``): only detected and
reported; CGFS16 does not configure it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

L9_DLL_NAME = "dinput8.dll"
L9_INI_NAME = "dinput8_L9.ini"
L9_LOG_NAME = "dinput8_L9.log"
L9_BACKUP_SUFFIX = ".cgfs16.bak"
GAMEPLAY_EXTENDER_DLL_NAME = "Gameplay_Extender.dll"
GAMEPLAY_EXTENDER_LOG_NAME = "Gameplay_Extender.log"

SUBS_SECTION = "Wechsel"
BENCH_SECTION = "Ersatzbank"

# Ranges documented in L9's own ini header (L9.118+).
L9_SUBS_MIN = 1
L9_SUBS_MAX = 12
L9_BENCH_MIN = 7      # 7 = FIFA's original bench
L9_BENCH_MAX = 12
L9_BENCH_COMFORT_MAX = 10   # the mod's readme: with 12, some substitutes sit "in the air"

# The L9 dll embeds its ini name; another dinput8.dll proxy (or Windows' own copy) does not.
_L9_DLL_MARKER = L9_INI_NAME.encode("ascii")

_LOG_VERSION_RE = re.compile(r"dinput8\s+(L9\.\d+)")
_LOG_SUBS_RE = re.compile(r"Stand: L9-39 Wechsel .*?gesetzt: (\d+) je Team")
_LOG_BENCH_RE = re.compile(r"Stand: L9-38 Ersatzbank (\d+) gesetzt")
_LOG_BENCH_NOT_SET_RE = re.compile(r"\[L9-38\] Bank (\d+) NICHT gesetzt")
_LOG_CBAC_RE = re.compile(r"\[L9-38\] ant\.cbac:.*sub_home_11_Config/sub_away_11_Config (\w+)")
_GE_VERSION_RE = re.compile(r"GAMEPLAY EXTENDER\s+([0-9][0-9.]*)")

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")


@dataclass(frozen=True)
class ExtenderStatus:
    """What is installed next to fifa16.exe. Versions come from each mod's last log (None until
    the game has been started once with it)."""

    l9_installed: bool
    l9_version: str | None
    gameplay_extender_installed: bool
    gameplay_extender_version: str | None


@dataclass(frozen=True)
class L9Values:
    """The two values CGFS16 edits, as the ini has them now (None = key/section missing)."""

    subs_active: bool
    subs_count: int | None
    bench_active: bool
    bench_count: int | None


@dataclass(frozen=True)
class L9Applied:
    """What L9 reported applying at the last FIFA start (``dinput8_L9.log``).

    ``cbac_ok``: True when SubsOn's 12-place ant.cbac was found, False when L9 said the places are
    missing, None when the log does not say. ``stale``: the ini was saved after that start, so the
    log does not reflect it yet (applies at the next start)."""

    subs: int | None
    bench: int | None
    bench_requested_not_set: int | None
    cbac_ok: bool | None
    stale: bool


def _is_l9_dll(path: Path) -> bool:
    try:
        return _L9_DLL_MARKER in path.read_bytes()
    except OSError:
        return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def detect(game_dir: Path | None) -> ExtenderStatus:
    if game_dir is None:
        return ExtenderStatus(False, None, False, None)
    game_dir = Path(game_dir)
    l9_installed = (game_dir / L9_INI_NAME).is_file() and _is_l9_dll(game_dir / L9_DLL_NAME)
    l9_version = None
    if l9_installed:
        log = _read_text(game_dir / L9_LOG_NAME)
        match = _LOG_VERSION_RE.search(log or "")
        l9_version = match.group(1) if match else None
    ge_installed = (game_dir / GAMEPLAY_EXTENDER_DLL_NAME).is_file()
    ge_version = None
    if ge_installed:
        match = _GE_VERSION_RE.search(_read_text(game_dir / GAMEPLAY_EXTENDER_LOG_NAME) or "")
        ge_version = match.group(1) if match else None
    return ExtenderStatus(l9_installed, l9_version, ge_installed, ge_version)


def _strip_comment(value: str) -> str:
    for marker in (";", "#"):
        index = value.find(marker)
        if index != -1:
            value = value[:index]
    return value.strip()


def _section_values(text: str, section: str) -> dict[str, str]:
    """Keys of one section (case-insensitive names, last occurrence wins, comments stripped)."""
    values: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            current = header.group(1).strip().lower()
            continue
        if current != section.lower() or "=" not in line or line.lstrip().startswith((";", "#")):
            continue
        key, _, value = line.partition("=")
        values[key.strip().lower()] = _strip_comment(value)
    return values


def _as_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def read_values(ini_path: Path) -> L9Values | None:
    text = _read_text(Path(ini_path))
    if text is None:
        return None
    subs = _section_values(text, SUBS_SECTION)
    bench = _section_values(text, BENCH_SECTION)
    return L9Values(
        subs_active=_as_int(subs.get("aktiv")) == 1,
        subs_count=_as_int(subs.get("anzahl")),
        bench_active=_as_int(bench.get("aktiv")) == 1,
        bench_count=_as_int(bench.get("bank")),
    )


def validate(subs: int, bench: int) -> str | None:
    """Error code for the UI, or None. Codes: subs_range, bench_range, subs_over_bench."""
    if not L9_SUBS_MIN <= subs <= L9_SUBS_MAX:
        return "subs_range"
    if not L9_BENCH_MIN <= bench <= L9_BENCH_MAX:
        return "bench_range"
    if subs > bench:
        return "subs_over_bench"
    return None


def _set_section_keys(lines: list[str], section: str, updates: dict[str, str], newline: str) -> list[str]:
    """Set ``key=value`` for each update inside ``[section]``: the value of an existing key is
    replaced in place (inline comment kept), a missing key is inserted right after the header, a
    missing section is appended at the end of the file."""
    start = end = None
    for index, line in enumerate(lines):
        header = _SECTION_RE.match(line)
        if header is None:
            continue
        if start is not None:
            end = index
            break
        if header.group(1).strip().lower() == section.lower():
            start = index
    if start is None:
        result = list(lines)
        if result and not result[-1].endswith(("\n", "\r")):
            result[-1] += newline
        if result and result[-1].strip():
            result.append(newline)   # blank line before the new section
        result.append(f"[{section}]{newline}")
        result.extend(f"{key}={value}{newline}" for key, value in updates.items())
        return result
    if end is None:
        end = len(lines)
    pending = dict(updates)
    result = list(lines)
    for index in range(start + 1, end):
        line = result[index]
        if "=" not in line or line.lstrip().startswith((";", "#")):
            continue
        key, sep, rest = line.partition("=")
        name = key.strip()
        match_key = next((k for k in pending if k.lower() == name.lower()), None)
        if match_key is None:
            continue
        body = rest.rstrip("\r\n")
        line_end = rest[len(body):]
        comment_at = min((i for i in (body.find(";"), body.find("#")) if i != -1), default=-1)
        comment = ""
        if comment_at != -1:
            raw_value = body[:comment_at]
            spacing = raw_value[len(raw_value.rstrip()):] or " "
            comment = spacing + body[comment_at:]
        result[index] = f"{key}{sep}{pending.pop(match_key)}{comment}{line_end}"
    if pending:
        insert = [f"{key}={value}{newline}" for key, value in pending.items()]
        result[start + 1:start + 1] = insert
    return result


def write_values(ini_path: Path, subs: int, bench: int) -> None:
    """Save the substitution count and bench size into L9's ini (``Aktiv=1`` for both sections).

    Validates first (ValueError with the ``validate`` code). Keeps every other byte of the file:
    encoding, line endings, comments, other sections. A copy of the previous file goes to
    ``dinput8_L9.ini.cgfs16.bak`` and the new file replaces the old one atomically."""
    error = validate(subs, bench)
    if error is not None:
        raise ValueError(error)
    ini_path = Path(ini_path)
    raw = ini_path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw[3 if bom else 0:].decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        encoding = "cp1252"
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    lines = _set_section_keys(lines, SUBS_SECTION, {"Aktiv": "1", "Anzahl": str(subs)}, newline)
    lines = _set_section_keys(lines, BENCH_SECTION, {"Aktiv": "1", "Bank": str(bench)}, newline)
    data = "".join(lines).encode(encoding, errors="replace")
    if bom:
        data = b"\xef\xbb\xbf" + data
    if data == raw:
        return
    backup = ini_path.with_name(ini_path.name + L9_BACKUP_SUFFIX)
    backup.write_bytes(raw)
    temp = ini_path.with_name(ini_path.name + ".cgfs16.tmp")
    temp.write_bytes(data)
    os.replace(temp, ini_path)


def read_applied(game_dir: Path) -> L9Applied | None:
    """Parse the last ``dinput8_L9.log``; None when there is no log yet."""
    game_dir = Path(game_dir)
    log_path = game_dir / L9_LOG_NAME
    text = _read_text(log_path)
    if text is None:
        return None
    subs = bench = not_set = None
    cbac_ok = None
    for line in text.splitlines():
        if (match := _LOG_SUBS_RE.search(line)) is not None:
            subs = int(match.group(1))
        elif (match := _LOG_BENCH_RE.search(line)) is not None:
            bench = int(match.group(1))
        elif (match := _LOG_BENCH_NOT_SET_RE.search(line)) is not None:
            not_set = int(match.group(1))
        elif (match := _LOG_CBAC_RE.search(line)) is not None:
            cbac_ok = match.group(1).lower() == "vorhanden"
    stale = False
    try:
        stale = (game_dir / L9_INI_NAME).stat().st_mtime > log_path.stat().st_mtime
    except OSError:
        pass
    return L9Applied(subs=subs, bench=bench, bench_requested_not_set=not_set, cbac_ok=cbac_ok, stale=stale)
