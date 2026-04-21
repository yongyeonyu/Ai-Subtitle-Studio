# Version: 02.02.01
# Phase: PHASE1-B
"""
core/whisper_worker.py
별도 프로세스에서 faster-whisper 실행 (PyQt6 충돌 회피)
stdin으로 작업 수신 → stdout으로 JSON 결과 반환
"""
import sys
import json


def main():
    import io
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # stdin에서 작업 정보 읽기
    task = json.loads(sys.stdin.readline())

    chunk_paths = task["chunk_paths"]
    model_path = task["model"]
    language = task["language"]

    from faster_whisper import WhisperModel

    # compute_type 자동 선택
    import ctranslate2
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

    sys.stderr.write(f"  🔧 device={device}, compute_type={compute}\n")
    sys.stderr.flush()

    whisper = WhisperModel(model_path, device=device, compute_type=compute)
    sys.stderr.write(f"  ✅ 모델 로딩 완료\n")
    sys.stderr.flush()

    for chunk_path in chunk_paths:
        try:
            segments, info = whisper.transcribe(
                chunk_path,
                language=language,
                word_timestamps=True,
                beam_size=5,
                condition_on_previous_text=False
            )

            result_segments = []
            for seg in segments:
                words = []
                if seg.words:
                    for w in seg.words:
                        words.append({
                            "word": w.word,
                            "start": w.start,
                            "end": w.end
                        })
                result_segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": words
                })

            result = {"segments": result_segments}
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()