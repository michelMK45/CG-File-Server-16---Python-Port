# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

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

exe = EXE(
    pyz,
    a.scripts,
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
