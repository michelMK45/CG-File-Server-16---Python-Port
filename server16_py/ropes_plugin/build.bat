@echo off
setlocal EnableDelayedExpansion
REM Builds bin\SERVER16_Ropes.asi (FIFA Plugin Loader plugin, x64). build_exe.bat calls this too,
REM from an environment where vcvarsall x64 already ran; standalone it sets the environment up.

where cl >nul 2>&1
if not errorlevel 1 goto compile

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo ERROR: vswhere.exe not found. Install Visual Studio with "Desktop development with C++".
  exit /b 1
)
set "VSINSTALL="
for /f "usebackq delims=" %%i in (`call "%VSWHERE%" -latest -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL (
  echo ERROR: No Visual Studio installation found.
  exit /b 1
)
call "%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 (
  echo ERROR: vcvarsall.bat x64 failed.
  exit /b 1
)

:compile
set "SRCDIR=%~dp0"
set "BINDIR=%~dp0..\..\bin"
set "OBJDIR=%~dp0..\..\build\ropes_plugin"
if not exist "%BINDIR%" mkdir "%BINDIR%"
if not exist "%OBJDIR%" mkdir "%OBJDIR%"

REM MinHook 1.3.3 (BSD-2, thirdparty\minhook): x64 sources only.
set "MH=%SRCDIR%thirdparty\minhook\src"
cl /nologo /c /O2 /W3 /MT ^
  "%MH%\hook.c" "%MH%\buffer.c" "%MH%\trampoline.c" "%MH%\hde\hde64.c" ^
  /Fo:"%OBJDIR%\\" /Fd:"%OBJDIR%\minhook.pdb"
if errorlevel 1 (
  echo BUILD FAILED: MinHook
  exit /b 1
)

cl /nologo /O2 /W4 /EHsc /std:c++17 /MT /LD ^
  "%SRCDIR%SERVER16_Ropes.cpp" ^
  "%OBJDIR%\hook.obj" "%OBJDIR%\buffer.obj" "%OBJDIR%\trampoline.obj" "%OBJDIR%\hde64.obj" ^
  /Fo:"%OBJDIR%\\" /Fd:"%OBJDIR%\SERVER16_Ropes.pdb" ^
  /link /DLL /OUT:"%BINDIR%\SERVER16_Ropes.asi" /IMPLIB:"%OBJDIR%\SERVER16_Ropes.lib" kernel32.lib
if errorlevel 1 (
  echo BUILD FAILED: SERVER16_Ropes.asi
  exit /b 1
)
echo BUILD OK: %BINDIR%\SERVER16_Ropes.asi
exit /b 0
