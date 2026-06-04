from __future__ import annotations

import random
import shutil
import subprocess
import unicodedata
import zipfile
from pathlib import Path

try:
    import rarfile
    _RAR_AVAILABLE = True
except ImportError:
    _RAR_AVAILABLE = False

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

    previews = stadium_preview_dir(root)
    if previews.exists():
        for item in previews.iterdir():
            if item.is_file() and item.suffix.lower() in STADIUM_PREVIEW_SUFFIXES:
                add(item.stem)

    return sorted(names.values(), key=lambda value: _normalized_lookup_name(value))


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
    elif suffix == ".rar" and _RAR_AVAILABLE:
        with rarfile.RarFile(archive_path, "r") as rf:
            members = rf.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                rf.extract(member, dest_dir)
                if progress_callback:
                    progress_callback(index, total, member.filename)
    elif suffix == ".rar":
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
            _copy_file_if_needed(item, target)


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


def extra_setup(source_dir: str | Path, dest_dir: str | Path, source_index: str, asset_prefix: str, dest_index: str) -> None:
    src_root = Path(source_dir)
    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    if not src_root.exists():
        return
    token = f"_{source_index}"
    replacement = f"_{dest_index}"
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        target_name = item.name.replace(token, replacement) if token in item.name else item.name
        if asset_prefix.lower() not in target_name.lower() and asset_prefix not in {"4", "9"}:
            continue
        _copy_file_if_needed(item, dest_root / target_name)


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
