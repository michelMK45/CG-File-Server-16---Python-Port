from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import Server16App

# Offsets of the stadium name text fields inside fifa_ng_db.db
# These are the exact byte positions where the null-terminated name string lives.
# Each field can hold up to 198 characters (null-terminated within a 200-byte region).
DB_STADIUM_NAME_OFFSET_176 = 209270
DB_STADIUM_NAME_OFFSET_261 = 208346
DB_NAME_FIELD_SIZE = 198  # max chars, must be null-terminated within 200-byte region

# Original names to restore after the match (read from the DB at first patch)
_original_name_176: bytes | None = None
_original_name_261: bytes | None = None


def _is_valid_field_range(data_size: int, offset: int) -> bool:
    return 0 <= offset and (offset + DB_NAME_FIELD_SIZE) <= data_size


def _db_path(app: "Server16App") -> Path | None:
    candidate = app.exedir / "data" / "db" / "fifa_ng_db.db"
    if candidate.exists():
        return candidate
    return None


def _backup_path(app: "Server16App") -> Path:
    return app.exedir / "data" / "db" / "fifa_ng_db.db.bak"


def _read_name(data: bytes, offset: int) -> bytes:
    """Read the null-terminated name at the given offset."""
    chunk = data[offset:offset + DB_NAME_FIELD_SIZE]
    end = chunk.find(b"\x00")
    return chunk[:end] if end != -1 else chunk


def _write_name(path: Path, offset: int, name: str) -> None:
    """Write a null-terminated name at the given offset in the DB file."""
    encoded = name.encode("utf-8")[:DB_NAME_FIELD_SIZE - 1]
    payload = encoded + b"\x00" * (DB_NAME_FIELD_SIZE - len(encoded))
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(payload)


def patch_stadium_names(app: "Server16App", name_176: str, name_261: str) -> bool:
    """
    Overwrite the stadium names for slots 176 and 261 in the DB file.
    Saves the originals so they can be restored later.
    Returns True on success.
    """
    global _original_name_176, _original_name_261

    db = _db_path(app)
    if db is None:
        app.log("DB patcher: fifa_ng_db.db not found — skipping name patch")
        return False

    # Create a backup on first run
    bak = _backup_path(app)
    if not bak.exists():
        try:
            shutil.copy2(db, bak)
            app.log(f"DB patcher: backup created at {bak}")
        except Exception as exc:
            app.log("DB patcher: failed to create backup", exc)
            return False

    try:
        with open(db, "rb") as f:
            data = f.read()

        if not _is_valid_field_range(len(data), DB_STADIUM_NAME_OFFSET_176):
            app.log(
                f"DB patcher: offset out of range for slot 176 "
                f"(offset={DB_STADIUM_NAME_OFFSET_176}, size={len(data)})"
            )
            return False
        if not _is_valid_field_range(len(data), DB_STADIUM_NAME_OFFSET_261):
            app.log(
                f"DB patcher: offset out of range for slot 261 "
                f"(offset={DB_STADIUM_NAME_OFFSET_261}, size={len(data)})"
            )
            return False

        # Save originals before first patch
        if _original_name_176 is None:
            _original_name_176 = _read_name(data, DB_STADIUM_NAME_OFFSET_176)
        if _original_name_261 is None:
            _original_name_261 = _read_name(data, DB_STADIUM_NAME_OFFSET_261)

        _write_name(db, DB_STADIUM_NAME_OFFSET_176, name_176)
        _write_name(db, DB_STADIUM_NAME_OFFSET_261, name_261)
        app.log(f"DB patcher: patched name 176='{name_176}' 261='{name_261}'")
        return True

    except Exception as exc:
        app.log("DB patcher: failed to patch stadium names", exc)
        return False


def restore_stadium_names(app: "Server16App") -> None:
    """
    Restore the original stadium names in the DB file.
    Called after the match ends or on close.
    """
    global _original_name_176, _original_name_261

    db = _db_path(app)
    if db is None:
        return

    try:
        with open(db, "rb") as f:
            data = f.read()
        if not _is_valid_field_range(len(data), DB_STADIUM_NAME_OFFSET_176):
            app.log(
                f"DB patcher: restore aborted, offset out of range for slot 176 "
                f"(offset={DB_STADIUM_NAME_OFFSET_176}, size={len(data)})"
            )
            return
        if not _is_valid_field_range(len(data), DB_STADIUM_NAME_OFFSET_261):
            app.log(
                f"DB patcher: restore aborted, offset out of range for slot 261 "
                f"(offset={DB_STADIUM_NAME_OFFSET_261}, size={len(data)})"
            )
            return

        if _original_name_176 is not None:
            name = _original_name_176.decode("utf-8", errors="replace")
            _write_name(db, DB_STADIUM_NAME_OFFSET_176, name)
        if _original_name_261 is not None:
            name = _original_name_261.decode("utf-8", errors="replace")
            _write_name(db, DB_STADIUM_NAME_OFFSET_261, name)
        app.log("DB patcher: original stadium names restored")
        # Clear cached originals after a successful restore to avoid stale values
        # being reused across unrelated runs.
        _original_name_176 = None
        _original_name_261 = None
    except Exception as exc:
        app.log("DB patcher: failed to restore stadium names", exc)
