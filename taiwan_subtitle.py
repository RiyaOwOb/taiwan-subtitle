#!/usr/bin/env python3
"""Taiwan Subtitle v0.6 Windows core.

Windows-first local transcription pipeline using TEA-ASR-1.1 through the
native Hugging Face Transformers Qwen3-ASR implementation, plus the native
Qwen3 Forced Aligner model. No MLX and no qwen-asr wrapper are required.
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
APP_VERSION = "0.6.0"
PROJECT_DIR = Path(__file__).resolve().parent
APPDATA_ROOT = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
DEFAULT_HF_HOME = APPDATA_ROOT / APP_NAME / "models" / "huggingface"
DEFAULT_LOG_DIR = APPDATA_ROOT / APP_NAME / "logs"
DEFAULT_ASR_MODEL = "JacobLinCool/TEA-ASR-1.1"
DEFAULT_ASR_MODEL_SMALL = "JacobLinCool/TEA-ASR-1.1-mini"
DEFAULT_ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B-hf"
SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".flac",
    ".aac", ".ogg", ".opus", ".wmv", ".m4v", ".ts",
}
ASR_CHUNK_SECONDS = 30.0


def app_data_dir() -> Path:
    p = APPDATA_ROOT / APP_NAME
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
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def bundled_ffmpeg_path() -> Path | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.extend([base / "ffmpeg" / "ffmpeg.exe", base / "ffmpeg.exe"])
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
    return str(bundled) if bundled else shutil.which("ffmpeg")


def ffmpeg_version() -> str | None:
    binary = find_ffmpeg()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=8, **_subprocess_kwargs()
        )
        output = result.stdout or result.stderr or ""
        return output.splitlines()[0].strip() if output else None
    except Exception:
        return None


def detect_runtime() -> str:
    bits = [platform.system(), platform.machine()]
    try:
        import torch
        if torch.cuda.is_available():
            bits.append(f"NVIDIA CUDA · {torch.cuda.get_device_name(0)}")
        else:
            bits.append("CPU")
    except Exception:
        bits.append("PyTorch not initialized")
    bits.append("FFmpeg OK" if find_ffmpeg() else "FFmpeg missing")
    return " · ".join(bits)


def select_device(mode: str = "auto") -> tuple[str, Any, str]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("找不到 PyTorch。請重新安裝 Taiwan Subtitle。") from exc

    mode = mode.lower()
    if mode not in {"auto", "cpu", "cuda"}:
        raise ValueError("運算模式必須是 auto、cpu 或 cuda。")
    if mode == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定使用 CUDA，但找不到可用的 NVIDIA GPU。請確認 NVIDIA Driver 與 CUDA PyTorch wheel 已安裝。")
    use_cuda = mode == "cuda" or (mode == "auto" and torch.cuda.is_available())
    if use_cuda:
        bf16_supported = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        dtype = torch.bfloat16 if bf16_supported else torch.float16
        return "cuda:0", dtype, f"NVIDIA CUDA · {torch.cuda.get_device_name(0)}"
    return "cpu", torch.float32, "CPU"


def configure_hf_cache(cache_dir: Path | None = None) -> Path:
    cache = Path(cache_dir or os.environ.get("HF_HOME") or DEFAULT_HF_HOME).expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_CACHE"] = str(cache / "hub")
    Path(os.environ["HF_HUB_CACHE"]).mkdir(parents=True, exist_ok=True)
    return cache


def clean_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[\ue000-\uf8ff]+", "", text)
    return " ".join(text.replace("\x00", "").replace("\n", " ").split())


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
            cues.append({"start": start, "end": end, "text": text})
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


def normalize_audio(input_path: Path, work_dir: Path, log: Callable[[str], None]) -> Path:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("找不到 FFmpeg。請重新安裝 Taiwan Subtitle。")
    output = work_dir / "audio.wav"
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(input_path),
        "-vn", "-sn", "-dn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-map_metadata", "-1", "-f", "wav", "-y", str(output),
    ]
    log("[1/4] FFmpeg：正規化音訊為 16 kHz / mono WAV…")
    try:
        subprocess.run(cmd, check=True, timeout=None, **_subprocess_kwargs())
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg 無法讀取這個媒體檔案（exit code {exc.returncode}）。") from exc
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("FFmpeg 沒有產生有效的 WAV 音訊。")
    return output


MODEL_CACHE: dict[tuple[Any, ...], Any] = {}


def _register_qwen3_asr_if_needed() -> None:
    """Compatibility hook for Transformers source revisions where mappings are lazy-loaded."""
    try:
        import transformers.models.qwen3_asr  # noqa: F401
    except Exception:
        pass


def _load_asr_model(model_id: str, device: str, dtype: Any) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    _register_qwen3_asr_if_needed()
    key = ("asr", model_id, device, str(dtype))
    if key in MODEL_CACHE:
        return MODEL_CACHE[key]

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForMultimodalLM.from_pretrained(
        model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    MODEL_CACHE[key] = (model, processor)
    return model, processor


def _load_aligner_model(model_id: str, device: str, dtype: Any) -> tuple[Any, Any]:
    from transformers import AutoModelForTokenClassification, AutoProcessor

    key = ("aligner", model_id, device, str(dtype))
    if key in MODEL_CACHE:
        return MODEL_CACHE[key]

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForTokenClassification.from_pretrained(
        model_id,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    MODEL_CACHE[key] = (model, processor)
    return model, processor


def _read_audio_chunks(wav_path: Path):
    import numpy as np
    import soundfile as sf

    audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    if sample_rate != 16000:
        raise RuntimeError(f"內部 WAV 取樣率異常：{sample_rate} Hz")
    total = len(audio)
    chunk_size = int(ASR_CHUNK_SECONDS * sample_rate)
    for start in range(0, total, chunk_size):
        end = min(total, start + chunk_size)
        chunk = np.asarray(audio[start:end], dtype=np.float32)
        if len(chunk):
            yield start / sample_rate, end / sample_rate, chunk


def _asr_chunk(model: Any, processor: Any, audio: Any, language: str | None, prompt: str | None, max_new_tokens: int) -> tuple[str, str | None]:
    import torch

    inputs = processor.apply_transcription_request(
        audio=audio,
        language=language,
        prompt=prompt or None,
    )
    inputs = inputs.to(model.device, model.dtype)
    with torch.inference_mode():
        output_ids = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
    parsed = processor.decode(generated_ids, return_format="parsed")
    item = parsed[0] if isinstance(parsed, list) and parsed else parsed
    if isinstance(item, dict):
        return clean_text(item.get("transcription", "")), item.get("language")
    text = processor.decode(generated_ids, return_format="transcription_only")
    if isinstance(text, list):
        text = text[0] if text else ""
    return clean_text(text), None


def _align_chunk(model: Any, processor: Any, audio: Any, transcript: str, language: str, offset: float) -> list[dict[str, Any]]:
    if not transcript.strip():
        return []
    import torch

    aligner_inputs, word_lists = processor.prepare_forced_aligner_inputs(
        audio=audio,
        transcript=transcript,
        language=language,
    )
    aligner_inputs = aligner_inputs.to(model.device, model.dtype)
    with torch.inference_mode():
        outputs = model(**aligner_inputs)
    timestamps = processor.decode_forced_alignment(
        logits=outputs.logits,
        input_ids=aligner_inputs["input_ids"],
        word_lists=word_lists,
        timestamp_token_id=model.config.timestamp_token_id,
    )[0]
    items: list[dict[str, Any]] = []
    for item in timestamps:
        text = clean_text(item.get("text", ""))
        start = item.get("start_time")
        end = item.get("end_time")
        if not text or start is None or end is None:
            continue
        items.append({
            "text": text,
            "start_time": float(start) + offset,
            "end_time": float(end) + offset,
        })
    return items


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
    max_new_tokens: int = 512,
    cache_dir: Path | None = None,
    cancel_event=None,
    log: Callable[[str], None] = print,
) -> RunResult:
    del max_batch  # v0.6 intentionally favors predictable Windows memory usage.

    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"找不到輸入檔：{input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的副檔名：{input_path.suffix}")

    output = Path(output_dir or input_path.parent).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    configure_hf_cache(cache_dir)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    if force_cpu:
        device_mode = "cpu"
    elif force_gpu:
        device_mode = "cuda"
    device, dtype, device_name = select_device(device_mode)
    log(f"[2/4] 裝置：{device_name}")
    log(f"[3/4] 載入模型：{asr_model}")
    if aligner_model:
        log(f"       Forced Aligner：{aligner_model}")

    asr_model_obj, asr_processor = _load_asr_model(asr_model, device, dtype)
    aligner_model_obj = aligner_processor = None
    if aligner_model:
        aligner_model_obj, aligner_processor = _load_aligner_model(aligner_model, device, dtype)

    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("使用者已取消。")

    started = time.perf_counter()
    all_alignment: list[dict[str, Any]] = []
    transcript_parts: list[str] = []
    detected_language = language or "Chinese"
    warnings: list[str] = []
    chunk_total = 0

    with tempfile.TemporaryDirectory(prefix="taiwan-subtitle-v06-") as td:
        wav_path = normalize_audio(input_path, Path(td), log)
        chunks = list(_read_audio_chunks(wav_path))
        chunk_total = len(chunks)
        if not chunks:
            raise RuntimeError("音訊沒有可處理內容。")

        for index, (chunk_start, chunk_end, audio) in enumerate(chunks, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("使用者已取消。")
            log(f"[4/4] AI 轉錄：{index}/{chunk_total} ({chunk_start:.1f}–{chunk_end:.1f}s)…")
            text, detected = _asr_chunk(
                asr_model_obj,
                asr_processor,
                audio,
                language=language,
                prompt=context,
                max_new_tokens=max_new_tokens,
            )
            if detected:
                detected_language = str(detected)
            if not text:
                continue
            transcript_parts.append(text)
            if aligner_model_obj is not None and aligner_processor is not None:
                try:
                    all_alignment.extend(
                        _align_chunk(
                            aligner_model_obj,
                            aligner_processor,
                            audio,
                            text,
                            language=detected_language,
                            offset=chunk_start,
                        )
                    )
                except Exception as exc:
                    warnings.append(f"第 {index} 段 Forced Align 失敗：{type(exc).__name__}: {exc}")

    full_text = smart_join(transcript_parts)
    cues = make_cues(all_alignment, max_chars=max_chars, max_seconds=max_seconds)
    if not cues and full_text:
        # Alignment disabled/unavailable: distribute chunk-level transcript timing.
        running = 0.0
        per_chunk = max(0.1, ASR_CHUNK_SECONDS)
        for part in transcript_parts:
            duration = min(per_chunk, max(0.1, len(part) * 0.18))
            cues.append({"start": running, "end": running + duration, "text": part})
            running += duration
        warnings.append("未取得字詞級時間戳，SRT 使用 chunk-level fallback timing。")

    if no_punctuation:
        for cue in cues:
            cue["text"] = re.sub(r"[，。！？；：、,.!?;:]", "", cue["text"])

    stem = input_path.stem
    srt_path = output / f"{stem}.srt"
    txt_path = output / f"{stem}.txt"
    json_path = output / f"{stem}.json"
    blocks = []
    for i, cue in enumerate(cues, 1):
        end = max(float(cue["start"]) + 0.05, float(cue["end"]))
        blocks.append(f"{i}\n{srt_ts(cue['start'])} --> {srt_ts(end)}\n{cue['text']}\n")
    srt_path.write_text("\n".join(blocks), encoding="utf-8-sig")
    txt_path.write_text(full_text + ("\n" if full_text else ""), encoding="utf-8-sig")

    elapsed = time.perf_counter() - started
    payload = {
        "app_version": APP_VERSION,
        "full_transcript": full_text,
        "language": detected_language,
        "segments": cues,
        "alignment_items": all_alignment,
        "model": asr_model,
        "aligner": aligner_model,
        "device": device,
        "backend": "huggingface-transformers-native",
        "elapsed_seconds": round(elapsed, 3),
        "warnings": warnings,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    log(f"完成：{srt_path}")
    log(f"      {len(cues)} 個字幕 cue · {elapsed:.1f} 秒")
    return RunResult(
        input=str(input_path),
        srt=str(srt_path),
        txt=str(txt_path),
        json=str(json_path),
        model=asr_model,
        aligner=aligner_model,
        device=device,
        language=detected_language,
        text=full_text,
        cues=cues,
        elapsed_seconds=elapsed,
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Taiwan Subtitle v0.6 — Windows 台灣繁中 AI 字幕")
    p.add_argument("input", type=Path)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--asr-model", default=DEFAULT_ASR_MODEL)
    p.add_argument("--small-model", action="store_true")
    p.add_argument("--aligner-model", default=DEFAULT_ALIGNER_MODEL)
    p.add_argument("--no-aligner", action="store_true")
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--language", default="Chinese")
    p.add_argument("--context", default="這是台灣中文影片，請使用自然的繁體中文與台灣常用詞彙。")
    p.add_argument("--max-chars", type=int, default=28)
    p.add_argument("--max-seconds", type=float, default=5.0)
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--no-punctuation", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asr = DEFAULT_ASR_MODEL_SMALL if args.small_model else args.asr_model
    aligner = None if args.no_aligner else args.aligner_model
    try:
        result = transcribe(
            args.input,
            args.output_dir,
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
