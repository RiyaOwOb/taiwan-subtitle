@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo This folder is not installed. Run install_dev_windows.bat.
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python taiwan_subtitle.py %*
endlocal
