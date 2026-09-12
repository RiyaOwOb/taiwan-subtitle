@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul || (echo [ERROR] Python 3.13 is required.& exit /b 1)
  set "PY=python"
) else (
  set "PY=py -3.13"
)

if not exist "%ROOT%.venv\Scripts\python.exe" (
  %PY% -m venv "%ROOT%.venv"
  if errorlevel 1 exit /b 1
)
call "%ROOT%.venv\Scripts\activate.bat"
python -m pip install --upgrade pip wheel packaging
python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0
python -m pip install --upgrade -r requirements.txt
python -c "import torch; print('Torch:', torch.__version__); print('CUDA runtime:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available())"
python -c "from transformers import AutoModelForMultimodalLM, AutoModelForTokenClassification; print('Native Qwen Transformers classes: OK')"
echo.
echo Development environment ready.
endlocal
