@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

REM ---------------------------------------------------------------
REM  Vendors + builds RmlUi and FreeType (static libs) into
REM  server16_py\d3d_overlay\thirdparty\, for the RmlUi overlay
REM  proof-of-concept (see the Phase 0 plan). Run once before
REM  building. Safe to re-run (no-op if already built). Must run
REM  from an environment where cl.exe/nmake are already on PATH
REM  (i.e. after "vcvarsall.bat x64") and where cmake.exe is on PATH.
REM ---------------------------------------------------------------

set "TP=server16_py\d3d_overlay\thirdparty"
set "RMLUI_TAG=6.2"
set "FREETYPE_TAG=VER-2-14-3"

if exist "%TP%\build\RmlUi\rmlui.lib" (
    echo [OK] RmlUi/FreeType already built under %TP%\build\
    exit /b 0
)

where cmake >nul 2>nul
if errorlevel 1 (
    echo [ERROR] cmake not found on PATH. Install it ^(e.g. "winget install Kitware.CMake"^)
    echo         and open a new terminal so PATH picks it up, then re-run.
    exit /b 1
)

echo [1/5] Fetching FreeType %FREETYPE_TAG% ...
if not exist "%TP%\freetype" (
    git clone --depth 1 --branch %FREETYPE_TAG% https://github.com/freetype/freetype.git "%TP%\freetype"
    if errorlevel 1 ( echo [ERROR] FreeType clone failed. & exit /b 1 )
)

echo [2/5] Building FreeType ^(static, static CRT^) ...
cmake -S "%TP%\freetype" -B "%TP%\build\freetype" -G "NMake Makefiles" ^
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF ^
    -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ^
    -DFT_DISABLE_ZLIB=ON -DFT_DISABLE_BZIP2=ON -DFT_DISABLE_PNG=ON ^
    -DFT_DISABLE_HARFBUZZ=ON -DFT_DISABLE_BROTLI=ON
if errorlevel 1 ( echo [ERROR] FreeType cmake configure failed. & exit /b 1 )
cmake --build "%TP%\build\freetype" --config Release
if errorlevel 1 ( echo [ERROR] FreeType build failed. & exit /b 1 )
cmake --install "%TP%\build\freetype" --prefix "%TP%\install\freetype"
if errorlevel 1 ( echo [ERROR] FreeType install step failed. & exit /b 1 )

echo [3/5] Fetching RmlUi %RMLUI_TAG% ...
if not exist "%TP%\RmlUi" (
    git clone --depth 1 --branch %RMLUI_TAG% https://github.com/mikke89/RmlUi.git "%TP%\RmlUi"
    if errorlevel 1 ( echo [ERROR] RmlUi clone failed. & exit /b 1 )
)

echo [4/5] Configuring RmlUi ^(static, static CRT, FreeType font engine^) ...
cmake -S "%TP%\RmlUi" -B "%TP%\build\RmlUi" -G "NMake Makefiles" ^
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DRMLUI_SAMPLES=OFF ^
    -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ^
    -DCMAKE_PREFIX_PATH="%CD%\%TP%\install\freetype"
if errorlevel 1 ( echo [ERROR] RmlUi cmake configure failed. & exit /b 1 )

echo [5/5] Building RmlUi ...
cmake --build "%TP%\build\RmlUi" --config Release
if errorlevel 1 ( echo [ERROR] RmlUi build failed. & exit /b 1 )

if not exist "%TP%\build\RmlUi\rmlui.lib" (
    echo [ERROR] Build finished but rmlui.lib was not produced where expected.
    exit /b 1
)

echo.
echo [OK] RmlUi + FreeType ready under %TP%\
exit /b 0
