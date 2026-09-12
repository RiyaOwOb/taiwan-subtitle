@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================
echo Taiwan Subtitle - Windows x64 Release Builder
echo ==============================================

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul || (echo [ERROR] Python 3.12/3.13 is required.& exit /b 1)
  set "PY=py -3.13"
) else (
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 %PY% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (echo [ERROR] Could not create venv.& exit /b 1)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip wheel

powershell -NoProfile -ExecutionPolicy Bypass -File ".\download_ffmpeg.ps1"
if not exist "runtime\ffmpeg\ffmpeg.exe" (echo [ERROR] FFmpeg sidecar is missing.& exit /b 1)

REM Install the official Windows wheel chosen by the current pip resolver.
python -m pip install --upgrade torch
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
if not exist release mkdir release

echo [1/3] Building portable application...
python -m PyInstaller --noconfirm --clean TaiwanSubtitle.spec
if errorlevel 1 (echo [ERROR] PyInstaller build failed.& exit /b 1)

if not exist "dist\TaiwanSubtitle\TaiwanSubtitle.exe" (echo [ERROR] EXE missing after build.& exit /b 1)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\TaiwanSubtitle\*' -DestinationPath 'release\TaiwanSubtitle-windows-x64-portable.zip' -Force"
if errorlevel 1 (echo [ERROR] Portable ZIP creation failed.& exit /b 1)

echo [2/3] Portable ZIP created.

set "ISCC_EXE="
where ISCC.exe >nul 2>nul && set "ISCC_EXE=ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (
  echo [ERROR] Inno Setup 6 not found. Install it, then run this script again.
  exit /b 1
)

"%ISCC_EXE%" installer\TaiwanSubtitle.iss
if errorlevel 1 (echo [ERROR] Inno Setup build failed.& exit /b 1)
if not exist "release\TaiwanSubtitle-windows-x64-setup.exe" (echo [ERROR] Installer missing after build.& exit /b 1)

echo [3/3] Installer created.
echo.
echo ==============================================
echo BUILD COMPLETE
echo ==============================================
echo Portable ZIP: %CD%\release\TaiwanSubtitle-windows-x64-portable.zip
echo Installer:    %CD%\release\TaiwanSubtitle-windows-x64-setup.exe
endlocal
