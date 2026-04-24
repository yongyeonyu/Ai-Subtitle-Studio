# Version: 02.02.01
# Phase: PHASE1-B
"""
core/worker_threads.py - PyQt6 QThread 워커 (크PD 변환)
tkinter: threading.Thread + root.after(0, ...) 패턴
PyQt6 : QThread + pyqtSignal 패턴

모든 무거운 작업(Whisper, Ollama, ffmpeg)이 여기서 실행.
UI는 절대 block되지 않음.
"""
from PyQt6.QtCore import QThread, pyqtSignal
from logger import get_logger


class PipelineWorker(QThread):
    """
    자막 생성 전체 파이프라인 워커.
    CoreBackend._run_all() 로직을 QThread로 래핑.

    시그널:
      segments_ready(list)  : 청크별 세그먼트 배출 (실시간 에디터 추가용)
      status_update(str)    : 상태 메시지 (헤더 표시용)
      finished_ok()         : 정상 완료
      finished_err(str)     : 오류 완료
    """
    segments_ready  = pyqtSignal(list)   # (chunk_segments)
    status_update   = pyqtSignal(str)
    finished_ok     = pyqtSignal()
    finished_err    = pyqtSignal(str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        try:
            self._backend._run_all_qt(self)
            if not self._stop_flag:
                self.finished_ok.emit()
        except Exception as e:
            import traceback
            get_logger().log(f"❌ 파이프라인 오류:\n{traceback.format_exc()}")
            self.finished_err.emit(str(e))


class OllamaTranslateWorker(QThread):
    """
    단어 번역 비동기 워커 (editor_popup용).
    Ollama REST 호출 결과를 시그널로 반환.
    """
    result_ready = pyqtSignal(str, str, str, str)  # (en_word, en_meaning, ko_word, ko_meaning)

    def __init__(self, word: str, model: str, parent=None):
        super().__init__(parent)
        self._word  = word
        self._model = model

    def run(self):
        en_word, en_meaning = self._translate("en")
        ko_word, ko_meaning = self._translate("ko")
        self.result_ready.emit(en_word, en_meaning, ko_word, ko_meaning)

    def _translate(self, target_lang: str):
        import re, requests
        try:
            if target_lang == "en":
                prompt = (f"Translate '{self._word}' into a natural English term. "
                          "Reply STRICTLY: EnglishText : 한국어 뜻")
            else:
                prompt = (f"Translate '{self._word}' into a natural Korean term. "
                          "Reply STRICTLY: 한국어텍스트 : 한국어 뜻")
            payload = {
                "model": self._model, "prompt": prompt, "stream": False,
                "keep_alive": -1, "options": {"temperature": 0.0, "num_predict": 50}
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=4)
            if r.status_code == 200:
                result = r.json().get("response", "").strip()
                sep = ":" if ":" in result else ("-" if "-" in result else None)
                if sep:
                    word, meaning = result.split(sep, 1)
                else:
                    word, meaning = result, "사전적 의미 생략"
                word = word.strip()
                if target_lang == "en":
                    word = re.sub(r'[^a-zA-Z\s]', '', word).lower()
                else:
                    word = re.sub(r'[^가-힣\s]', '', word)
                return word.strip(), meaning.strip()
        except Exception:
            pass
        return "", ""
