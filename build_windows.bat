@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==============================================
echo Taiwan Subtitle - Windows x64 Release Builder
echo ==============================================
echo Project root: %ROOT%

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul || (echo [ERROR] Python 3.12/3.13 is required.& exit /b 1)
  set "PY=py -3.13"
) else (
  set "PY=python"
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  %PY% -m venv "%ROOT%.venv"
  if errorlevel 1 %PY% -m venv "%ROOT%.venv"
)
if not exist "%ROOT%.venv\Scripts\python.exe" (echo [ERROR] Could not create venv.& exit /b 1)
call "%ROOT%.venv\Scripts\activate.bat"
python -m pip install --upgrade pip wheel

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%download_ffmpeg.ps1" -Root "%ROOT%"
if errorlevel 1 (echo [ERROR] FFmpeg download step failed.& exit /b 1)

set "FFMPEG=%ROOT%runtime\ffmpeg\ffmpeg.exe"
if not exist "%FFMPEG%" (
  echo [ERROR] FFmpeg sidecar is missing: %FFMPEG%
  echo [DEBUG] Contents of runtime:
  if exist "%ROOT%runtime" dir /s /b "%ROOT%runtime"
  exit /b 1
)
"%FFMPEG%" -version | findstr /B /C:"ffmpeg version" >nul
if errorlevel 1 (echo [ERROR] FFmpeg exists but could not be executed.& exit /b 1)
echo FFmpeg sidecar verified: %FFMPEG%

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
if not defined ISCC_EXE (echo [ERROR] Inno Setup 6 not found.& exit /b 1)
"%ISCC_EXE%" "%ROOT%installer\TaiwanSubtitle.iss"
if errorlevel 1 (echo [ERROR] Inno Setup build failed.& exit /b 1)
if not exist "release\TaiwanSubtitle-windows-x64-setup.exe" (echo [ERROR] Installer missing after build.& exit /b 1)

echo [3/3] Installer created.
echo.
echo ==============================================
echo BUILD COMPLETE
echo ==============================================
echo Portable ZIP: %ROOT%release\TaiwanSubtitle-windows-x64-portable.zip
echo Installer:    %ROOT%release\TaiwanSubtitle-windows-x64-setup.exe
endlocal
