# Windows Distribution

`v0.5.1` distribution targets:

- `TaiwanSubtitle-windows-x64-portable.zip`: unzip and run `TaiwanSubtitle.exe`; no Python installation is required on the target machine.
- `TaiwanSubtitle-windows-x64-setup.exe`: per-user installer; no administrator account is required.

The application binary and Python runtime are packaged by PyInstaller. FFmpeg is shipped as an application sidecar. Large AI model weights are downloaded on first use and cached under `%LOCALAPPDATA%\\TaiwanSubtitle` so the installer stays practical in size.
