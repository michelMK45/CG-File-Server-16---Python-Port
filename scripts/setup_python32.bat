@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

REM ---------------------------------------------------------------
REM  Sets up a 32-bit Python embeddable in bin\python32\ so that
REM  bh_worker.py can load the x86-only FifaLibrary16.dll.
REM  Run once before building. Safe to re-run (no-op if ready).
REM ---------------------------------------------------------------

set "PYTHON32_DIR=bin\python32"
set "PYTHON_VER=3.9.13"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-embed-win32.zip"
set "PIP_URL=https://bootstrap.pypa.io/pip/3.9/get-pip.py"
set "PYTHONNET_VER=3.0.5"

if exist "%PYTHON32_DIR%\python.exe" (
    echo [OK] 32-bit Python already at %PYTHON32_DIR%
    exit /b 0
)

echo [1/4] Downloading Python %PYTHON_VER% x86 embeddable...
if not exist "%PYTHON32_DIR%" mkdir "%PYTHON32_DIR%"

powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON32_DIR%\embed.zip' -UseBasicParsing"
if errorlevel 1 (
    echo [ERROR] Download failed: %PYTHON_URL%
    goto :cleanup_fail
)

echo [2/4] Extracting...
powershell -NoProfile -Command "Expand-Archive -Path '%PYTHON32_DIR%\embed.zip' -DestinationPath '%PYTHON32_DIR%' -Force"
if errorlevel 1 (
    echo [ERROR] Extraction failed.
    goto :cleanup_fail
)
del "%PYTHON32_DIR%\embed.zip" 2>nul

REM Enable site-packages ? embeddable disables it by default via _pth file.
powershell -NoProfile -Command "$f = Get-Item '%PYTHON32_DIR%\python*._pth'; $c = (Get-Content $f.FullName) -replace '#import site','import site'; Set-Content $f.FullName $c"
if errorlevel 1 (
    echo [ERROR] Failed to enable site-packages in _pth file.
    goto :cleanup_fail
)

echo [3/4] Installing pip...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PIP_URL%' -OutFile '%PYTHON32_DIR%\get-pip.py' -UseBasicParsing"
if errorlevel 1 (
    echo [ERROR] Download failed: %PIP_URL%
    goto :cleanup_fail
)
"%PYTHON32_DIR%\python.exe" "%PYTHON32_DIR%\get-pip.py" --quiet
if errorlevel 1 (
    echo [ERROR] pip installation failed.
    goto :cleanup_fail
)
del "%PYTHON32_DIR%\get-pip.py" 2>nul

echo [4/4] Installing pythonnet %PYTHONNET_VER%...
"%PYTHON32_DIR%\python.exe" -m pip install "pythonnet==%PYTHONNET_VER%" --quiet
if errorlevel 1 (
    echo [ERROR] pythonnet installation failed.
    goto :cleanup_fail
)

echo.
echo [OK] 32-bit Python ready at %PYTHON32_DIR%
exit /b 0

:cleanup_fail
echo [INFO] Removing incomplete installation at %PYTHON32_DIR%...
if exist "%PYTHON32_DIR%" rmdir /s /q "%PYTHON32_DIR%"
echo [ERROR] Setup failed. Fix the error above and re-run.
exit /b 1
