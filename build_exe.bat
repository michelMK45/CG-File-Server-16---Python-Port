@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_NAME=Server16Python"
set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"
set "OVERLAY_DLL=bin\cgfs16_overlay.dll"
set "INJECTOR_EXE=bin\cgfs16_inject.exe"
set "FIFA_LIBRARY=bin\FifaLibrary16.dll"
set "KIT_EXTRACTOR_EXE=bin\KitExtractorHost.exe"
set "UN_CHUNLZMA_EXE=bin\un_chunlzma.exe"
set "FIFA16_DECRYPTOR_EXE=bin\fifa16_decryptor.exe"
set "DB_TEMPLATE=bin\Templates\data\db\fifa_ng_db.db"
set "DB_TEMPLATE_XML=bin\Templates\data\db\fifa_ng_db-meta.xml"
set "ZLIB_NET_DLL=bin\zlib.net.dll"

echo ============================================================
echo  CGFS16 - Full Build
echo ============================================================
echo.

REM Sanity checks
if not exist "server16.ico" (
  call :fail "Icon not found: server16.ico"
  exit /b 1
)

if not exist "bin" mkdir "bin"

call :build_cpp_helpers
if errorlevel 1 exit /b 1

call :build_kit_extractor
if errorlevel 1 exit /b 1

call :require_file "%OVERLAY_DLL%" "Overlay DLL"
if errorlevel 1 exit /b 1
call :require_file "%INJECTOR_EXE%" "Overlay injector"
if errorlevel 1 exit /b 1
call :require_file "%FIFA_LIBRARY%" "FIFA database library"
if errorlevel 1 exit /b 1
call :require_file "%KIT_EXTRACTOR_EXE%" "KitExtractorHost.exe (Extract Kits)"
if errorlevel 1 exit /b 1
call :require_file "%UN_CHUNLZMA_EXE%" "un_chunlzma.exe (kit decompressor, ships with Creation Master 16)"
if errorlevel 1 exit /b 1
call :require_file "%FIFA16_DECRYPTOR_EXE%" "fifa16_decryptor.exe (db decompressor, ships with FIF Converter)"
if errorlevel 1 exit /b 1
call :require_file "%DB_TEMPLATE%" "fifa_ng_db.db template (Extract Kits bootstraps a fresh install's database from this, ships with Creation Master 16's Templates folder)"
if errorlevel 1 exit /b 1
call :require_file "%DB_TEMPLATE_XML%" "fifa_ng_db-meta.xml template (same source as fifa_ng_db.db template)"
if errorlevel 1 exit /b 1
call :require_file "%ZLIB_NET_DLL%" "zlib.net.dll (Extract Kit UI decompressor, ships with Creation Master 16)"
if errorlevel 1 exit /b 1

echo [3/4] Setting up 32-bit Python for BH regeneration...
call "scripts\setup_python32.bat"
if errorlevel 1 exit /b 1

echo [4/4] Running PyInstaller ...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --distpath "%DISTPATH%" ^
  --workpath "%WORKPATH%" ^
  "Server16Python.spec"
if errorlevel 1 (
  call :fail "PyInstaller build failed."
  exit /b 1
)

echo.
echo ============================================================
echo  Build complete.
echo  EXE: %~dp0%DISTPATH%\%APP_NAME%.exe
echo ============================================================
call :pause_if_needed
exit /b 0

:build_cpp_helpers
if /i "%SKIP_CPP_BUILD%"=="1" goto skip_cpp_build

REM Locate MSVC. If it is not installed, use the checked-in helper binaries.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" goto find_visual_studio
call :use_prebuilt_helpers "vswhere.exe not found. Visual Studio C++ tools are not installed."
exit /b !ERRORLEVEL!

