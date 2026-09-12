# v0.5.5

- Fix Windows FFmpeg sidecar verification by using an absolute project root.
- Pass the project root explicitly from `build_windows.bat` to `download_ffmpeg.ps1`.
- Verify the copied FFmpeg executable before continuing the build.
