"""Text-preserving editor for third-party plugin inis (the Plugins tab's ⚙ dialog).

Plugin inis (``plugins\\adboards.ini``, ``Gameplay_Extender.ini``…) are hand-written: inline ``;``
comments, repeated keys (``148 = 1`` twice), commented-out entries the user may want back
(``; 435 = 1``), ``//`` comments, UTF-8 or cp1252 text. configparser / ``SessionIniFile`` would
reorder, reject or rewrite them, so this module keeps the file as its original lines and only ever
rewrites the value span of the line the user edited. An unchanged document gives back the exact
bytes it was read from.

Rules:
- comment line: after leading whitespace it starts with ``;``, ``#`` or ``//``;
- section header: ``[name]``; keys before any header belong to section ``""``;
- field: any other line containing ``=``; key = text before the first ``=``;
- inline comment: the first ``;`` or ``#`` preceded by whitespace, searched from the second character
  of the value — so ``color=#ff0000`` and ``abc;1`` stay whole values;
- help text of a field: the contiguous comment lines right above it, plus its inline comment; a
  commented-out entry with its own inline comment (``; 435 = 1   ; League One``) is not help and
  ends the block.

See docs/superpowers/specs/2026-11-20-plugins-tab-design.md §6.2.
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path

BACKUP_SUFFIX = ".cgfs16.bak"
_TEMP_SUFFIX = ".cgfs16.tmp"
_BOM = b"\xef\xbb\xbf"
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")
_COMMENT_MARKERS = (";", "#", "//")


class IniChangedOnDisk(Exception):
    """The ini on disk is no longer the bytes the document was loaded from."""


@dataclass(frozen=True)
class IniField:
    line_index: int
    section: str
    key: str
    value: str
    help: str


@dataclass(frozen=True)
class _ValueSpan:
    prefix: str        # everything up to and including the spaces after '='
    value: str
    spacing: str       # whitespace between the value and the inline comment (or trailing spaces)
    comment: str       # inline comment including its marker, or ""
    ending: str        # "\r\n", "\n", "\r" or ""


def _split_ending(line: str) -> tuple[str, str]:
    body = line.rstrip("\r\n")
    return body, line[len(body):]


def _is_comment(body: str) -> bool:
    return body.lstrip().startswith(_COMMENT_MARKERS)


def _comment_text(comment: str) -> str:
    text = comment.strip()
    for marker in ("//", ";", "#"):
        if text.startswith(marker):
            return text[len(marker):].strip()
    return text


def _value_span(line: str) -> _ValueSpan | None:
    body, ending = _split_ending(line)
    if not body.strip() or _is_comment(body) or _SECTION_RE.match(body) or "=" not in body:
        return None
    key_part, _, rest = body.partition("=")
    after = rest.lstrip(" \t")
    prefix = key_part + "=" + rest[: len(rest) - len(after)]
    comment_at = -1
    for index in range(1, len(after)):
        if after[index] in ";#" and after[index - 1] in " \t":
            comment_at = index
            break
    if comment_at == -1:
        value = after.rstrip(" \t")
        return _ValueSpan(prefix, value, after[len(value):], "", ending)
    head = after[:comment_at]
    value = head.rstrip(" \t")
    return _ValueSpan(prefix, value, head[len(value):], after[comment_at:], ending)


def _is_commented_out_entry(comment_text: str) -> bool:
    """``; 435 = 1   ; League One`` — a switched-off entry (it has its own inline comment), as
    opposed to a description such as ``; 1 = angosto, 2 = ancho``."""
    span = _value_span(comment_text)
    return span is not None and bool(span.comment)


def _decode(raw: bytes) -> tuple[str, str, bool]:
    bom = raw.startswith(_BOM)
    data = raw[len(_BOM):] if bom else raw
    try:
        return data.decode("utf-8"), "utf-8", bom
    except UnicodeDecodeError:
        # surrogateescape keeps bytes cp1252 can't map, so an untouched file round-trips exactly.
        return data.decode("cp1252", errors="surrogateescape"), "cp1252", bom


class IniDocument:
    def __init__(self, lines: list[str], encoding: str, bom: bool, newline: str) -> None:
        self._lines = lines
        self.encoding = encoding
        self.bom = bom
        self.newline = newline

    @classmethod
    def from_bytes(cls, raw: bytes) -> "IniDocument":
        text, encoding, bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        return cls(text.splitlines(keepends=True), encoding, bom, newline)

    @classmethod
    def from_text(cls, text: str, like: "IniDocument") -> "IniDocument":
        """Document from edited text (the dialog's Text tab, which only knows ``\\n``), with
        ``like``'s encoding and BOM. Lines that match ``like``'s lines keep their own original
        ending (a mixed CRLF/LF file stays as it was); new or changed lines take the line ending
        of the line they replace, else ``like.newline``."""
        parts = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        last_has_ending = parts[-1] == ""
        if last_has_ending:
            parts.pop()
        old = [_split_ending(line) for line in like._lines]
        old_bodies = [body for body, _ in old]
        endings: list[str] = [""] * len(parts)
        matcher = difflib.SequenceMatcher(None, old_bodies, parts, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            for offset, j in enumerate(range(j1, j2)):
                i = i1 + offset
                if tag in ("equal", "replace") and i < i2:
                    endings[j] = old[i][1]
        lines = []
        for index, body in enumerate(parts):
            is_last = index == len(parts) - 1
            if is_last and not last_has_ending:
                ending = ""
            else:
                ending = endings[index] or like.newline
            lines.append(body + ending)
        return cls(lines, like.encoding, like.bom, like.newline)

    @property
    def text(self) -> str:
        return "".join(self._lines)

    def to_bytes(self) -> bytes:
        try:
            data = self.text.encode(self.encoding, errors="surrogateescape")
        except UnicodeEncodeError:
            data = self.text.encode(self.encoding, errors="replace")
        return _BOM + data if self.bom else data

    def fields(self) -> list[IniField]:
        result: list[IniField] = []
        section = ""
        pending_help: list[str] = []
        for index, line in enumerate(self._lines):
            body, _ = _split_ending(line)
            header = _SECTION_RE.match(body)
            if header and not _is_comment(body):
                section = header.group(1).strip()
                pending_help = []
                continue
            if _is_comment(body):
                text = _comment_text(body)
                if _is_commented_out_entry(text):
                    pending_help = []   # a disabled entry, not a description of the next key
                else:
                    pending_help.append(text)
                continue
            span = _value_span(line)
            if span is None:
                pending_help = []
                continue
            help_lines = list(pending_help)
            if span.comment:
                help_lines.append(_comment_text(span.comment))
            result.append(IniField(index, section, span.prefix.split("=", 1)[0].strip(), span.value,
                                   "\n".join(help_lines)))
            pending_help = []
        return result

    def set_value(self, line_index: int, value: str) -> None:
        """Replace the value of one ``key = value`` line (surrounding spaces of ``value`` are
        dropped). Raises ``ValueError`` for a value this module would read back differently —
        a line break, an empty value before an inline comment, or a value containing `` ;`` /
        `` #`` — so the line, and its comment, are never corrupted."""
        if not 0 <= line_index < len(self._lines):
            raise ValueError(f"line {line_index} is out of range")
        span = _value_span(self._lines[line_index])
        if span is None:
            raise ValueError(f"line {line_index} is not a key = value line")
        value = value.strip(" \t")
        if value == span.value:
            return
        if "\r" in value or "\n" in value:
            raise ValueError("a value cannot contain a line break")
        tail = span.spacing + span.comment if span.comment else ""
        line = span.prefix + value + tail + span.ending
        check = _value_span(line)
        if check is None or check.value != value or check.comment != span.comment:
            raise ValueError(f"{value!r} would not read back as the same value")
        self._lines[line_index] = line


def load(path: Path) -> tuple[IniDocument, bytes]:
    raw = Path(path).read_bytes()
    return IniDocument.from_bytes(raw), raw


def save(path: Path, doc: IniDocument, original_raw: bytes) -> bool:
    """Write ``doc`` over ``path`` if it changed. Refuses (``IniChangedOnDisk``) when the file on
    disk is no longer ``original_raw`` — e.g. the plugin's own editor saved it meanwhile. The
    previous bytes go to ``<name>.cgfs16.bak``; the new file replaces the old one atomically."""
    path = Path(path)
    try:
        current = path.read_bytes()
    except FileNotFoundError as exc:
        raise IniChangedOnDisk(str(path)) from exc
    if current != original_raw:
        raise IniChangedOnDisk(str(path))
    data = doc.to_bytes()
    if data == original_raw:
        return False
    path.with_name(path.name + BACKUP_SUFFIX).write_bytes(original_raw)
    temp = path.with_name(path.name + _TEMP_SUFFIX)
    temp.write_bytes(data)
    os.replace(temp, path)
    return True
