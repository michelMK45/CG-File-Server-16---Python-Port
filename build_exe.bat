@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_NAME=Server16Python"
set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"
set "OVERLAY_DLL=bin\cgfs16_overlay.dll"
set "INJECTOR_EXE=bin\cgfs16_inject.exe"
set "FIFA_LIBRARY=bin\FifaLibrary14.dll"

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

call :require_file "%OVERLAY_DLL%" "Overlay DLL"
if errorlevel 1 exit /b 1
call :require_file "%INJECTOR_EXE%" "Overlay injector"
if errorlevel 1 exit /b 1
call :require_file "%FIFA_LIBRARY%" "FIFA database library"
if errorlevel 1 exit /b 1

echo [3/3] Running PyInstaller ...
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

echo [1/3] Compiling cgfs16_overlay.dll ...
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 ^
  "server16_py\d3d_overlay\cgfs16_overlay.cpp" ^
  /Fe:"%OVERLAY_DLL%" ^
  /Fd:"bin\cgfs16_overlay.pdb" ^
  /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib
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
