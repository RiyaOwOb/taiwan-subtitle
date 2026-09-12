#!/usr/bin/env python3
"""Taiwan Subtitle Windows core pipeline.

Local-first Taiwanese Mandarin subtitle generation using TEA-ASR and the
Qwen3 forced aligner. Media is normalized by a bundled/system FFmpeg before
ASR so common video/audio containers work consistently on Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

APP_NAME = "TaiwanSubtitle"
APP_VERSION = "0.5.0"
PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_HF_HOME = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / APP_NAME / "models" / "huggingface"
DEFAULT_LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / APP_NAME / "logs"
DEFAULT_ASR_MODEL = "JacobLinCool/TEA-ASR-1.1"
DEFAULT_ASR_MODEL_SMALL = "JacobLinCool/TEA-ASR-1.1-mini"
DEFAULT_ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wmv", ".m4v", ".ts"}


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
    p = base / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _subprocess_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def bundled_ffmpeg_path() -> Path | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend([Path(meipass) / "ffmpeg" / "ffmpeg.exe", Path(meipass) / "ffmpeg.exe"])
    candidates.extend([
        PROJECT_DIR / "runtime" / "ffmpeg" / "ffmpeg.exe",
        PROJECT_DIR / "ffmpeg" / "ffmpeg.exe",
    ])
    for p in candidates:
        if p.is_file():
            return p
    return None


def find_ffmpeg() -> str | None:
    bundled = bundled_ffmpeg_path()
    if bundled:
        return str(bundled)
    return shutil.which("ffmpeg")


def ffmpeg_version() -> str | None:
    binary = find_ffmpeg()
    if not binary:
        return None
    try:
        out = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=8, **_subprocess_kwargs())
        first = (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else ""
        return first.strip() or None
    except Exception:
        return None


def detect_runtime() -> str:
    bits = [platform.system(), platform.machine()]
    if platform.system() == "Windows":
        bits[0] = "Windows"
    try:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
            bits.append(f"NVIDIA CUDA · {gpu}")
        else:
            bits.append("CPU")
    except Exception:
        bits.append("PyTorch not initialized")
    if find_ffmpeg():
        bits.append("FFmpeg OK")
    else:
        bits.append("FFmpeg missing")
    return " · ".join(bits)


def select_device(mode: str = "auto") -> tuple[str, Any, str]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("找不到 PyTorch。請重新安裝 Taiwan Subtitle。") from exc

    mode = mode.lower()
    if mode not in {"auto", "cpu", "cuda"}:
        raise ValueError("運算模式必須是 auto、cpu 或 cuda。")
    if mode == "cpu":
        return "cpu", torch.float32, "CPU"
    if mode == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定使用 CUDA，但找不到可用的 NVIDIA GPU。請確認 NVIDIA Driver 與 CUDA PyTorch wheel 已安裝。")
    if torch.cuda.is_available():
        bf16_ok = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        dtype = torch.bfloat16 if bf16_ok else torch.float16
        return "cuda:0", dtype, f"NVIDIA CUDA · {torch.cuda.get_device_name(0)}"
    return "cpu", torch.float32, "CPU"


def configure_hf_cache(cache_dir: Path | None = None) -> Path:
    cache = Path(cache_dir or os.environ.get("HF_HOME") or DEFAULT_HF_HOME).expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("HF_HUB_CACHE", str(cache / "hub"))
    Path(os.environ["HF_HUB_CACHE"]).mkdir(parents=True, exist_ok=True)
    return cache


def clean_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[\ue000-\uf8ff]+", "", text)
    text = text.replace("\x00", "")
    return " ".join(text.replace("\n", " ").split())


def to_traditional_taiwan(text: str) -> str:
    from opencc import OpenCC
    return OpenCC("s2twp").convert(text)


def srt_ts(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def smart_join(parts: list[str]) -> str:
    out = ""
    for raw in parts:
        unit = clean_text(raw)
        if not unit:
            continue
        if not out:
            out = unit
        elif unit[0] in "，。！？；：、」』）》〉）]}.>,.!?;:":
            out += unit
        elif out[-1] in "([［「『《〈（{“‘":
            out += unit
        elif re.search(r"[A-Za-z0-9]$", out) and re.match(r"^[A-Za-z0-9]", unit):
            out += " " + unit
        elif ("\u3400" <= out[-1] <= "\u9fff") and ("\u3400" <= unit[0] <= "\u9fff"):
            out += unit
        else:
            out += unit
    return out.strip()


def make_cues(items: list[dict[str, Any]], max_chars: int = 28, max_seconds: float = 5.0) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        text = smart_join([x["text"] for x in current])
        start = float(current[0]["start_time"])
        end = max(start + 0.05, float(current[-1]["end_time"]))
        if text:
            cues.append({"start": max(0.0, start), "end": end, "text": text})
        current = []
        current_chars = 0

    for item in items:
        text = clean_text(item.get("text", ""))
        if not text:
            continue
        start = float(item.get("start_time", item.get("start", 0.0)))
        end = max(start + 0.01, float(item.get("end_time", item.get("end", start + 0.1))))
        if current and (current_chars + len(text) > max_chars or end - float(current[0]["start_time"]) > max_seconds):
            flush()
        current.append({"text": text, "start_time": start, "end_time": end})
        current_chars += len(text)
        if re.search(r"[。！？!?；]$", text):
            flush()
    flush()
    return cues


def extract_alignment_items(result: Any) -> list[dict[str, Any]]:
    ts = getattr(result, "time_stamps", None)
    if ts is None:
        return []
    raw_items = getattr(ts, "items", ts)
    if raw_items is None:
        return []
    out: list[dict[str, Any]] = []
    for item in raw_items:
        text = getattr(item, "text", None)
        start = getattr(item, "start_time", None)
        end = getattr(item, "end_time", None)
        if isinstance(item, dict):
            text = item.get("text", text)
            start = item.get("start_time", item.get("start", start))
            end = item.get("end_time", item.get("end", end))
        if text is None or start is None or end is None:
            continue
        out.append({"text": str(text), "start_time": float(start), "end_time": float(end)})
    return out


def normalize_audio(input_path: Path, work_dir: Path, log: Callable[[str], None] = print, cancel_event=None) -> Path:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("找不到 FFmpeg。重新安裝 Taiwan Subtitle 即可恢復；也可把 ffmpeg.exe 放到 runtime\\ffmpeg\\。")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("使用者已取消。")
    output = work_dir / "audio.wav"
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-vn", "-sn", "-dn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-map_metadata", "-1", "-f", "wav", "-y", str(output)]
    log("[1/4] FFmpeg：正規化音訊為 16 kHz / mono WAV…")
    try:
        subprocess.run(cmd, check=True, timeout=None, **_subprocess_kwargs())
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg 無法讀取這個媒體檔案（exit code {exc.returncode}）。") from exc
    return output


MODEL_CACHE: dict[tuple[str, str | None, str, str, int, int], Any] = {}

def init_model(asr_model: str, aligner_model: str | None, device: str, dtype: Any, max_batch: int, max_new_tokens: int) -> Any:
    key = (asr_model, aligner_model, device, str(dtype), max_batch, max_new_tokens)
    cached = MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    from qwen_asr import Qwen3ASRModel
    kwargs: dict[str, Any] = {
        "dtype": dtype,
        "device_map": device,
        "max_inference_batch_size": max_batch,
        "max_new_tokens": max_new_tokens,
    }
    if aligner_model:
        kwargs["forced_aligner"] = aligner_model
        kwargs["forced_aligner_kwargs"] = {"dtype": dtype, "device_map": device}
    model = Qwen3ASRModel.from_pretrained(asr_model, **kwargs)
    MODEL_CACHE[key] = model
    return model


@dataclass
class RunResult:
    input: str
    srt: str
    txt: str
    json: str
    model: str
    aligner: str | None
    device: str
    language: str
    text: str
    cues: list[dict[str, Any]]
    elapsed_seconds: float
    warnings: list[str]


def transcribe(
    input_path: Path,
    output_dir: Path | None = None,
    asr_model: str = DEFAULT_ASR_MODEL,
    aligner_model: str | None = DEFAULT_ALIGNER_MODEL,
    language: str | None = "Chinese",
    context: str = "這是台灣中文影片，請使用自然的繁體中文與台灣常用詞彙。",
    device_mode: str = "auto",
    force_cpu: bool = False,
    force_gpu: bool = False,
    no_punctuation: bool = False,
    max_chars: int = 28,
    max_seconds: float = 5.0,
    max_batch: int = 1,
    max_new_tokens: int = 1024,
    cache_dir: Path | None = None,
    cancel_event=None,
    log: Callable[[str], None] = print,
) -> RunResult:
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到輸入檔：{input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的副檔名：{input_path.suffix}")

    output = (Path(output_dir).expanduser().resolve() if output_dir else input_path.parent)
    output.mkdir(parents=True, exist_ok=True)
    configure_hf_cache(cache_dir)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if force_cpu:
        device_mode = "cpu"
    elif force_gpu:
        device_mode = "cuda"
    device, dtype, device_name = select_device(device_mode)
    log(f"[2/4] 裝置：{device_name}")
    log(f"[3/4] 載入模型：{asr_model}")
    if aligner_model:
        log(f"       Forced Aligner：{aligner_model}")
    model = init_model(asr_model, aligner_model, device, dtype, max_batch, max_new_tokens)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("使用者已取消。")
    log("[4/4] AI 轉錄中… 首次使用會從 Hugging Face 下載模型。")
    with tempfile.TemporaryDirectory(prefix="taiwan-subtitle-") as td:
        audio_path = normalize_audio(input_path, Path(td), log=log, cancel_event=cancel_event)
        results = model.transcribe(
            audio=str(audio_path),
            language=language,
            context=context,
            return_time_stamps=bool(aligner_model),
        )

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("使用者已取消。")
    if not results:
        raise RuntimeError("ASR 沒有回傳結果。")

    result = results[0]
    raw_text = clean_text(getattr(result, "text", ""))
    traditional = to_traditional_taiwan(raw_text)
    detected_language = str(getattr(result, "language", None) or language or "Chinese")
    items = extract_alignment_items(result)
    warnings: list[str] = []
    cues = make_cues(items, max_chars=max_chars, max_seconds=max_seconds) if items else []
    if not cues and traditional:
        cues = [{"start": 0.0, "end": 0.1, "text": traditional}]
        warnings.append("未取得 Forced Aligner 時間戳，SRT 使用 fallback cue。")

    if no_punctuation:
        for cue in cues:
            cue["text"] = re.sub(r"[，。！？；：、,.!?;:]", "", cue["text"])

    stem = input_path.stem
    srt_path = output / f"{stem}.srt"
    txt_path = output / f"{stem}.txt"
    json_path = output / f"{stem}.json"
    srt_blocks = []
    for i, cue in enumerate(cues, 1):
        end = max(float(cue["start"]) + 0.05, float(cue["end"]))
        srt_blocks.append(f"{i}\n{srt_ts(cue['start'])} --> {srt_ts(end)}\n{cue['text']}\n")
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8-sig")
    txt_path.write_text(traditional + ("\n" if traditional else ""), encoding="utf-8-sig")

    elapsed = time.perf_counter() - started
    payload = {
        "app_version": APP_VERSION,
        "full_transcript": traditional,
        "raw_transcript": raw_text,
        "language": detected_language,
        "segments": cues,
        "alignment_items": items,
        "model": asr_model,
        "aligner": aligner_model,
        "device": device,
        "elapsed_seconds": round(elapsed, 3),
        "warnings": warnings,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    log(f"完成：{srt_path}")
    log(f"      {len(cues)} 個字幕 cue · {elapsed:.1f} 秒")
    return RunResult(
        input=str(input_path), srt=str(srt_path), txt=str(txt_path), json=str(json_path),
        model=asr_model, aligner=aligner_model, device=device, language=detected_language,
        text=traditional, cues=cues, elapsed_seconds=elapsed, warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Taiwan Subtitle — Windows 台灣繁中 AI 字幕")
    p.add_argument("input", type=Path, help="影片／音訊檔")
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--asr-model", default=DEFAULT_ASR_MODEL)
    p.add_argument("--small-model", action="store_true")
    p.add_argument("--aligner-model", default=DEFAULT_ALIGNER_MODEL)
    p.add_argument("--no-aligner", action="store_true")
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p.add_argument("--cpu", action="store_true", help="相容舊版參數：強制 CPU")
    p.add_argument("--gpu", action="store_true", help="相容舊版參數：強制 CUDA")
    p.add_argument("--language", default="Chinese")
    p.add_argument("--context", default="這是台灣中文影片，請使用自然的繁體中文與台灣常用詞彙。")
    p.add_argument("--max-chars", type=int, default=28)
    p.add_argument("--max-seconds", type=float, default=5.0)
    p.add_argument("--max-batch", type=int, default=1)
    p.add_argument("--max-new-tokens", type=int, default=1024)
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--no-punctuation", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asr = DEFAULT_ASR_MODEL_SMALL if args.small_model else args.asr_model
    aligner = None if args.no_aligner else args.aligner_model
    try:
        result = transcribe(
            args.input, args.output_dir,
            asr_model=asr,
            aligner_model=aligner,
            language=args.language,
            context=args.context,
            device_mode=args.device,
            force_cpu=args.cpu,
            force_gpu=args.gpu,
            no_punctuation=args.no_punctuation,
            max_chars=args.max_chars,
            max_seconds=args.max_seconds,
            max_batch=args.max_batch,
            max_new_tokens=args.max_new_tokens,
            cache_dir=args.cache_dir,
        )
        print(json.dumps(asdict(result), ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"錯誤：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
