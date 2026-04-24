@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "APP_NAME=Server16Python"
set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"

echo ============================================================
echo  CGFS16 - Full Build
echo ============================================================
echo.

:: ── Sanity checks ────────────────────────────────────────────────────────
if not exist "server16.ico" (
  echo [ERROR] Icon not found: server16.ico
  exit /b 1
)

:: ── Locate MSVC (requires Visual Studio 2019 or newer) ──────────────────
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo [ERROR] vswhere.exe not found. Install Visual Studio 2019 or newer.
  exit /b 1
)

for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -property installationPath`) do set "VS=%%i"
if "%VS%"=="" (
  echo [ERROR] No Visual Studio installation found.
  exit /b 1
)

set "VCVARS=%VS%\VC\Auxiliary\Build\vcvarsall.bat"
if not exist "%VCVARS%" (
  echo [ERROR] vcvarsall.bat not found at: %VCVARS%
  exit /b 1
)

echo [INFO] Visual Studio: %VS%
echo.

:: ── Compile D3D overlay DLL (x64) ────────────────────────────────────────
echo [1/3] Compiling cgfs16_overlay.dll ...
cmd /c "call "%VCVARS%" x64 && cl /nologo /O2 /W3 /LD /EHsc /std:c++17 server16_py\d3d_overlay\cgfs16_overlay.cpp /Fe:bin\cgfs16_overlay.dll /Fd:bin\cgfs16_overlay.pdb /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib"
if errorlevel 1 (
  echo [ERROR] cgfs16_overlay.dll compilation failed.
  exit /b 1
)
echo [OK] cgfs16_overlay.dll
echo.

:: ── Compile DLL injector EXE (x64) ──────────────────────────────────────
echo [2/3] Compiling cgfs16_inject.exe ...
cmd /c "call "%VCVARS%" x64 && cl /nologo /O2 /W3 /EHsc /std:c++17 server16_py\d3d_overlay\cgfs16_inject.cpp /Fe:bin\cgfs16_inject.exe /link kernel32.lib"
if errorlevel 1 (
  echo [ERROR] cgfs16_inject.exe compilation failed.
  exit /b 1
)
echo [OK] cgfs16_inject.exe
echo.

:: ── PyInstaller ──────────────────────────────────────────────────────────
echo [3/3] Running PyInstaller ...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --distpath "%DISTPATH%" ^
  --workpath "%WORKPATH%" ^
  "Server16Python.spec"
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  exit /b 1
)

echo.
echo ============================================================
echo  Build complete.
echo  EXE: %~dp0%DISTPATH%\%APP_NAME%.exe
echo ============================================================
pause