@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  CGFS16 KitExtractorHost builder
echo ============================================================

set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo ERROR: csc.exe not found at:
    echo   %CSC%
    echo A .NET Framework 4.x install is required to build this tool.
    exit /b 1
)

echo Using: %CSC%
echo.

set "SRCDIR=%~dp0"
set "BINDIR=%~dp0..\..\..\bin"
set "SRC=%SRCDIR%KitExtractorHost.cs"
set "OUT=%SRCDIR%KitExtractorHost.exe"
set "DLL=%BINDIR%\FifaLibrary16.dll"

if not exist "%DLL%" (
    echo ERROR: FifaLibrary16.dll not found at:
    echo   %DLL%
    exit /b 1
)

echo Building %OUT% ...
"%CSC%" /nologo /platform:x86 /target:exe /out:"%OUT%" /reference:"%DLL%" "%SRC%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED
    exit /b %ERRORLEVEL%
)
echo BUILD OK: %OUT%
echo.

echo Copying output to %BINDIR% ...
copy /Y "%OUT%" "%BINDIR%\KitExtractorHost.exe" > nul
echo.
echo NOTE: un_chunlzma.exe and fifa16_decryptor.exe must also be present in
echo %BINDIR% next to KitExtractorHost.exe - they are external decompressors
echo FifaLibrary16.dll shells out to. They ship with Creation Master 16 /
echo FIF Converter, not with this repo; copy them there manually if missing.
exit /b 0
