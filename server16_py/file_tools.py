from __future__ import annotations

import random
import shutil
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



def is_archive(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix == ".zip" or (suffix == ".rar" and _RAR_AVAILABLE)


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
