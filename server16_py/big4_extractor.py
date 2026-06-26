"""
Extract specific FSW source files from FIFA 16's BIG4 game archives.

BIG4 stores files uncompressed; extraction is a seek + read at the indexed offset.
Files are matched by their basename and written to target directories.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable


def _parse_index(big_path: Path) -> list[tuple[int, int, str]]:
    """Return list of (offset, size, name) from a BIG4 archive."""
    with open(big_path, "rb") as f:
        if f.read(4) != b"BIG4":
            return []
        f.read(4)  # total archive size
        num_files = struct.unpack(">I", f.read(4))[0]
        f.read(4)  # data start offset
        entries: list[tuple[int, int, str]] = []
        for _ in range(num_files):
            offset = struct.unpack(">I", f.read(4))[0]
            size = struct.unpack(">I", f.read(4))[0]
            name_bytes = bytearray()
            while True:
                b = f.read(1)
                if not b or b == b"\x00":
                    break
                name_bytes += b
            entries.append((offset, size, name_bytes.decode("ascii", errors="replace")))
    return entries


def _extract_matching(
    big_path: Path,
    rules: list[tuple[str, Path]],
    log: Callable[[str], None] | None = None,
) -> int:
    """
    Extract entries from big_path whose basename contains a rule pattern.

    rules: list of (pattern, dest_dir) — first match wins.
    Returns count of files written or already up-to-date.
    """
    if not big_path.exists():
        return 0

    entries = _parse_index(big_path)
    count = 0

    with open(big_path, "rb") as f:
        for offset, size, name in entries:
            basename = Path(name).name
            dest_dir: Path | None = None
            for pattern, target_dir in rules:
                if pattern in basename:
                    dest_dir = target_dir
                    break
            if dest_dir is None:
                continue

            dest_file = dest_dir / basename
            if dest_file.exists() and dest_file.stat().st_size == size:
                count += 1
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)
            f.seek(offset)
            dest_file.write_bytes(f.read(size))
            count += 1
            if log:
                log(f"  extracted: {basename}")

    return count


def extract_fsw_sources(
    exedir: Path,
    fsw_dir: Path,
    log: Callable[[str], None] | None = None,
) -> None:
    """
    Extract vanilla FIFA 16 game files from the installation's .big archives
    into the FSW source directories that CGFS16 uses as base textures.

    Populates:
      FSW/Police/          — all policeofficer_*.rx3 variants
      FSW/Nets/            — all netcolor_*_textures.rx3 variants
      FSW/PitchMowPattern/ — all pitchmowpattern_*_textures.rx3 variants
      FSW/Stadium/crowdplacement/ — crowd_176/261 placement data
      FSW/Stadium/fx/      — glares_176/261 light effect files
      FSW/Stadium/stadium/ — default stadium_176/261 model + textures
    """
    police_dir = fsw_dir / "Police"
    nets_dir = fsw_dir / "Nets"
    pitch_dir = fsw_dir / "PitchMowPattern"
    crowdplace_dir = fsw_dir / "Stadium" / "crowdplacement"
    fx_dir = fsw_dir / "Stadium" / "fx"
    stadium_dir = fsw_dir / "Stadium" / "stadium"

    # data_graphic2.big: police variants 5, 6, 9 — nets 0-17 — pitch 0-15
    g2 = exedir / "data_graphic2.big"
    if log:
        log(f"BIG4: scanning {g2.name}")
    _extract_matching(g2, [
        ("policeofficer_", police_dir),
        ("netcolor_", nets_dir),
        ("pitchmowpattern_", pitch_dir),
    ], log)

    # data_graphic2_extra.big: police 1-4, 7, 8, 10 — crowdplacement 176/261 — glares 176/261
    g2x = exedir / "data_graphic2_extra.big"
    if log:
        log(f"BIG4: scanning {g2x.name}")
    _extract_matching(g2x, [
        ("policeofficer_", police_dir),
        ("crowd_176_", crowdplace_dir),
        ("crowd_261_", crowdplace_dir),
        ("glares_176_", fx_dir),
        ("glares_261_", fx_dir),
    ], log)

    # data_graphic1_extra.big: default stadium_176 and stadium_261 meshes + textures
    g1x = exedir / "data_graphic1_extra.big"
    if log:
        log(f"BIG4: scanning {g1x.name}")
    _extract_matching(g1x, [
        ("stadium_176", stadium_dir),
        ("stadium_261", stadium_dir),
    ], log)
