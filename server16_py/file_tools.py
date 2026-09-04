from __future__ import annotations

import importlib
import random
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

try:
    import rarfile as _rarmod
    # Windows ships with "tar" (bsdtar); tell rarfile to use it so that
    # extraction works even when unrar.exe / 7z are not installed.
    if sys.platform == "win32" and _rarmod.BSDTAR_TOOL == "bsdtar":
        _rarmod.BSDTAR_TOOL = "tar"
except ImportError:
    _rarmod = None


def _try_install_rarfile():
    """Attempt to pip-install/upgrade rarfile and return the module on success, None on failure."""
    if getattr(sys, "frozen", False):
        return None  # running as PyInstaller bundle — sys.executable is the app, not Python
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "rarfile"],
            capture_output=True,
            check=True,
        )
        return importlib.import_module("rarfile")
    except Exception:
        return None


def _extract_with_rarmod(archive_path: Path, dest_dir: Path, progress_callback) -> bool:
    """Extract RAR with _rarmod. Returns True on success, False if unrar tool is missing."""
    try:
        with _rarmod.RarFile(archive_path, "r") as rf:
            members = rf.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                rf.extract(member, dest_dir)
                if progress_callback:
                    progress_callback(index, total, member.filename)
        return True
    except Exception as exc:
        if "Cannot find working tool" in str(exc) or exc.__class__.__name__.endswith("CannotExec"):
            return False
        raise

try:
    from win32api import GetFileVersionInfo, HIWORD, LOWORD
except Exception:
    GetFileVersionInfo = None
    HIWORD = LOWORD = None


STADIUM_ARCHIVE_SUFFIXES = {".zip", ".rar"}
STADIUM_PREVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".jepg"}


def _normalized_lookup_name(value: str) -> str:
    return unicodedata.normalize("NFC", value or "").casefold()


def stadium_preview_dir(stadium_gbd: str | Path) -> Path:
    return Path(stadium_gbd) / "render" / "thumbnail" / "stadium"


def _bundled_resource_path(filename: str) -> Path | None:
    """Resolves a file under the bundled `resources/` folder.

    Checked against every base dir a `resources/` folder could live under, in the
    same order the app icon is resolved (§9 conventions): the PyInstaller MEIPASS
    bundle dir, then the dir next to the exe/repo root.
    """
    candidate_bases = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidate_bases.append(Path(bundle_dir))
    if getattr(sys, "frozen", False):
        candidate_bases.append(Path(sys.executable).resolve().parent)
    else:
        candidate_bases.append(Path(__file__).resolve().parent.parent)
    for base in candidate_bases:
        candidate = base / "resources" / filename
        if candidate.is_file():
            return candidate
    return None


def stadium_preview_fallback_path() -> Path | None:
    """Bundled generic image shown when a stadium has no preview of its own."""
    return _bundled_resource_path("stadium-placeholder.png")


def gamepad_button_icon_dir() -> Path | None:
    """Bundled resources/buttons/gamepad folder (a/b/dpad/lb/rb/rs/start icons)
    used by the D3D overlay's gamepad hint bar, or None if not found."""
    marker = _bundled_resource_path("buttons/gamepad/a.png")
    return marker.parent if marker is not None else None


def keyboard_button_icon_dir() -> Path | None:
    """Bundled resources/buttons/keyboard folder (up/down/left/right/enter/esc/
    mouse/space icons) used by the D3D overlay's keyboard hint bar, or None if
    not found."""
    marker = _bundled_resource_path("buttons/keyboard/up.png")
    return marker.parent if marker is not None else None


def rmlui_content_dir() -> Path | None:
    """Bundled resources/rmlui/ folder (toast.rml, stadium_panel.rml) that the
    D3D overlay's RmlUi renderer (cgfs16_rmlui.cpp) loads as loose files at
    runtime instead of from embedded C++ string literals — lets those
    documents be edited and re-tested (relaunch FIFA) without recompiling the
    DLL. Returns None if not found."""
    marker = _bundled_resource_path("rmlui/toast.rml")
    return marker.parent if marker is not None else None


def kit_ui_placeholder_path() -> Path | None:
    """Bundled generic image shown when a kit set has no kit UI thumbnail
    (kitui) of its own — used by the Simple Mode preview and the hotkey
    cycling overlay notification, instead of extracting a jersey texture."""
    return _bundled_resource_path("kit-ui-placeholder.png")


