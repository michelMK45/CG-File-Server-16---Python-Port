from __future__ import annotations

import random
import shutil
import zipfile
from pathlib import Path

try:
    import rarfile
    _RARFILE_AVAILABLE = True
except ImportError:
    rarfile = None  # type: ignore[assignment]
    _RARFILE_AVAILABLE = False


def _candidate_rar_tools() -> list[Path]:
    candidates: list[Path] = []
    for name in ("UnRAR.exe", "unrar.exe", "WinRAR.exe", "winrar.exe", "7z.exe", "7za.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    common_dirs = [
        Path.cwd(),
        Path.cwd() / "bin",
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent / "bin",
        Path(__file__).resolve().parents[1] / "bin" if len(Path(__file__).resolve().parents) > 1 else Path(__file__).resolve().parent / "bin",
        Path(r"C:\Program Files\WinRAR"),
        Path(r"C:\Program Files (x86)\WinRAR"),
        Path(r"C:\Program Files\7-Zip"),
        Path(r"C:\Program Files (x86)\7-Zip"),
    ]
    for base in common_dirs:
        for name in ("UnRAR.exe", "unrar.exe", "WinRAR.exe", "winrar.exe", "7z.exe", "7za.exe"):
            candidate = base / name
            if candidate.exists():
                candidates.append(candidate)
    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item).lower()
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def _extract_rar_with_external_tool(archive_path: Path, dest_dir: Path) -> None:
    import subprocess
    # Run external extractors hidden on Windows so no CMD window opens.
    errors: list[str] = []
    for tool in _candidate_rar_tools():
        exe = tool.name.lower()
        if exe in {"winrar.exe", "winrar"}:
            cmd = [str(tool), "x", "-ibck", "-o+", str(archive_path), str(dest_dir) + "\\"]
        elif exe in {"7z.exe", "7za.exe", "7z", "7za"}:
            cmd = [str(tool), "x", "-y", f"-o{dest_dir}", str(archive_path)]
        else:
            cmd = [str(tool), "x", "-o+", str(archive_path), str(dest_dir) + "\\"]
        try:
            startupinfo = None
            creationflags = 0
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
                startupinfo.wShowWindow = 0
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags |= subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
                creationflags=creationflags,
                shell=False,
            )
            if result.returncode == 0:
                return
            errors.append(f"{tool}: exit {result.returncode} {result.stderr.strip() or result.stdout.strip()}")
        except Exception as exc:
            errors.append(f"{tool}: {exc}")
    raise RuntimeError(
        "RAR extraction failed. Install WinRAR/UnRAR/7-Zip or place UnRAR.exe next to the server exe. "
        + ("Attempts: " + " | ".join(errors) if errors else "No RAR tool found.")
    )


def _configure_rarfile_tool() -> None:
    if not _RARFILE_AVAILABLE:
        return
    for tool in _candidate_rar_tools():
        if tool.name.lower() in {"unrar.exe", "unrar", "rar.exe", "rar"}:
            try:
                rarfile.UNRAR_TOOL = str(tool)  # type: ignore[union-attr]
            except Exception:
                pass
            return


_configure_rarfile_tool()
_RAR_AVAILABLE = True

try:
    from win32api import GetFileVersionInfo, HIWORD, LOWORD
except Exception:
    GetFileVersionInfo = None
    HIWORD = LOWORD = None



def is_archive(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".zip", ".rar"}


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
        return

    if suffix == ".rar":
        if _RARFILE_AVAILABLE:
            try:
                with rarfile.RarFile(archive_path, "r") as rf:  # type: ignore[union-attr]
                    members = rf.infolist()
                    total = len(members)
                    for index, member in enumerate(members, start=1):
                        rf.extract(member, dest_dir)
                        if progress_callback:
                            progress_callback(index, total, member.filename)
                return
            except Exception:
                pass
        _extract_rar_with_external_tool(archive_path, dest_dir)
        if progress_callback:
            progress_callback(1, 1, archive_path.name)
        return

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
    _SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
    for item in src_path.rglob("*"):
        if item.name.lower() in _SKIP_NAMES:
            continue
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
