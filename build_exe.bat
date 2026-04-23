@echo off
setlocal
cd /d "%~dp0"

set "APP_NAME=Server16Python"
set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"

if not exist "server16.ico" (
  echo.
  echo Arquivo de icone nao encontrado: %~dp0server16.ico
  exit /b 1
)

pyinstaller ^
  --noconfirm ^
  --clean ^
  --distpath "%DISTPATH%" ^
  --workpath "%WORKPATH%" ^
  "Server16Python.spec"

echo.
echo Build finalizado.
echo EXE: %~dp0%DISTPATH%\%APP_NAME%.exe
pause