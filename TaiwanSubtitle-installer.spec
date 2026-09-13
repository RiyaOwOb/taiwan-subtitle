# Taiwan Subtitle v0.6.2 full installer build.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

root = Path.cwd().resolve()

# Avoid collect_all(torch): it unnecessarily bundles every PyTorch binary/data file.
# PyInstaller's built-in torch hooks collect the binaries actually needed by imports.
transformers_hidden = collect_submodules("transformers.models.qwen3_asr")
transformers_datas = collect_data_files("transformers", includes=["**/*.json", "**/*.txt", "**/*.pyi"], excludes=["**/tests/**"])

hiddenimports = sorted(set([
    "app", "taiwan_subtitle", "subtitle_editor",
    "transformers",
    "transformers.models.qwen3_asr",
    "accelerate", "safetensors", "huggingface_hub", "soundfile",
    "opencc", "tkinterdnd2", "cv2", "PIL", "PIL.Image",
    "numpy", "psutil",
    *transformers_hidden,
]))

datas = [*transformers_datas]

binaries = []
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
    excludes=[
        "pytest", "jupyter", "notebook", "IPython",
        "matplotlib", "scipy", "pandas", "torchaudio", "torchvision",
        "tensorflow", "keras", "onnxruntime",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name="TaiwanSubtitle",
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
)
COLLECT(
    exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="TaiwanSubtitle",
)
