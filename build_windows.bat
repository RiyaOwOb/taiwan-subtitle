@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==============================================
echo Taiwan Subtitle v0.6.2 - Windows x64 Release
echo ==============================================
echo Project root: %ROOT%

where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul || (echo [ERROR] Python 3.13 is required.& exit /b 1)
  set "PY=python"
) else (
  set "PY=py -3.13"
)

if not exist "%ROOT%.venv-portable\Scripts\python.exe" (
  %PY% -m venv "%ROOT%.venv-portable" || (echo [ERROR] Could not create portable venv.& exit /b 1)
)
if not exist "%ROOT%.venv-installer\Scripts\python.exe" (
  %PY% -m venv "%ROOT%.venv-installer" || (echo [ERROR] Could not create installer venv.& exit /b 1)
)

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

if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
if exist "release" rmdir /s /q release
mkdir release
mkdir release\portable-stage

REM =====================
REM 1/4 CPU-only Portable
REM =====================
echo [1/4] Preparing CPU-only portable environment...
call "%ROOT%.venv-portable\Scripts\activate.bat"
python -m pip install --upgrade pip wheel packaging
python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cpu torch==2.11.0
python -m pip install --upgrade -r requirements.txt
python -m pip install --upgrade pyinstaller
python -c "import torch; print('Portable Torch:', torch.__version__); print('Portable CUDA:', torch.version.cuda); print('Portable CUDA available:', torch.cuda.is_available()); assert torch.version.cuda is None; assert not torch.cuda.is_available()"
python -c "import transformers; print('Transformers:', transformers.__version__)"
python -c "from transformers import AutoModelForMultimodalLM, AutoModelForTokenClassification; print('Qwen native Transformers classes: OK')"
python -m PyInstaller --noconfirm --clean TaiwanSubtitle-portable.spec
if errorlevel 1 (echo [ERROR] Portable PyInstaller build failed.& exit /b 1)
if not exist "dist\TaiwanSubtitle\TaiwanSubtitle.exe" (echo [ERROR] Portable EXE missing.& exit /b 1)
powershell -NoProfile -Command "Compress-Archive -Path 'dist\TaiwanSubtitle\*' -DestinationPath 'release\TaiwanSubtitle-windows-x64-v0.6.2-portable.zip' -Force"
if errorlevel 1 (echo [ERROR] Portable ZIP creation failed.& exit /b 1)
for %%F in ("release\TaiwanSubtitle-windows-x64-v0.6.2-portable.zip") do echo Portable size: %%~zF bytes
call deactivate

REM =====================
REM 2/4 Full CUDA Installer
REM =====================
echo [2/4] Preparing CUDA-enabled installer environment...
call "%ROOT%.venv-installer\Scripts\activate.bat"
python -m pip install --upgrade pip wheel packaging
python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0
python -m pip install --upgrade -r requirements.txt
python -m pip install --upgrade pyinstaller
python -c "import torch; print('Installer Torch:', torch.__version__); print('Installer CUDA runtime:', torch.version.cuda)"
python -c "import transformers; print('Transformers:', transformers.__version__)"
python -c "from transformers import AutoModelForMultimodalLM, AutoModelForTokenClassification; print('Qwen native Transformers classes: OK')"
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
python -m PyInstaller --noconfirm --clean TaiwanSubtitle-installer.spec
if errorlevel 1 (echo [ERROR] Installer PyInstaller build failed.& exit /b 1)
if not exist "dist\TaiwanSubtitle\TaiwanSubtitle.exe" (echo [ERROR] Installer EXE missing.& exit /b 1)
call deactivate

REM =====================
REM 3/4 Inno Setup
REM =====================
echo [3/4] Building installer...
set "ISCC_EXE="
where ISCC.exe >nul 2>nul && set "ISCC_EXE=ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE (echo [ERROR] Inno Setup 6 not found.& exit /b 1)
"%ISCC_EXE%" "%ROOT%installer\TaiwanSubtitle.iss"
if errorlevel 1 (echo [ERROR] Inno Setup build failed.& exit /b 1)
if not exist "release\TaiwanSubtitle-windows-x64-setup.exe" (echo [ERROR] Installer missing after build.& exit /b 1)

REM =====================
REM 4/4 Final checks
REM =====================
echo [4/4] Final release checks...
for %%F in ("release\TaiwanSubtitle-windows-x64-v0.6.2-portable.zip") do echo Portable ZIP: %%~zF bytes
for %%F in ("release\TaiwanSubtitle-windows-x64-setup.exe") do echo Installer EXE: %%~zF bytes
powershell -NoProfile -Command "$p='release\TaiwanSubtitle-windows-x64-v0.6.2-portable.zip'; if ((Get-Item $p).Length -ge 2147483648) { throw ('Portable ZIP is {0:N1} MiB and cannot be uploaded; reduce the bundle below 2048 MiB.' -f ((Get-Item $p).Length / 1MB)) }"
if errorlevel 1 exit /b 1

echo.
echo BUILD COMPLETE
echo Portable: %ROOT%release\TaiwanSubtitle-windows-x64-v0.6.2-portable.zip
echo Installer: %ROOT%release\TaiwanSubtitle-windows-x64-setup.exe
endlocal
