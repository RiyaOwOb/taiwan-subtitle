# Taiwan Subtitle v0.6 PyInstaller spec.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path.cwd().resolve()

transformers_datas, transformers_binaries, transformers_hidden = collect_all("transformers")
torch_datas, torch_binaries, torch_hidden = collect_all("torch")
accelerate_datas, accelerate_binaries, accelerate_hidden = collect_all("accelerate")
tk_dnd_datas, tk_dnd_binaries, tk_dnd_hidden = collect_all("tkinterdnd2")
cv2_datas, cv2_binaries, cv2_hidden = collect_all("cv2")
pil_datas, pil_binaries, pil_hidden = collect_all("PIL")

hiddenimports = sorted(set([
    "app",
    "taiwan_subtitle",
    "transformers",
    "transformers.models.qwen3_asr",
    "transformers.models.qwen3_asr.configuration_qwen3_asr",
    "transformers.models.qwen3_asr.feature_extraction_qwen3_asr",
    "transformers.models.qwen3_asr.processing_qwen3_asr",
    "transformers.models.qwen3_asr.modeling_qwen3_asr",
    "transformers.models.qwen3_asr.modular_qwen3_asr",
    "accelerate",
    "safetensors",
    "huggingface_hub",
    "soundfile",
    "opencc",
    "tkinterdnd2",
    "subtitle_editor",
    "cv2",
    "PIL",
    "PIL.Image",
    *transformers_hidden,
    *torch_hidden,
    *accelerate_hidden,
    *tk_dnd_hidden,
    *cv2_hidden,
    *pil_hidden,
]))

datas = [
    *transformers_datas,
    *torch_datas,
    *accelerate_datas,
    *tk_dnd_datas,
    *cv2_datas,
    *pil_datas,
]
binaries = [
    *transformers_binaries,
    *torch_binaries,
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
