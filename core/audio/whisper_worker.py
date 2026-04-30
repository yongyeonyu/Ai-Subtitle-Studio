# Version: 03.01.23
# Phase: PHASE2
"""
core/whisper_worker.py
Run faster-whisper in a separate process and return JSON lines per chunk.
Fail fast on model-load / chunk errors so caller can mark the job as failed.
"""
import sys
import json
import os
import traceback


def _write_json_line(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    import io
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    try:
        task = json.loads(sys.stdin.readline())
    except Exception as e:
        _write_json_line({"fatal_error": str(e), "stage": "task_decode"})
        sys.exit(1)
    chunk_paths = task["chunk_paths"]
    model_path = task["model"]
    fallback_model = task.get("fallback_model") or ""
    language = task["language"]

    try:
        from faster_whisper import WhisperModel
        import ctranslate2
    except Exception as e:
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
        _write_json_line({"fatal_error": str(e), "stage": "import"})
        sys.exit(1)

    device = "cpu"
    try:
        supported = ctranslate2.get_supported_compute_types("cuda")
        if "float16" in supported:
            device, compute = "cuda", "float16"
        elif "int8_float32" in supported:
            device, compute = "cuda", "int8_float32"
        elif "int8" in supported:
            device, compute = "cuda", "int8"
        else:
            raise RuntimeError("no suitable cuda compute type")
    except Exception:
        supported = ctranslate2.get_supported_compute_types("cpu")
        priority = ["int8", "int8_float32", "float32"]
        compute = "float32"
        for p in priority:
            if p in supported:
                compute = p
                break

    sys.stderr.write(f"  [FW] device={device}, compute_type={compute}\n")
    sys.stderr.flush()

    loaded_model = model_path
    try:
        whisper = WhisperModel(model_path, device=device, compute_type=compute)
        sys.stderr.write("  [FW] model load complete\n")
        sys.stderr.flush()
    except Exception as e:
        if fallback_model and fallback_model != model_path:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.write(f"  [FW] model load failed, fallback={fallback_model}\n")
            sys.stderr.flush()
            try:
                whisper = WhisperModel(fallback_model, device=device, compute_type=compute)
                loaded_model = fallback_model
                sys.stderr.write("  [FW] fallback model load complete\n")
                sys.stderr.flush()
            except Exception as fallback_exc:
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
                _write_json_line({"fatal_error": str(fallback_exc), "stage": "model_load", "model": model_path, "fallback_model": fallback_model})
                sys.exit(2)
        else:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            _write_json_line({"fatal_error": str(e), "stage": "model_load", "model": model_path})
            sys.exit(2)

    for chunk_path in chunk_paths:
        try:
            segments, info = whisper.transcribe(
                chunk_path,
                language=language,
                word_timestamps=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            result_segments = []
            for seg in segments:
                words = []
                if seg.words:
                    for w in seg.words:
                        words.append({
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": getattr(w, "probability", None),
                        })
                result_segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": words,
                    "avg_logprob": getattr(seg, "avg_logprob", None),
                    "compression_ratio": getattr(seg, "compression_ratio", None),
                    "no_speech_prob": getattr(seg, "no_speech_prob", None),
                    "temperature": getattr(seg, "temperature", None),
                })
            _write_json_line({
                "backend": "faster-whisper",
                "loaded_model": loaded_model,
                "segments": result_segments,
                "chunk_path": chunk_path,
                "language_probability": getattr(info, "language_probability", None),
            })
        except Exception as e:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            _write_json_line({"error": str(e), "stage": "transcribe", "chunk_path": chunk_path})
            sys.exit(3)


if __name__ == "__main__":
    main()
