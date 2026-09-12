# PyInstaller spec. Run build_windows.bat on Windows after the runtime/ffmpeg
# sidecar has been downloaded.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path.cwd().resolve()

qwen_datas, qwen_binaries, qwen_hidden = collect_all("qwen_asr")
torch_datas, torch_binaries, torch_hidden = collect_all("torch")
transformers_datas, transformers_binaries, transformers_hidden = collect_all("transformers")
accelerate_datas, accelerate_binaries, accelerate_hidden = collect_all("accelerate")
tk_dnd_datas, tk_dnd_binaries, tk_dnd_hidden = collect_all("tkinterdnd2")
cv2_datas, cv2_binaries, cv2_hidden = collect_all("cv2")
pil_datas, pil_binaries, pil_hidden = collect_all("PIL")

hiddenimports = sorted(set([
    "app",
    "taiwan_subtitle",
    "qwen_asr",
    "transformers",
    "accelerate",
    "safetensors",
    "soundfile",
    "opencc",
    "tkinterdnd2",
    "subtitle_editor",
    "cv2",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    *qwen_hidden,
    *torch_hidden,
    *transformers_hidden,
    *accelerate_hidden,
    *tk_dnd_hidden,
    *cv2_hidden,
    *pil_hidden,
]))

datas = [
    *qwen_datas,
    *torch_datas,
    *transformers_datas,
    *accelerate_datas,
    *tk_dnd_datas,
    *cv2_datas,
    *pil_datas,
]
binaries = [
    *qwen_binaries,
    *torch_binaries,
    *transformers_binaries,
    *accelerate_binaries,
    *tk_dnd_binaries,
    *cv2_binaries,
    *pil_binaries,
]
ffmpeg = root / "runtime" / "ffmpeg" / "ffmpeg.exe"
if ffmpeg.exists():
    binaries.append((str(ffmpeg), "ffmpeg"))

analysis = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "jupyter", "notebook", "IPython"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TaiwanSubtitle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TaiwanSubtitle",
)
