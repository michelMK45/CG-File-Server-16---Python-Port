@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  CGFS16 D3D Overlay DLL builder
echo ============================================================

REM ── Find Visual Studio via vswhere ──────────────────────────────────────────
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo ERROR: vswhere.exe not found.
    echo Install Visual Studio 2022 with the "Desktop development with C++" workload.
    exit /b 1
)

for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -property installationPath 2^>nul`) do set "VSINSTALL=%%i"
if not defined VSINSTALL (
    echo ERROR: No Visual Studio installation found.
    exit /b 1
)

set "VCVARS=%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat"
if not exist "%VCVARS%" (
    echo ERROR: vcvarsall.bat not found at:
    echo   %VCVARS%
    echo.
    echo Open "Visual Studio Installer", select VS 2022, click "Modify", and
    echo install the "Desktop development with C++" workload.
    exit /b 1
)

echo Using: %VSINSTALL%
REM FIFA 16 is a 64-bit process - DLL and injector must be x64
call "%VCVARS%" x64 > nul 2>&1
echo Compiler environment ready (x64).
echo.

REM ── Paths ───────────────────────────────────────────────────────────────────
set "SRCDIR=%~dp0"
set "OUTDIR=%~dp0..\..\runtime"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

REM ── Compile DLL (x86) ───────────────────────────────────────────────────────
set "SRC=%SRCDIR%cgfs16_overlay.cpp"
set "OUT=%OUTDIR%\cgfs16_overlay.dll"
set "PDB=%OUTDIR%\cgfs16_overlay.pdb"
echo Building %OUT% ...
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 ^
    "%SRC%" ^
    /Fe:"%OUT%" ^
    /Fd:"%PDB%" ^
    /link d3d9.lib user32.lib gdi32.lib

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED on DLL (exit code %ERRORLEVEL%)
    exit /b %ERRORLEVEL%
)
echo BUILD OK: %OUT%
echo.

REM ── Compile injector EXE (x86) ──────────────────────────────────────────────
set "SRC2=%SRCDIR%cgfs16_inject.cpp"
set "OUT2=%OUTDIR%\cgfs16_inject.exe"
set "PDB2=%OUTDIR%\cgfs16_inject.pdb"
echo Building %OUT2% ...
cl /nologo /O2 /W3 /EHsc /std:c++17 ^
    "%SRC2%" ^
    /Fe:"%OUT2%" ^
    /Fd:"%PDB2%" ^
    /link kernel32.lib

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED on injector EXE (exit code %ERRORLEVEL%)
    exit /b %ERRORLEVEL%
)
echo BUILD OK: %OUT2%
echo.
exit /b 0
