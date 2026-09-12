@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul || (echo [ERROR] Please install Python 3.12 or 3.13. & exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip wheel
python -m pip install --upgrade torch
python -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File ".\download_ffmpeg.ps1"
if not exist "models" mkdir models
if not exist "output" mkdir output
echo.
echo Development environment ready. Run run_windows.bat
endlocal
