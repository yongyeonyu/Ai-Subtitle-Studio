# Version: 03.02.16
# Phase: PHASE2
"""
core/state_manager.py
[v01.00.06] 모드/상태 정의 문서 1:1 반영
- StateManager는 ViewModel (표시 전용)
- 완료 판단 / 저장 판단 로직 제거
- 하위 호환 별칭 포함
"""
from PyQt6.QtCore import QObject, pyqtSignal


class SubtitleStateManager(QObject):
    """
    UI 상태 전용 ViewModel
    - MODE: 작업의 종류 (변하지 않음)
    - STATE: 진행 단계 (EditorPipeline이 결정)
    - 이 클래스는 '판단'을 하지 않는다.
    """

    # (mode, state, is_locked, is_dirty, status_text, button_text, button_enabled)
    sig_ui_update = pyqtSignal(str, str, bool, bool, str, str, bool)

    # MODE 정의 (작업 종류)
    MODE_EDIT      = "MODE_EDIT"
    MODE_AI_ALL    = "MODE_AI_ALL"
    MODE_PARTIAL   = "MODE_PARTIAL"
    MODE_FROM_HERE = "MODE_FROM_HERE"
    MODE_AUTO      = "MODE_AUTO"

    # STATE 정의 (진행 단계)
    ST_IDLE     = "ST_IDLE"
    ST_PROC     = "ST_PROC"
    ST_EDITING  = "ST_EDITING"
    ST_AUTOSAVE = "ST_AUTOSAVE"
    ST_COMP     = "ST_COMP"
    ST_SAVED    = "ST_SAVED"

    def __init__(self):
        super().__init__()
        self.mode = self.MODE_EDIT
        self.state = self.ST_IDLE
        self.is_locked = False
        self.is_dirty = False
        self._status_msg = "💤 대기중"
        self._button_text = "시작"
        self._button_enabled = True
        self.current_file = ""

    # ── 내부 헬퍼 ──
    def _mode_prefix(self):
        return {
            self.MODE_EDIT:      "[자막 편집]",
            self.MODE_AI_ALL:    "[자막 전체 생성]",
            self.MODE_PARTIAL:   "[구간 재생성]",
            self.MODE_FROM_HERE: "[이후 전체 재생성]",
            self.MODE_AUTO:      "[자동 처리]"
        }.get(self.mode, "")

    def _emit(self):
        label = f"{self._mode_prefix()} {self._status_msg}"
        self.sig_ui_update.emit(
            self.mode, self.state, self.is_locked, self.is_dirty,
            label, self._button_text, self._button_enabled
        )

    # ── 상태 반영 API (판단 ❌ / 반영 ✅) ──
    def set_idle(self):
        self.state = self.ST_IDLE
        self.is_locked = False
        self._status_msg = "💤 대기중"
        self._button_text = "▶ 시작"
        self._button_enabled = True
        self._emit()

    def start_processing(self):
        self.state = self.ST_PROC
        self.is_locked = True
        self.is_dirty = True
        self._status_msg = "⏳ 처리중..."
        self._button_text = "⏳ 처리중"
        self._button_enabled = True
        self._emit()

    def update_progress(self, current, total, percent, custom_msg=""):
        if self.state != self.ST_PROC:
            return
        if custom_msg:
            self._status_msg = custom_msg
        elif not self._is_stage_status_active():
            self._status_msg = f"처리중 ({current:02d}/{total:02d}) / {percent}%"
        self._emit()

    def _is_stage_status_active(self):
        text = str(self._status_msg or "")
        text_l = text.lower()
        return any(
            key in text_l or key in text
            for key in ("vad", "whisper", "llm", "오디오", "추출", "인식", "자막 생성", "최적화")
        )

    def complete_ai(self):
        self.state = self.ST_COMP
        self.is_locked = False
        self.is_dirty = True
        self._status_msg = "✨ 자막 생성 완료"
        self._button_text = "🔄 재시작"
        self._button_enabled = True
        self._emit()

    def complete_save(self):
        self.state = self.ST_SAVED
        self.is_locked = False
        self.is_dirty = False
        self._status_msg = "💾 저장 완료"
        self._button_text = "🔄 재시작"
        self._button_enabled = True
        self._emit()

    def start_editing(self):
        if self.is_locked:
            return
        self.state = self.ST_EDITING
        self.is_dirty = True
        self._status_msg = "✏ 편집 중"
        self._emit()

    def start_autosave(self):
        self.state = self.ST_AUTOSAVE
        self._status_msg = "💾 자동 저장 중..."
        self._emit()

    def stop_processing(self, msg="작업이 중단되었습니다.", send_ntfy=True):
        """send_ntfy 파라미터는 호환성 유지용 (실제 ntfy 전송 없음)"""
        self.state = self.ST_IDLE
        self.is_locked = False
        self._status_msg = msg
        self._button_text = "🔄 재시작"
        self._button_enabled = True
        self._emit()

    # ── 하위 호환 별칭 (editor_widget 등 기존 코드 대응) ──
    def init_state(self):
        self.mode = self.MODE_EDIT
        self.set_idle()

    def init_auto_state(self):
        self.mode = self.MODE_AUTO
        self.set_idle()

    def start_ai_all(self):
        self.mode = self.MODE_AI_ALL
        self.start_processing()

    def start_auto_mode(self):
        self.mode = self.MODE_AUTO
        self.start_processing()

    def start_partial_segment(self):
        self.mode = self.MODE_PARTIAL
        self.start_processing()

    def start_partial_from_here(self):
        self.mode = self.MODE_FROM_HERE
        self.start_processing()

    def complete_auto_mode(self):
        self.complete_ai()

    def set_custom_status(self, msg):
        self._status_msg = msg
        self._emit()

    def _broadcast(self):
        self._emit()