:find_visual_studio
set "VS="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -property installationPath 2^>nul`) do set "VS=%%i"
if defined VS goto check_vcvars
call :use_prebuilt_helpers "No Visual Studio installation found."
exit /b !ERRORLEVEL!

:check_vcvars
set "VCVARS=%VS%\VC\Auxiliary\Build\vcvarsall.bat"
if exist "%VCVARS%" goto compile_cpp_helpers
call :use_prebuilt_helpers "vcvarsall.bat not found at: %VCVARS%"
exit /b !ERRORLEVEL!

:compile_cpp_helpers
echo [INFO] Visual Studio: %VS%
call "%VCVARS%" x64 >nul
if errorlevel 1 (
  call :fail "Failed to initialize the MSVC x64 build environment."
  exit /b 1
)
echo.

if not "%SKIP_RMLUI_THIRDPARTY_BUILD%"=="1" call "scripts\setup_rmlui_thirdparty.bat"
if errorlevel 1 (
  call :fail "RmlUi/FreeType thirdparty build failed (set SKIP_RMLUI_THIRDPARTY_BUILD=1 to skip)."
  exit /b 1
)
echo.

echo [1/3] Compiling cgfs16_overlay.dll ...
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 ^
  "server16_py\d3d_overlay\cgfs16_overlay.cpp" ^
  "server16_py\d3d_overlay\cgfs16_rmlui.cpp" ^
  "server16_py\d3d_overlay\cgfs16_rmlui_menu.cpp" ^
  /I "server16_py\d3d_overlay\thirdparty\RmlUi\Include" ^
  /Fe:"%OVERLAY_DLL%" ^
  /Fd:"bin\cgfs16_overlay.pdb" ^
  /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib ^
  /LIBPATH:"server16_py\d3d_overlay\thirdparty\build\RmlUi" rmlui.lib ^
  /LIBPATH:"server16_py\d3d_overlay\thirdparty\install\freetype\lib" freetype.lib
if errorlevel 1 (
  call :fail "cgfs16_overlay.dll compilation failed."
  exit /b 1
)
echo [OK] cgfs16_overlay.dll
echo.

echo [2/3] Compiling cgfs16_inject.exe ...
cl /nologo /O2 /W3 /EHsc /std:c++17 ^
  "server16_py\d3d_overlay\cgfs16_inject.cpp" ^
  /Fe:"%INJECTOR_EXE%" ^
  /link kernel32.lib
if errorlevel 1 (
  call :fail "cgfs16_inject.exe compilation failed."
  exit /b 1
)
echo [OK] cgfs16_inject.exe
echo.
exit /b 0

:skip_cpp_build
echo [1/3] Skipping C++ helper build (SKIP_CPP_BUILD=1).
echo [2/3] Skipping C++ helper build (SKIP_CPP_BUILD=1).
echo.
exit /b 0

:use_prebuilt_helpers
echo [WARN] %~1
if exist "%OVERLAY_DLL%" if exist "%INJECTOR_EXE%" (
  echo [1/3] Using existing %OVERLAY_DLL%.
  echo [2/3] Using existing %INJECTOR_EXE%.
  echo.
  exit /b 0
)

call :fail "MSVC is unavailable and the prebuilt C++ helpers are missing from bin."
exit /b 1

:build_kit_extractor
if /i "%SKIP_KIT_EXTRACTOR_BUILD%"=="1" (
  echo [INFO] Skipping KitExtractorHost.exe build ^(SKIP_KIT_EXTRACTOR_BUILD=1^), using existing bin\KitExtractorHost.exe.
  echo.
  exit /b 0
)

REM KitExtractorHost.exe is a small .NET Framework x86 console app compiled
REM with csc.exe (ships with Windows) — see server16_py\native_tools\kit_extractor
REM for why it must run as a real compiled .exe rather than hosted via pythonnet.
set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if exist "%CSC%" goto compile_kit_extractor
echo [WARN] csc.exe not found at %CSC% - using existing %KIT_EXTRACTOR_EXE% if present.
if exist "%KIT_EXTRACTOR_EXE%" (
  echo [OK] Using existing %KIT_EXTRACTOR_EXE%.
  echo.
  exit /b 0
)
echo [WARN] %KIT_EXTRACTOR_EXE% is also missing - the "Extract Kits" feature will be unavailable in this build.
echo.
exit /b 0

:compile_kit_extractor
echo Compiling KitExtractorHost.exe ...
call "server16_py\native_tools\kit_extractor\build.bat"
if errorlevel 1 (
  call :fail "KitExtractorHost.exe compilation failed."
  exit /b 1
)
echo.
exit /b 0

:require_file
if exist "%~1" exit /b 0
call :fail "%~2 not found: %~1"
exit /b 1

:fail
echo.
echo [ERROR] %~1
echo.
call :pause_if_needed
exit /b 1

:pause_if_needed
if /i not "%BUILD_NO_PAUSE%"=="1" pause
exit /b 0
