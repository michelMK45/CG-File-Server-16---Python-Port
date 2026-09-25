# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path

from PyInstaller.building.splash import Splash

# bin/ViGEmBus/*.{exe,msi} (an ADDITIONAL/override ViGEmBus driver installer
# for the Gamepads tab, see gamepad_bridge_runtime.py's find_vigembus_installer())
# is optional and not built by this repo -- only bundle it if a contributor has
# actually placed one there. It is NOT the only source: vgamepad's own package
# already vendors ViGEmBusSetup_x64.msi/_x86.msi (see _vgamepad_datas below),
# which find_vigembus_installer() falls back to automatically, so most builds
# need nothing placed here at all -- this only matters for shipping a newer/
# different installer than whatever vgamepad happens to bundle.
_vigembus_dir = Path("bin") / "ViGEmBus"
_extra_datas = [(str(_vigembus_dir), "bin\\ViGEmBus")] if _vigembus_dir.is_dir() else []

# bin/HidHide/*.{exe,msi} (hidhide_runtime.py's find_hidhide_installer()) --
# unlike ViGEmBus, no Python package vendors a copy of this installer, so
# this is the ONLY source and is genuinely optional: HidHide hides a slot's
# physical controller from fifa16.exe to avoid double input, but the core
# gamepad bridge already works without it. A contributor downloads the
# current installer (an .exe, e.g. HidHide_<version>_x64.exe -- confirmed
# live; an earlier assumption here that it was an .msi was wrong) from
# https://github.com/nefarius/HidHide/releases and places it here.
_hidhide_dir = Path("bin") / "HidHide"
_extra_datas += [(str(_hidhide_dir), "bin\\HidHide")] if _hidhide_dir.is_dir() else []

# vgamepad loads a native ViGEmClient.dll (vendored inside its own package,
# per-architecture) via a plain ctypes.CDLL() at import time, at a path it
# computes relative to its own __file__ -- PyInstaller's static analysis
# bundles the *.py files that reference it just fine, but never bundles that
# DLL (or, as a side effect of grabbing the whole package's data, the
# ViGEmBusSetup_x64.msi/_x86.msi installers vgamepad also vendors) unless
# told to explicitly. Confirmed live 2026-09: omitting this produces exactly
# "Could not find module '...\\vgamepad\\win\\vigem\\client\\x64\\ViGEmClient.dll'"
# at startup of the built EXE. Wrapped in try/except so a build environment
# without vgamepad installed still builds (the app already degrades
# gracefully at runtime when vgamepad is missing, same as pypresence/
# ffpyplayer) instead of hard-failing the whole build over an optional dep.
try:
    from PyInstaller.utils.hooks import collect_data_files

    _vgamepad_datas = collect_data_files('vgamepad')
except Exception:
    _vgamepad_datas = []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        ('bin\\cgfs16_overlay.dll',   'bin'),
        ('bin\\cgfs16_inject.exe',    'bin'),
        ('bin\\FifaLibrary16.dll',    'bin'),
        ('bin\\KitExtractorHost.exe', 'bin'),
        ('bin\\un_chunlzma.exe',      'bin'),
        ('bin\\fifa16_decryptor.exe', 'bin'),
        ('bin\\zlib.net.dll',        'bin'),
    ],
    datas=[
        ('server16_py\\offsets.json', 'server16_py'),
        ('server16_py\\bh_worker.py', 'server16_py'),
        ('server16_py\\db_worker.py', 'server16_py'),
        ('server16_py\\kit_worker.py', 'server16_py'),
        ('server16_py\\kit_preview_worker.py', 'server16_py'),
        ('server16_py\\dds_image_worker.py', 'server16_py'),
        ('server16_py\\locales', 'server16_py\\locales'),
        ('bin\\python32', 'bin\\python32'),
        ('bin\\Templates', 'bin\\Templates'),
        ('server16.ico', '.'),
        ('install_data', 'install_data'),
        ('resources', 'resources'),
    ] + _extra_datas + _vgamepad_datas,
    hiddenimports=['clr', 'rarfile', 'pygame', 'vgamepad'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# A onefile exe unpacks itself before any Python runs, and server16_py/splash.py
# (the live, animated splash) can only appear once Python is up -- so on this
# ~200MB exe the first seconds would show nothing. PyInstaller's bootloader can
# show a static image during that stretch; scripts/make_boot_splash.py draws it
# with the live splash's own geometry (so the handoff looks like the spinner
# starting to turn), and main.py closes it once the live splash is on screen.
# Never fatal: if the image can't be rendered the build just has no boot splash.
def _boot_splash_image():
    try:
        script = Path(SPECPATH) / "scripts" / "make_boot_splash.py"
        module_spec = importlib.util.spec_from_file_location("make_boot_splash", script)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return str(module.render(Path(SPECPATH) / "build" / "boot_splash.png"))
    except Exception as exc:
        print(f"WARNING: boot splash image not generated ({exc}); building without it")
        return None


def _boot_splash_target():
    image = _boot_splash_image()
    if image is None:
        return None
    try:
        return Splash(image, binaries=a.binaries, datas=a.datas)
    except (Exception, SystemExit) as exc:  # Splash exits the build if Tcl/Tk is unusable
        print(f"WARNING: PyInstaller boot splash unavailable ({exc}); building without it")
        return None


splash = _boot_splash_target()
_splash_targets = [splash, splash.binaries] if splash is not None else []

exe = EXE(
    pyz,
    a.scripts,
    *_splash_targets,
    a.binaries,
    a.datas,
    [],
    name='Server16Python',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['server16.ico'],
)
