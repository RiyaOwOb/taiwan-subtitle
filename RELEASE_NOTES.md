# v0.5.2

- Fix PyInstaller spec path resolution on GitHub Actions/Windows by using the build working directory instead of `__file__`.
- Update GitHub Actions to Node 24-compatible action versions.

## v0.5.0 — Video Editor Workspace

- Added waveform timeline rendering.
- Added draggable/resizable subtitle clips on the timeline.
- Added live typography/style controls and preview.
- Added FFmpeg ASS-based hard-subtitle (burn-in) MP4 export.
- Updated Windows installer version to 0.5.0.

# Taiwan Subtitle 0.3.0 — Windows-first release

## User-facing changes

- Native Windows x64 desktop GUI.
- Drag-and-drop media import.
- Multi-file batch transcription.
- Auto / CUDA / CPU device selection.
- TEA-ASR-1.1 and TEA-ASR-1.1-mini model choices.
- Qwen3 Forced Aligner timestamps.
- Bundled FFmpeg sidecar for media normalization.
- SRT / TXT / JSON output.
- Per-user model cache under `%LOCALAPPDATA%\\TaiwanSubtitle`.
- Per-user logs under `%LOCALAPPDATA%\\TaiwanSubtitle\\logs`.
- PyInstaller portable build and Inno Setup installer.
- GitHub Actions workflow for Windows x64 release builds.

## Not included yet

- DaVinci Resolve direct timeline integration.
- Premiere Pro / After Effects integration.
- Speaker diarization UI.
- In-app subtitle editor.

## v0.4.0 — Subtitle Editor & Video Preview

- In-app SRT/JSON subtitle editor
- Video frame preview and muted playback
- Timeline seek bar with cue blocks
- Edit cue text/start/end
- Add, delete, merge, split cues
- Set cue boundaries from current preview time
- Undo/redo
- Automatically open the editor when transcription finishes
- Open existing video + SRT directly from the editor
