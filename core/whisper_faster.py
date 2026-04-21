# Version: 02.02.00
# Phase: PHASE1-B
"""
core/whisper_faster.py
Windows 전용 Whisper 백엔드 (faster-whisper)
- media_processor.py의 proc.stdout.readline() 인터페이스와 호환
- subprocess 대신 스레드 + 파이프로 JSON 스트리밍
"""
import io
import json
import threading
from logger import get_logger


class _FakeProc:
    """media_processor가 기대하는 Popen 호환 객체"""

    def __init__(self):
        self._reader, self._writer = io.StringIO(), None
        self._buffer = io.StringIO()
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._lines = []
        self._line_ready = threading.Event()
        self._line_idx = 0
        self.returncode = 0
        self.stderr = io.StringIO()

        # stdout 흉내
        self.stdout = self

    def _push_line(self, line: str):
        with self._lock:
            self._lines.append(line)
        self._line_ready.set()

    def readline(self):
        while True:
            with self._lock:
                if self._line_idx < len(self._lines):
                    line = self._lines[self._line_idx]
                    self._line_idx += 1
                    return line
            if self._done.is_set():
                with self._lock:
                    if self._line_idx < len(self._lines):
                        line = self._lines[self._line_idx]
                        self._line_idx += 1
                        return line
                return ""
            self._line_ready.wait(timeout=1.0)
            self._line_ready.clear()

    def wait(self):
        self._done.wait()
        return 0

    def poll(self):
        return 0 if self._done.is_set() else None

    def terminate(self):
        self._done.set()

    def kill(self):
        self._done.set()


def run_whisper(chunk_paths: list, model: str, language: str, temperature_tuple: str):
    """
    faster-whisper 실행.
    media_processor.py 호환: Popen-like 객체 반환 (stdout.readline() 가능)
    """
    proc = _FakeProc()

    def _worker():
        try:
            from faster_whisper import WhisperModel

            # 모델명 변환: mlx 모델명 → faster-whisper 호환
            fw_model = _convert_model_name(model)

            get_logger().log(f"  🔧 faster-whisper 모델 로딩: {fw_model}")
            whisper = WhisperModel(fw_model, device="cuda", compute_type="float16")

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
                    proc._push_line(json.dumps(result, ensure_ascii=False) + "\n")

                except Exception as e:
                    get_logger().log(f"  ❌ 청크 처리 오류: {e}")
                    proc._push_line(json.dumps({"error": str(e)}, ensure_ascii=False) + "\n")

        except Exception as e:
            get_logger().log(f"❌ faster-whisper 로딩 실패: {e}")
            for _ in chunk_paths:
                proc._push_line(json.dumps({"error": str(e)}, ensure_ascii=False) + "\n")
        finally:
            proc._done.set()
            proc._line_ready.set()

    t = threading.Thread(target=_worker, daemon=True, name="faster-whisper")
    t.start()

    return proc


def _convert_model_name(mlx_model: str) -> str:
    """mlx-community 모델명을 faster-whisper 호환 모델명으로 변환"""
    conversions = {
        "mlx-community/whisper-large-v3-mlx": "large-v3",
        "mlx-community/whisper-large-v3-turbo": "large-v3-turbo",
        "mlx-community/whisper-medium-mlx": "medium",
        "mlx-community/whisper-small-mlx": "small",
        "mlx-community/whisper-base-mlx": "base",
        "mlx-community/whisper-tiny-mlx": "tiny",
    }

    # 정확히 매칭되면 변환
    if mlx_model in conversions:
        return conversions[mlx_model]

    # "mlx-community/" 접두사 제거 후 매칭 시도
    stripped = mlx_model.replace("mlx-community/", "").replace("-mlx", "")
    for key, val in conversions.items():
        if val in stripped:
            return val

    # 이미 faster-whisper 형식이면 그대로
    valid = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "large-v3-turbo"]
    if mlx_model in valid:
        return mlx_model

    # 기본값
    get_logger().log(f"  ⚠️ 모델명 변환 불가: {mlx_model} → medium 사용")
    return "medium"