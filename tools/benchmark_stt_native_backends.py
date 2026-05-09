#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.stt_backend_router import select_stt_backend
from core.runtime import config
from core.settings_profiles import materialize_user_settings


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def _edit_distance(a: list[str], b: list[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, left in enumerate(a, start=1):
        cur = [i]
        for j, right in enumerate(b, start=1):
            cost = 0 if left == right else 1
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _word_error_rate(reference: str, hypothesis: str) -> float | None:
    ref_words = _normalize_text(reference).split()
    hyp_words = _normalize_text(hypothesis).split()
    if not ref_words:
        return None
    return _edit_distance(ref_words, hyp_words) / float(len(ref_words))


def _segments_text(payload: dict[str, Any]) -> str:
    if payload.get("text"):
        return _normalize_text(str(payload.get("text") or ""))
    parts = []
    for seg in payload.get("segments") or []:
        if isinstance(seg, dict) and str(seg.get("text") or "").strip():
            parts.append(str(seg.get("text") or "").strip())
    return _normalize_text(" ".join(parts))


def _read_worker_result(proc, task_id: str | None = None) -> dict[str, Any]:
    texts: list[str] = []
    segments: list[dict[str, Any]] = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        data = json.loads(line)
        if task_id and data.get("task_id") != task_id:
            continue
        if data.get("fatal_error") or data.get("error"):
            raise RuntimeError(data.get("fatal_error") or data.get("error"))
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        if isinstance(result, dict):
            text = _segments_text(result)
            if text:
                texts.append(text)
            if isinstance(result.get("segments"), list):
                segments.extend([seg for seg in result.get("segments") if isinstance(seg, dict)])
        if data.get("done"):
            break
    return {"text": _normalize_text(" ".join(texts)), "segments": segments}


def _run_whisperkit(audio: str, model: str, word_timestamps: bool) -> dict[str, Any]:
    from core.audio.whisperkit_persistent import ensure_worker, stop_worker, submit_task

    proc = ensure_worker(None, log_label="Bench-WhisperKit")
    if proc is None:
        raise RuntimeError("WhisperKit persistent worker is not available")
    try:
        task_id = submit_task(
            proc=proc,
            chunk_paths=[audio],
            model=model,
            language=getattr(config, "LANGUAGE", "ko"),
            temperature_values=[0.0],
            word_timestamps=word_timestamps,
        )
        return _read_worker_result(proc, task_id)
    finally:
        stop_worker(proc)


def _run_mlx(audio: str, model: str, word_timestamps: bool) -> dict[str, Any]:
    from core.audio.whisper_mlx import ensure_worker, stop_worker, submit_task

    proc = ensure_worker(None)
    try:
        task_id = submit_task(
            proc=proc,
            chunk_paths=[audio],
            model=model,
            language=getattr(config, "LANGUAGE", "ko"),
            temperature_values=[0.0],
            word_timestamps=word_timestamps,
        )
        return _read_worker_result(proc, task_id)
    finally:
        stop_worker(proc)


def _run_whisper_cpp(audio: str, model: str, word_timestamps: bool) -> dict[str, Any]:
    from core.audio.whisper_cpp import run_whisper

    proc = run_whisper(
        chunk_paths=[audio],
        model=model,
        language=getattr(config, "LANGUAGE", "ko"),
        temperature_tuple="(0.0,)",
        log_label="Bench-whisper.cpp",
        word_timestamps=word_timestamps,
    )
    if proc is None:
        raise RuntimeError("whisper.cpp backend is not available")
    try:
        return _read_worker_result(proc)
    finally:
        proc.wait(timeout=5)


def _backend_ready(choice) -> dict[str, Any]:
    ready = False
    detail = ""
    try:
        if choice.backend == "whisperkit_persistent":
            from core.audio.whisperkit_persistent import find_whisperkit_persistent_worker

            detail = find_whisperkit_persistent_worker()
            ready = bool(detail)
        elif choice.backend == "mlx":
            import importlib.util

            ready = importlib.util.find_spec("mlx_whisper") is not None
            detail = "mlx_whisper importable" if ready else "mlx_whisper missing"
        elif choice.backend == "whisper_cpp":
            from core.audio.whisper_cpp import find_whisper_cpp_binary, resolve_whisper_cpp_model_path

            binary = find_whisper_cpp_binary()
            model_path = resolve_whisper_cpp_model_path(choice.model)
            ready = bool(binary and model_path)
            detail = f"binary={binary or 'missing'}, model={model_path or 'missing'}"
        else:
            detail = "not a native benchmark backend"
    except Exception as exc:
        detail = str(exc)
    return {"ready": ready, "detail": detail}


def _transcribe(choice, audio: str, word_timestamps: bool) -> dict[str, Any]:
    if choice.backend == "whisperkit_persistent":
        return _run_whisperkit(audio, choice.model, word_timestamps)
    if choice.backend == "mlx":
        return _run_mlx(audio, choice.model, word_timestamps)
    if choice.backend == "whisper_cpp":
        return _run_whisper_cpp(audio, choice.model, word_timestamps)
    raise RuntimeError(f"unsupported benchmark backend: {choice.backend}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare macOS native STT backends.")
    parser.add_argument("--audio", default="", help="Optional WAV/audio file. Without it, only readiness is reported.")
    parser.add_argument("--reference-text", default="", help="Optional reference transcript text.")
    parser.add_argument("--reference-file", default="", help="Optional UTF-8 text reference transcript path.")
    parser.add_argument("--word-timestamps", action="store_true", help="Run with word timestamps enabled.")
    parser.add_argument("--execute", action="store_true", help="Actually transcribe --audio instead of dry-run readiness.")
    parser.add_argument(
        "--models",
        nargs="*",
        default=[
            getattr(config, "WHISPERKIT_QUALITY_MODEL", "whisperkit-persistent:large-v3"),
            getattr(config, "MLX_FALLBACK_MODEL", "mlx-community/whisper-large-v3-turbo"),
            "whisper.cpp:large-v3-turbo",
        ],
        help="Model selectors to compare.",
    )
    args = parser.parse_args()

    reference = args.reference_text
    if args.reference_file:
        reference = Path(args.reference_file).expanduser().read_text(encoding="utf-8", errors="replace")

    settings = materialize_user_settings({})
    rows = []
    for model in args.models:
        choice = select_stt_backend(model, {**settings, "stt_backend_policy": "auto"})
        ready = _backend_ready(choice)
        row: dict[str, Any] = {
            "requested_model": model,
            "backend": choice.backend,
            "resolved_model": choice.model,
            "reason": choice.reason,
            "ready": ready["ready"],
            "readiness_detail": ready["detail"],
        }
        if args.audio and args.execute and ready["ready"]:
            started = time.perf_counter()
            try:
                result = _transcribe(choice, str(Path(args.audio).expanduser()), bool(args.word_timestamps))
                elapsed = time.perf_counter() - started
                text = _segments_text(result)
                row.update(
                    {
                        "elapsed_sec": round(elapsed, 3),
                        "text_chars": len(text),
                        "segments": len(result.get("segments") or []),
                        "wer": _word_error_rate(reference, text) if reference else None,
                        "text_preview": text[:160],
                    }
                )
            except Exception as exc:
                row.update({"error": str(exc), "elapsed_sec": round(time.perf_counter() - started, 3)})
        rows.append(row)

    payload = {
        "schema": "ai_subtitle_studio.macos_native_stt_benchmark.v1",
        "mode": "execute" if args.audio and args.execute else "dry-run",
        "audio": str(Path(args.audio).expanduser()) if args.audio else "",
        "word_timestamps": bool(args.word_timestamps),
        "has_reference": bool(reference),
        "results": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
