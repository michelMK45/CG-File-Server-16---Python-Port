"""Installs the CGFS16 in-game menu (FIFA 16's own UI, built by the cgfs-ingame project) into the game.

The menu's files come prebuilt in the release package resources/ingame/mod (cgfs-ingame:
`python tools/ingame.py release --out ../repository/resources/ingame/mod`): its screens, data movie and
images, plus one hooked KickOffHub movie (R3 on the pre-match hub) per known original of that file
(vanilla FIFA 16 and FIP's); a game with another KickOffHub gets the menu without R3 (and so without a way in).
The text patches (the nav flows that load the KickOffHub; between CGFS16-INGAME markers) are applied to
whatever files the game has now. The old CGFS16 tile in Customise > Edit Teams is no longer installed and is
taken out of a game that still has it (ingame_hubpatch.RETIRED).

ingame_modinstall.py and ingame_hubpatch.py are byte-identical copies of cgfs-ingame's modinstall.py and
hubpatch.py (stdlib only), so an install made with either tool is updated or removed by the other: both
keep <game>/_cgfs16_ingame/manifest.json. FIFA 16 must be closed (its .bh files are changed).
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import ingame_hubpatch, ingame_modinstall
from .file_tools import _bundled_resource_path

PACKAGE_INFO = "ingame/mod/" + ingame_modinstall.PACKAGE_INFO
GENERATED_DIR = Path("data/ui/cgfs16")   # data.big and the previews the app makes (ingame_images.py)
SOURCE = "CG Server 16"


class FifaRunning(RuntimeError):
    """FIFA 16 is open: the menu can only be installed or removed with it closed."""


@dataclass
class MenuStatus:
    installed: str | None      # build of the installed menu ("2026-11-11 12:53"), None if not installed
    bundled: str | None        # build of the package in this app, None if the app has none
    without_r3: bool = False   # installed, but the game's KickOffHub is not one the package knows

    @property
    def up_to_date(self) -> bool:
        return self.installed is not None and self.installed == self.bundled


def package_dir() -> Path | None:
    info = _bundled_resource_path(PACKAGE_INFO)
    return info.parent if info is not None else None


def bundled_build() -> str | None:
    folder = package_dir()
    if folder is None:
        return None
    try:
        return json.loads((folder / ingame_modinstall.PACKAGE_INFO).read_text(encoding="utf-8")).get("installed")
    except (OSError, ValueError):
        return None


def _game(exedir: str | Path) -> ingame_modinstall.GameFiles:
    return ingame_modinstall.GameFiles(str(exedir))


def status(exedir: str | Path) -> MenuStatus:
    man = None
    try:
        man = ingame_modinstall.load_manifest(_game(exedir))
    except (OSError, ValueError):
        pass
    if not man or not man.get("created"):
        return MenuStatus(None, bundled_build())
    return MenuStatus(man.get("installed") or "?", bundled_build(), bool(man.get("skipped")))


def install(exedir: str | Path, log: Callable[[str], None]) -> MenuStatus:
    """Installs or updates the menu from the bundled package. Raises FifaRunning, FileNotFoundError (no
    package / not a FIFA 16 folder) or ValueError (a game file lacks what a patch anchors on)."""
    folder = package_dir()
    if folder is None:
        raise FileNotFoundError("resources/ingame/mod (the in-game menu package) is not in this build")
    if ingame_modinstall.game_running():
        raise FifaRunning("FIFA 16 is running")
    game = _game(exedir)
    info, files = ingame_modinstall.load_package(str(folder))
    info["source"] = SOURCE
    man = ingame_modinstall.install(game, files, ingame_hubpatch.PATCHES, info,
                                    check=ingame_hubpatch.check_patched, log=lambda m: log(f"In-game menu: {m}"),
                                    unpatch=ingame_hubpatch.UNPATCH)   # also takes out the old hub tile
    log(f"In-game menu: installed (build {info.get('installed')}, {len(man['created'])} files, "
        f"{len(man['patched'])} patched{', no R3: unknown KickOffHub' if man.get('skipped') else ''})")
    return status(exedir)


def uninstall(exedir: str | Path, log: Callable[[str], None]) -> bool:
    """Removes the menu (also the data and previews the app wrote for it). False if it was not installed."""
    if ingame_modinstall.game_running():
        raise FifaRunning("FIFA 16 is running")
    removed = ingame_modinstall.uninstall(_game(exedir), ingame_hubpatch.PATCHES,
                                          log=lambda m: log(f"In-game menu: {m}"), unpatch=ingame_hubpatch.UNPATCH)
    shutil.rmtree(Path(exedir) / GENERATED_DIR, ignore_errors=True)
    if removed:
        log("In-game menu: uninstalled")
    return removed
