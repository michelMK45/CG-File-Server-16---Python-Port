@echo off
setlocal
cd /d "%~dp0"

set "APP_NAME=Server16Python"
set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"

pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --icon "assets\server16.ico" ^
  --name "%APP_NAME%" ^
  --distpath "%DISTPATH%" ^
  --workpath "%WORKPATH%" ^
  --hidden-import "clr" ^
  --add-data "server16_py\offsets.json;server16_py" ^
  --add-data "bin\FifaLibrary14.dll;bin" ^
  main.py

echo.
echo Build finalizado.
echo EXE: %~dp0%DISTPATH%\%APP_NAME%.exe
pause
