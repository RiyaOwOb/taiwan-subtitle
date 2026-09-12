@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==============================================
echo Taiwan Subtitle v0.6 - Windows x64 Release
echo ==============================================
echo Project root: %ROOT%

where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul || (echo [ERROR] Python 3.13 is required.& exit /b 1)
  set "PY=python"
) else (
  set "PY=py -3.13"
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  %PY% -m venv "%ROOT%.venv"
  if errorlevel 1 (echo [ERROR] Could not create venv.& exit /b 1)
)
if not exist "%ROOT%.venv\Scripts\python.exe" (echo [ERROR] Python venv missing.& exit /b 1)
call "%ROOT%.venv\Scripts\activate.bat"
python -m pip install --upgrade pip wheel packaging

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%download_ffmpeg.ps1"
if errorlevel 1 (echo [ERROR] FFmpeg download step failed.& exit /b 1)
set "FFMPEG=%ROOT%runtime\ffmpeg\ffmpeg.exe"
if not exist "%FFMPEG%" (
  echo [ERROR] FFmpeg sidecar missing: %FFMPEG%
  if exist "%ROOT%runtime" dir /s /b "%ROOT%runtime"
  exit /b 1
)
"%FFMPEG%" -version | findstr /B /C:"ffmpeg version" >nul
if errorlevel 1 (echo [ERROR] FFmpeg exists but could not execute.& exit /b 1)
echo FFmpeg sidecar verified: %FFMPEG%

REM Build against the official CUDA 12.8 Windows wheel so NVIDIA users can use CUDA.
python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0
python -m pip install --upgrade -r requirements.txt
python -m pip install --upgrade pyinstaller

python -c "import torch; print('Torch:', torch.__version__); print('CUDA runtime:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available())"
python -c "import transformers; print('Transformers:', transformers.__version__)"
python -c "from transformers import AutoModelForMultimodalLM, AutoModelForTokenClassification; print('Qwen native Transformers classes: OK')"

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
if not exist release mkdir release

echo [1/3] Building portable application...
python -m PyInstaller --noconfirm --clean TaiwanSubtitle.spec
if errorlevel 1 (echo [ERROR] PyInstaller build failed.& exit /b 1)
if not exist "dist\TaiwanSubtitle\TaiwanSubtitle.exe" (echo [ERROR] EXE missing after build.& exit /b 1)

powershell -NoProfile -Command "Compress-Archive -Path 'dist\TaiwanSubtitle\*' -DestinationPath 'release\TaiwanSubtitle-windows-x64-v0.6.0-portable.zip' -Force"
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
echo BUILD COMPLETE
echo Portable: %ROOT%release\TaiwanSubtitle-windows-x64-v0.6.0-portable.zip
echo Installer: %ROOT%release\TaiwanSubtitle-windows-x64-setup.exe
endlocal