def rmlui_icon_path(name: str) -> Path | None:
    """Bundled resources/rmlui/icons/<name>.png — the same small icon set
    already used for toast notifications (see D3DOverlayInjector.show_toast's
    `icon` param). Also doubles as the generic placeholder for tabs (e.g.
    ScoreBoard/TVLogo) whose assets have no dedicated preview thumbnail of
    their own, the same fallback role stadium_preview_fallback_path()/
    kit_ui_placeholder_path() play for stadiums/kits."""
    return _bundled_resource_path(f"rmlui/icons/{name}.png")


def resolve_asset_thumbnail_path(folder: str | Path, key: str) -> Path | None:
    """Looks for a `<folder>/render/thumbnail/<key>.{png,jpg,jpeg}` preview
    image, falling back to the first image file in that thumbnail dir — the
    convention ScoreBoard/TVLogo asset packs use for their own thumbnails
    (originally implemented in dialogs.py's AssignmentDialog for the Setup
    preview panel; extracted here so the D3D overlay's menu preview can reuse
    the exact same lookup)."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    thumbnail_dir = folder / "render" / "thumbnail"
    if not thumbnail_dir.is_dir():
        return None
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = thumbnail_dir / f"{key}{ext}"
        if candidate.is_file():
            return candidate
    for candidate in sorted(thumbnail_dir.iterdir()):
        if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            return candidate
    return None


def resolve_movie_preview_path(folder: str | Path) -> Path | None:
    """The .vp8 file a Movies-tab asset folder carries, at the fixed
    filename this codebase has always used for it (asset_runtime.py's
    copy_if_exists() calls, dialogs.py's MovieDialog, settings_editor.py's
    Movies/TeamMovies/DerbyMatch tabs) — None if the folder or the file
    inside it doesn't exist."""
    candidate = Path(folder) / "bootflowoutro.vp8"
    return candidate if candidate.is_file() else None


def resolve_stadium_preview_path(stadium_gbd: str | Path, stadium_name: str) -> Path | None:
    stadium_name = (stadium_name or "").strip()
    if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
        return None
    preview_dir = stadium_preview_dir(stadium_gbd)
    if not preview_dir.exists():
        return None

    lookup_names = [stadium_name]
    stadium_suffix = Path(stadium_name).suffix.lower()
    if stadium_suffix in STADIUM_ARCHIVE_SUFFIXES:
        stem_name = Path(stadium_name).stem.strip()
        if stem_name:
            lookup_names.append(stem_name)

    for lookup_name in lookup_names:
        for suffix in sorted(STADIUM_PREVIEW_SUFFIXES):
            candidate = preview_dir / f"{lookup_name}{suffix}"
            if candidate.is_file():
                return candidate

    wanted = {_normalized_lookup_name(name) for name in lookup_names}
    for candidate in sorted(preview_dir.iterdir(), key=lambda path: path.name.lower()):
        if not candidate.is_file() or candidate.suffix.lower() not in STADIUM_PREVIEW_SUFFIXES:
            continue
        if _normalized_lookup_name(candidate.stem) in wanted:
            return candidate
    return None


def discover_stadium_names(stadium_gbd: str | Path) -> list[str]:
    root = Path(stadium_gbd)
    names: dict[str, str] = {}

    def add(name: str) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            return
        names.setdefault(_normalized_lookup_name(name), name)

    if root.exists():
        for item in root.iterdir():
            if item.name.startswith(".") or item.name.casefold() == "render":
                continue
            if item.is_dir():
                add(item.name)
            elif item.is_file() and item.suffix.lower() in STADIUM_ARCHIVE_SUFFIXES:
                add(item.stem)

    # Note: a preview thumbnail (render/thumbnail/stadium/*) never adds a stadium
    # name by itself - it only decorates one already found above via the real
    # folder/archive scan (see resolve_stadium_preview_path). A leftover/renamed
    # thumbnail with no matching model must never surface as a selectable
    # stadium on its own, since applying it crashes the load (no source to copy
    # from; see _resolve_stadium_source).

    return sorted(names.values(), key=lambda value: _normalized_lookup_name(value))


