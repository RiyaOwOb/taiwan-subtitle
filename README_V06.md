# Taiwan Subtitle v0.6 — Windows native Transformers

## What changed

v0.6 removes the Windows ASR dependency on the `qwen-asr` wrapper and calls the Qwen3 ASR and Forced Aligner models directly through Hugging Face Transformers.

Pipeline:

1. Bundled FFmpeg converts media to 16 kHz mono WAV.
2. TEA-ASR-1.1 / TEA-ASR-1.1-mini is loaded with `AutoProcessor` + `AutoModelForMultimodalLM`.
3. Audio is processed in 30-second chunks to keep Windows memory use predictable.
4. `Qwen/Qwen3-ForcedAligner-0.6B-hf` is loaded with `AutoProcessor` + `AutoModelForTokenClassification`.
5. The aligner creates word-level timestamps which are grouped into SRT cues.
6. Models are cached below `%LOCALAPPDATA%\\TaiwanSubtitle\\models\\huggingface`.

This deliberately avoids MLX and avoids importing `qwen_asr` in the application runtime, addressing the previous Windows `No module named 'prepro'` failure path.

## Important

The application does not bundle the model weights into the EXE. They are downloaded on first use and cached locally.

The release builder installs the official Windows PyTorch CUDA 12.8 wheel (`torch==2.11.0`) so the same portable build can use CUDA on systems with a compatible NVIDIA driver, while still falling back to CPU when CUDA is unavailable.

## Files to replace

- `taiwan_subtitle.py`
- `requirements.txt`
- `TaiwanSubtitle.spec`
- `build_windows.bat`
- `.github/workflows/windows-release.yml`
- `installer/TaiwanSubtitle.iss`
- `app.py` (version label only)
- `install_dev_windows.bat`

Do not copy `.venv`, `build`, `dist`, or model caches into Git.
