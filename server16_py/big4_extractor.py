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
    skip: set[str] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """
    Extract vanilla FIFA 16 game files from the installation's .big archives
    into the FSW source directories that CGFS16 uses as base textures.

    Populates:
      FSW/Police/          — all policeofficer_*.rx3 variants
      FSW/Nets/            — all netcolor_*_textures.rx3 variants
      FSW/PitchMowPattern/ — all pitchmowpattern_*_textures.rx3 variants
      FSW/GoalNet/         — default goalnet_*.rx3 / goalpost_*.rx3(_textures) models
      FSW/Stadium/crowdplacement/ — crowd_176/261 placement data
      FSW/Stadium/fx/      — glares_176/261 light effect files
      FSW/Stadium/stadium/ — default stadium_176/261 model + textures
      FSW/ScoreBoard/overlays/                      — overlay_9*.big scoreboard files
      FSW/ScoreBoard/globalcomponents/overlaycomponents_9/ — overlaycomponents_9.big
      FSW/TVLogo/          — overlay_9105.big default TV logo

    skip: optional set of category names to omit — "police", "nets", "pitch", "goalnet",
          "stadium", "scoreboard", "tvlogo"
    """
    skip = skip or set()

    police_dir = fsw_dir / "Police"
    nets_dir = fsw_dir / "Nets"
    pitch_dir = fsw_dir / "PitchMowPattern"
    goalnet_dir = fsw_dir / "GoalNet"
    crowdplace_dir = fsw_dir / "Stadium" / "crowdplacement"
    fx_dir = fsw_dir / "Stadium" / "fx"
    stadium_dir = fsw_dir / "Stadium" / "stadium"
    scoreboard_overlays_dir = fsw_dir / "ScoreBoard" / "overlays"
    scoreboard_components_dir = fsw_dir / "ScoreBoard" / "globalcomponents" / "overlaycomponents_9"
    tvlogo_dir = fsw_dir / "TVLogo"

    # data_graphic2.big: police variants 5, 6, 9 — nets 0-17 — pitch 0-15 —
    # default goalnet_0/1.rx3 + goalpost_0/1.rx3(_textures)
    g2 = exedir / "data_graphic2.big"
    rules_g2 = []
    if "police" not in skip:
        rules_g2.append(("policeofficer_", police_dir))
    if "nets" not in skip:
        rules_g2.append(("netcolor_", nets_dir))
    if "pitch" not in skip:
        rules_g2.append(("pitchmowpattern_", pitch_dir))
    if "goalnet" not in skip:
        rules_g2.append(("goalnet_", goalnet_dir))
        rules_g2.append(("goalpost_", goalnet_dir))

    # data_front_end.big: scoreboard overlay files and TV logo
    rules_fe = []
    if "scoreboard" not in skip:
        rules_fe.append(("overlaycomponents_9", scoreboard_components_dir))
    if "tvlogo" not in skip:
        rules_fe.append(("overlay_9105", tvlogo_dir))  # must precede overlay_9 rule
    if "scoreboard" not in skip:
        rules_fe.append(("overlay_9", scoreboard_overlays_dir))

    steps_done = 0
    total_steps = sum([bool(rules_g2), True, "stadium" not in skip, bool(rules_fe)])

    if rules_g2:
        if log:
            log(f"BIG4: scanning {g2.name}")
        _extract_matching(g2, rules_g2, log)
        steps_done += 1
        if on_progress:
            on_progress(steps_done, total_steps)

    # data_graphic2_extra.big: police 1-4, 7, 8, 10 — crowdplacement 176/261 — glares 176/261
    g2x = exedir / "data_graphic2_extra.big"
    rules_g2x = []
    if "police" not in skip:
        rules_g2x.append(("policeofficer_", police_dir))
    if "stadium" not in skip:
        rules_g2x += [
            ("crowd_176_", crowdplace_dir),
            ("crowd_261_", crowdplace_dir),
            ("glares_176_", fx_dir),
            ("glares_261_", fx_dir),
        ]
    if rules_g2x:
        if log:
            log(f"BIG4: scanning {g2x.name}")
        _extract_matching(g2x, rules_g2x, log)
    steps_done += 1
    if on_progress:
        on_progress(steps_done, total_steps)

    # data_graphic1_extra.big: default stadium_176 and stadium_261 meshes + textures
    if "stadium" not in skip:
        g1x = exedir / "data_graphic1_extra.big"
        if log:
            log(f"BIG4: scanning {g1x.name}")
        _extract_matching(g1x, [
            ("stadium_176", stadium_dir),
            ("stadium_261", stadium_dir),
        ], log)
        steps_done += 1
        if on_progress:
            on_progress(steps_done, total_steps)

    # data_front_end.big: scoreboard overlays and default TV logo
    if rules_fe:
        fe = exedir / "data_front_end.big"
        if log:
            log(f"BIG4: scanning {fe.name}")
        _extract_matching(fe, rules_fe, log)
        steps_done += 1
        if on_progress:
            on_progress(steps_done, total_steps)