def stadium_country_code(stadium_name: str) -> str:
    """3-letter country-code prefix convention used by community stadium
    packs (e.g. "ARG - Estadio ..."); "Other" for anything that doesn't
    match. Shared by the desktop StadiumDialog country filter and the F12
    overlay's Stadiums country filter panel."""
    stadium_name = (stadium_name or "").strip()
    if not stadium_name or stadium_name == "None":
        return "Other"
    if " - " in stadium_name:
        code = stadium_name.split(" - ", 1)[0].strip().upper()
        if len(code) == 3 and code.isalpha():
            return code
    return "Other"


def stadium_country_counts(stadium_names: list[str]) -> dict[str, int]:
    """Maps country code -> number of stadiums with that code, for building
    a country filter list."""
    counts: dict[str, int] = {}
    for name in stadium_names:
        if name == "None":
            continue
        code = stadium_country_code(name)
        counts[code] = counts.get(code, 0) + 1
    return counts


def is_archive(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in STADIUM_ARCHIVE_SUFFIXES


def extract_archive(archive_path: Path, dest_dir: Path, progress_callback=None) -> None:
    suffix = archive_path.suffix.lower()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                zf.extract(member, dest_dir)
                if progress_callback:
                    progress_callback(index, total, member.filename)
    elif suffix == ".rar":
        global _rarmod
        if _rarmod is None:
            _rarmod = _try_install_rarfile()
        if _rarmod is not None and not _extract_with_rarmod(archive_path, dest_dir, progress_callback):
            # RarCannotExec: old rarfile without unrar — try upgrading to 4.x (native RAR5 support)
            upgraded = _try_install_rarfile()
            if upgraded is not None:
                _rarmod = upgraded
            if _rarmod is not None and not _extract_with_rarmod(archive_path, dest_dir, progress_callback):
                _rarmod = None  # upgraded but still broken — fall through to tar
        if _rarmod is None:
            startupinfo = None
            creationflags = 0
            if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                result = subprocess.run(
                    ["tar", "-xf", str(archive_path), "-C", str(dest_dir)],
                    capture_output=True,
                    text=True,
                    check=False,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("The system tar extractor is not available for RAR support") from exc
            if result.returncode != 0:
                details = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(f"Failed to extract RAR archive {archive_path.name}: {details or 'unknown error'}")
            if progress_callback:
                progress_callback(1, 1, archive_path.name)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path.suffix}")


def checkdirs(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _files_match(src: Path, dst: Path) -> bool:
    try:
        if not dst.exists() or not dst.is_file():
            return False
        src_stat = src.stat()
        dst_stat = dst.stat()
        return src_stat.st_size == dst_stat.st_size and src_stat.st_mtime_ns == dst_stat.st_mtime_ns
    except Exception:
        return False


def _copy_file_if_needed(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _files_match(src, dst):
        return False
    shutil.copy2(src, dst)
    return True


def copy(src: str | Path, dst: str | Path) -> None:
    src_path = Path(src)
    dst_path = Path(dst)
    checkdirs(dst_path)
    if not src_path.exists():
        return
    if src_path.is_file():
        target = dst_path if dst_path.suffix else dst_path / src_path.name
        _copy_file_if_needed(src_path, target)
        return
    for item in src_path.rglob("*"):
        rel = item.relative_to(src_path)
        target = dst_path / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            if item.suffix.lower() == ".png":
                continue
            if item.name.lower() in {"desktop.ini", "thumbs.db"}:
                continue
            _copy_file_if_needed(item, target)


def copy_goalpost(src_dir: Path, dst_dir: Path, manifest_path: Path, fsw_goalnet_dir: Path | None = None) -> None:
    """Copy GoalpostGBD files to goalnet, tracking them in a manifest for later cleanup."""
    clear_goalpost(dst_dir, manifest_path, fsw_goalnet_dir)
    if not src_dir.is_dir():
        return
    copied: list[str] = []
    for item in src_dir.rglob("*"):
        if not item.is_file() or item.suffix.lower() == ".png":
            continue
        rel = item.relative_to(src_dir)
        _copy_file_if_needed(item, dst_dir / rel)
        copied.append(str(rel))
    if copied:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("\n".join(copied), encoding="utf-8")


_GOALNET_DEFAULT_NAMES = (
    "goalnet_0.rx3", "goalnet_1.rx3",
    "goalpost_0.rx3", "goalpost_0_textures.rx3",
    "goalpost_1.rx3", "goalpost_1_textures.rx3",
)


def restore_goalnet_defaults(dst_dir: Path, fsw_goalnet_dir: Path) -> None:
    """Restore the vanilla goalnet/goalpost model files from the FSW backup (extracted
    from data_graphic2.big by Setup) so the live goalnet folder is never left without a
    valid loose file after a custom GoalpostGBD stadium is cleared. Without this, the
    engine has to fall back to reading these assets from the packed .big archive, and
    that specific loose-file-goes-missing transition is where a previously loaded
    goalpost model can be left visually stuck instead of reloading.
    """
    if not fsw_goalnet_dir.is_dir():
        return
    for name in _GOALNET_DEFAULT_NAMES:
        src = fsw_goalnet_dir / name
        if src.is_file():
            _copy_file_if_needed(src, dst_dir / name)


def clear_goalpost(dst_dir: Path, manifest_path: Path, fsw_goalnet_dir: Path | None = None) -> None:
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            target = dst_dir / line.strip()
            if target.is_file():
                target.unlink()
        manifest_path.unlink(missing_ok=True)
    if fsw_goalnet_dir is not None:
        restore_goalnet_defaults(dst_dir, fsw_goalnet_dir)


_BCGAMEPLAY_NAMES = ("bcgameplay_176.dat", "bcgameplay_261.dat")


def copy_bcgameplay(src_dir: Path, dst_dir: Path, restore_dir: Path) -> None:
    """Copy GameplayCamGBD files to bcdata/camera. If absent, restore originals from restore_dir or delete."""
    for name in _BCGAMEPLAY_NAMES:
        src = src_dir / name
        dst = dst_dir / name
        if src.is_file():
            _copy_file_if_needed(src, dst)
        else:
            fsw_src = restore_dir / name
            if fsw_src.is_file():
                _copy_file_if_needed(fsw_src, dst)
            elif dst.is_file():
                dst.unlink()


def clear_bcgameplay(dst_dir: Path, restore_dir: Path) -> None:
    """Restore original bcgameplay files from restore_dir, or delete them if no originals exist."""
    for name in _BCGAMEPLAY_NAMES:
        dst = dst_dir / name
        fsw_src = restore_dir / name
        if fsw_src.is_file():
            _copy_file_if_needed(fsw_src, dst)
        elif dst.is_file():
            dst.unlink()


def _stadium_inj_file_pairs(sceneassets_dir: Path, fsw_stadium_dir: Path, inj_id: str) -> list[tuple[Path, Path]]:
    sid = inj_id
    pairs = [
        (fsw_stadium_dir / "stadium" / f"stadium_{sid}.rx3", sceneassets_dir / "stadium" / f"stadium_{sid}.rx3"),
        (fsw_stadium_dir / "stadium" / f"stadium_{sid}_1_textures.rx3", sceneassets_dir / "stadium" / f"stadium_{sid}_1_textures.rx3"),
        (fsw_stadium_dir / "stadium" / f"stadium_{sid}_3_textures.rx3", sceneassets_dir / "stadium" / f"stadium_{sid}_3_textures.rx3"),
        (fsw_stadium_dir / "crowdplacement" / f"crowd_{sid}_1.dat", sceneassets_dir / "crowdplacement" / f"crowd_{sid}_1.dat"),
        (fsw_stadium_dir / "crowdplacement" / f"crowd_{sid}_3.dat", sceneassets_dir / "crowdplacement" / f"crowd_{sid}_3.dat"),
        (fsw_stadium_dir / "crowdchair" / f"specificchair_0_{sid}.rx3", sceneassets_dir / "crowdchair" / f"specificchair_0_{sid}.rx3"),
    ]
    for suffix in range(4):
        for day_night in ("1", "3"):
            pairs.append((
                fsw_stadium_dir / "fx" / f"glares_{sid}_{day_night}_{suffix}.rx3",
                sceneassets_dir / "fx" / f"glares_{sid}_{day_night}_{suffix}.rx3",
            ))
            pairs.append((
                fsw_stadium_dir / "fx" / f"glares_{sid}_{day_night}_{suffix}.lnx",
                sceneassets_dir / "fx" / f"glares_{sid}_{day_night}_{suffix}.lnx",
            ))
    return pairs


def restore_stadium_inj_files(sceneassets_dir: Path, fsw_stadium_dir: Path, inj_id: str) -> None:
    """Reset a stadium injection slot back to the vanilla default, restoring each file
    from the FSW/Stadium backup extracted by Setup — or deleting it if no backup exists.

    Used to free up the "other" (currently unused) injection slot before writing a new
    custom stadium into the active one. Leaving that slot as a complete vanilla stadium
    — rather than emptying it outright — means a later BH regen or the game itself always
    finds valid content there instead of nothing, so that slot never gets stuck showing a
    broken/missing stadium until the next full Setup run.
    """
    for src, dst in _stadium_inj_file_pairs(sceneassets_dir, fsw_stadium_dir, inj_id):
        copy_or_clear(src, dst)


def sync_tree(src: str | Path, dst: str | Path, *, skip_suffixes: set[str] | None = None) -> int:
    src_path = Path(src)
    dst_path = Path(dst)
    suffixes = {suffix.lower() for suffix in (skip_suffixes or set())}
    if not src_path.exists():
        return 0
    if src_path.is_file():
        if src_path.suffix.lower() in suffixes:
            return 0
        return 1 if _copy_file_if_needed(src_path, dst_path) else 0
    dst_path.mkdir(parents=True, exist_ok=True)
    src_entries = {item.name: item for item in src_path.iterdir()}
    for existing in list(dst_path.iterdir()):
        if existing.name in src_entries:
            continue
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink(missing_ok=True)
    copied = 0
    for name, source_item in src_entries.items():
        target = dst_path / name
        if source_item.is_dir():
            copied += sync_tree(source_item, target, skip_suffixes=suffixes)
        else:
            if source_item.suffix.lower() in suffixes:
                continue
            copied += 1 if _copy_file_if_needed(source_item, target) else 0
    return copied


def copy_if_exists(src: str | Path, dst: str | Path) -> None:
    src_path = Path(src)
    if not src_path.exists():
        return
    _copy_file_if_needed(src_path, Path(dst))


def _is_cgfs_general_lua(text: str, template_text: str) -> bool:
    """True if `text` is CGFS's bundled general.lua, unmodified or with the
    kit-number toggle already applied by set_kit_number_scheme()."""
    normalized = text.replace("disableOriginalKitNumberIdentifier()", "useOriginalKitNumberIdentifier()")
    return normalized == template_text


def general_lua_is_foreign(general_lua_path: str | Path, template_path: str | Path) -> bool:
    """True if general_lua_path exists but isn't recognized as CGFS's bundled general.lua.

    Used to detect a total-conversion mod's own general.lua (e.g. FIFA Infinity)
    before offering to toggle the kit-number scheme on it.
    """
    path = Path(general_lua_path)
    template = Path(template_path)
    if not path.exists() or not template.exists():
        return False
    return not _is_cgfs_general_lua(path.read_text(encoding="utf-8"), template.read_text(encoding="utf-8"))


def set_kit_number_scheme(
    general_lua_path: str | Path,
    custom: bool,
    template_path: str | Path | None = None,
) -> bool:
    """Toggle which kit-number texture naming scheme general.lua asks the engine to use.

    Community kitnumbers_X_Y.rx3 font packs are built against one of two
    conventions; whichever one general.lua doesn't select shows a
    checkerboard/missing-texture placeholder for every font using it.

    If template_path is given, the file is only edited when its contents match
    the CGFS-bundled template (see _is_cgfs_general_lua) — a total-conversion
    mod's own general.lua (e.g. FIFA Infinity) is left untouched so this never
    silently overwrites a working mod's Lua config.

    Returns True if the file was updated, False if left untouched (missing,
    already in the desired state, or not recognized as CGFS's own file).
    """
    path = Path(general_lua_path)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")

    if template_path is not None:
        template = Path(template_path)
        if not template.exists():
            return False
        if not _is_cgfs_general_lua(text, template.read_text(encoding="utf-8")):
            return False

    target_call = "disableOriginalKitNumberIdentifier()" if custom else "useOriginalKitNumberIdentifier()"
    other_call = "useOriginalKitNumberIdentifier()" if custom else "disableOriginalKitNumberIdentifier()"
    if other_call in text:
        path.write_text(text.replace(other_call, target_call, 1), encoding="utf-8")
        return True
    return False


def copy_or_clear(src: str | Path, dst: str | Path) -> None:
    """Copy src to dst if it exists; otherwise delete any stale dst left by a previous stadium."""
    src_path = Path(src)
    dst_path = Path(dst)
    if src_path.exists():
        _copy_file_if_needed(src_path, dst_path)
    else:
        dst_path.unlink(missing_ok=True)


def copy_tvlogo(src: str | Path, dst: str | Path) -> str:
    src_path = Path(src)
    if not src_path.exists():
        return "default"
    dst_path = Path(dst)
    dst_path.mkdir(parents=True, exist_ok=True)
    if src_path.is_file():
        shutil.copyfile(src_path, dst_path / src_path.name)
        return "default"
    files = sorted(item for item in src_path.iterdir() if item.is_file())
    if not files:
        return "default"
    first_name = files[0].stem
    if "overlay_9105" in first_name:
        _copy_file_if_needed(files[0], dst_path / files[0].name)
        return "default"
    chosen = random.choice(files)
    tvlogo_type = chosen.name.split("_", 1)[0]
    _copy_file_if_needed(chosen, dst_path / "overlay_9105.big")
    return tvlogo_type


def copy_glares(src: str | Path, day_or_night: str, index: str, inj_id: str, exedir: str | Path) -> None:
    src_path = Path(src)
    if not src_path.exists():
        return
    dst = Path(exedir) / "data" / "sceneassets" / "fx" / f"glares_{inj_id}_{day_or_night}_{index}.lnx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    lines = src_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    rewritten: list[str] = []
    for line in lines:
        if 'name="glares' in line:
            parts = line.split("_")
            if len(parts) > 1:
                old_id = parts[1]
                line = line.replace(f"glares_{old_id}", f"glares_{inj_id}", 1)
        rewritten.append(line)
    dst.write_text("\r\n".join(rewritten) + "\r\n", encoding="utf-8")


def extra_setup(source_dir: str | Path, dest_dir: str | Path, source_index: str, asset_prefix: str, dest_index: str) -> list[str]:
    """Copy files from source_dir matching "{asset_prefix}_{source_index}_" into dest_dir,
    renaming "_{source_index}" to "_{dest_index}" in the destination filename. Returns the
    list of destination filenames actually written, so callers can log/verify a match was
    found rather than silently no-op'ing when source_index doesn't correspond to any file."""
    src_root = Path(source_dir)
    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    if not src_root.exists():
        return []
    token = f"_{source_index}"
    replacement = f"_{dest_index}"
    check = f"{asset_prefix}_{source_index}_"
    copied: list[str] = []
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        if check.lower() not in item.name.lower():
            continue
        target_name = item.name.replace(token, replacement)
        _copy_file_if_needed(item, dest_root / target_name)
        copied.append(target_name)
    return copied


def apply_specific_net_color(source_dir: str | Path, dest_dir: str | Path, source_index: str, stadium_id: str) -> list[str]:
    """Copy the netcolor_{source_index}_* variant into dest_dir as specificnetcolor_0_{stadium_id}_*.

    goalnet.lua's GetRMNetColour() checks this slot-specific path before falling back to the
    shared netcolor_0_* file that extra_setup() always overwrites. Since stadium_id (the 176/261
    injection slot) alternates every stadium load, this gives the engine a path it has not
    already cached this session — the plain netcolor_0_* overwrite alone only ever takes effect
    on the very first load after a game restart, because the engine never re-reads a path it has
    already resolved once.
    """
    src_root = Path(source_dir)
    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    if not src_root.exists():
        return []
    check = f"netcolor_{source_index}_"
    copied: list[str] = []
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        if check.lower() not in item.name.lower():
            continue
        suffix = item.name[len(check):]
        target_name = f"specificnetcolor_0_{stadium_id}_{suffix}"
        _copy_file_if_needed(item, dest_root / target_name)
        copied.append(target_name)
    return copied


def checkver(_fifa_exe: str) -> str:
    if not _fifa_exe or GetFileVersionInfo is None:
        return "unknown"
    try:
        info = GetFileVersionInfo(_fifa_exe, "\\")
        ms = info["FileVersionMS"]
        ls = info["FileVersionLS"]
        return ".".join(str(part) for part in (HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)))
    except Exception:
        return "unknown"


def inc_count(_count1: int, current: str) -> str:
    return "1" if current == "0" else "0"


def set_inj_id(counter: str) -> tuple[str, str]:
    return ("176", "4") if counter == "0" else ("261", "9")
