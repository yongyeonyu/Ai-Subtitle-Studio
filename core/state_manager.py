# Version: 01.00.05
"""
core/state_manager.py
[v01.00.05 수정사항]
- ntfy 푸시 알람을 state_manager에서 전부 제거
  → backend.py에서 _is_auto_pipeline 체크 후 통합 발송
"""
from PyQt6.QtCore import QObject, pyqtSignal


class SubtitleStateManager(QObject):
    # (모드, 상태, 에디터_잠금여부, 더티여부, 상태레이블, 버튼텍스트, 버튼활성화여부)
    sig_ui_update = pyqtSignal(str, str, bool, bool, str, str, bool)

    # 모드 정의
    MODE_EDIT      = "MODE_EDIT"
    MODE_AI_ALL    = "MODE_AI_ALL"
    MODE_PARTIAL   = "MODE_PARTIAL_RECOG"
    MODE_FROM_HERE = "MODE_FROM_HERE_RECOG"
    MODE_AUTO      = "MODE_AUTO"

    # 상태 정의
    ST_IDLE      = "IDLE"
    ST_PROC      = "PROCESSING"
    ST_EDITING   = "EDITING"
    ST_AUTOSAVE  = "AUTOSAVING"
    ST_COMP      = "PROCESS_COMPLETED"
    ST_SAVED     = "SAVE_COMPLETED"

    def __init__(self):
        super().__init__()
        self.mode = self.MODE_EDIT
        self.state = self.ST_IDLE
        self.is_dirty = False
        self.is_locked = False

        self._msg = "💤 대기중"
        self._btn_text = "▶️ 시작"
        self._btn_enabled = True
        self.current_file = ""

    # ---------------------------------------------------------
    # 내부 유틸
    # ---------------------------------------------------------
    def _get_prefix(self):
        if self.mode == self.MODE_AI_ALL:    return "[자막 전체 생성]"
        if self.mode == self.MODE_PARTIAL:   return "[AI 구간 재생성]"
        if self.mode == self.MODE_FROM_HERE: return "[AI 이후 전체 재생성]"
        if self.mode == self.MODE_AUTO:      return "[iCloud 자동]"
        return "[자막 편집]"

    def _broadcast(self):
        lbl_text = f"{self._get_prefix()} {self._msg}" if not self._msg.startswith("[") else self._msg
        self.sig_ui_update.emit(
            self.mode, self.state, self.is_locked, self.is_dirty,
            lbl_text, self._btn_text, self._btn_enabled
        )

    # ---------------------------------------------------------
    # 상태 전이 트리거 (API)
    # ---------------------------------------------------------
    def init_state(self):
        """최초 로드 — 일반 편집 모드"""
        self.mode, self.state = self.MODE_EDIT, self.ST_IDLE
        self.is_dirty, self.is_locked = False, False
        self._msg, self._btn_text, self._btn_enabled = "💤 대기중", "▶️ 시작", True
        self._broadcast()

    def init_auto_state(self):
        """iCloud 자동 모드 전용 최초 로드 — IDLE 상태, 버튼 활성화"""
        self.mode = self.MODE_AUTO
        self.state = self.ST_IDLE
        self.is_dirty, self.is_locked = False, False
        self._msg, self._btn_text, self._btn_enabled = "💤 대기중", "▶️ 시작", True
        self._broadcast()

    def start_ai_all(self):
        """전체 생성 시작"""
        self.mode, self.state = self.MODE_AI_ALL, self.ST_PROC
        self.is_dirty, self.is_locked = True, True
        self._msg, self._btn_text, self._btn_enabled = "⏳ 오디오 추출 및 정제 중...", "⏳ 처리중", True
        self._broadcast()

    def start_partial_segment(self):
        """현재 구간만 재생성"""
        self.mode, self.state = self.MODE_PARTIAL, self.ST_PROC
        self.is_dirty, self.is_locked = True, True
        self._msg, self._btn_text, self._btn_enabled = "🎯 선택 구간 정밀 생성 중...", "⚙️ 구간 생성중", True
        self._broadcast()

    def start_partial_from_here(self):
        """여기서부터 끝까지 재생성"""
        self.mode, self.state = self.MODE_FROM_HERE, self.ST_PROC
        self.is_dirty, self.is_locked = True, True
        self._msg, self._btn_text, self._btn_enabled = "🚀 남은 구간 이어서 생성 중...", "⚙️ 전체 생성중", True
        self._broadcast()

    def start_auto_mode(self):
        """iCloud 자동 처리 모드 시작"""
        self.mode = self.MODE_AUTO
        self.state = self.ST_PROC
        self.is_dirty, self.is_locked = True, True
        self._msg = "⏳ 자막 전체 생성 및 처리 중..."
        self._btn_text, self._btn_enabled = "⏳ 처리중", True
        self._broadcast()

    def stop_processing(self, msg="중지되었습니다.", send_ntfy=True):
        """중단 — send_ntfy 파라미터는 호환성 유지용 (실제 ntfy 전송 없음)"""
        self.mode, self.state = self.MODE_EDIT, self.ST_IDLE
        self.is_locked = False
        self._msg, self._btn_text, self._btn_enabled = msg, "🔄 재시작", True
        self._broadcast()

    def complete_ai(self):
        """AI 작업 완료"""
        self.state = self.ST_COMP
        self.is_dirty, self.is_locked = True, False
        self._msg, self._btn_text, self._btn_enabled = "✨ 생성 완료", "🔄 재시작", True
        self._broadcast()

    def complete_auto_mode(self):
        """iCloud 자동 처리 완료"""
        self.state = self.ST_COMP
        self.is_dirty, self.is_locked = True, False
        self._msg, self._btn_text, self._btn_enabled = "☁️ 자동처리 완료", "🔄 재시작", True
        self._broadcast()

    def complete_save(self):
        """수동/자동 저장 완료"""
        self.mode, self.state = self.MODE_EDIT, self.ST_SAVED
        self.is_dirty, self.is_locked = False, False
        self._msg, self._btn_text, self._btn_enabled = "✨ 저장 완료", "🔄 재시작", True
        self._broadcast()

    def start_editing(self):
        """수동 편집 시작"""
        if self.is_locked: return
        self.mode, self.state = self.MODE_EDIT, self.ST_EDITING
        self.is_dirty = True
        self._msg, self._btn_text, self._btn_enabled = "✏️ 편집 중", "🔄 재시작", True
        self._broadcast()

    def start_autosave(self):
        """자동 저장 시작"""
        if self.is_locked: return
        self.state = self.ST_AUTOSAVE
        self._msg = "💾 자동 저장 중..."
        self._broadcast()

    def update_progress(self, current, total, percentage, custom_msg=""):
        """진행률 중계 (빈번한 호출이므로 ntfy 없음)"""
        if self.state != self.ST_PROC: return
        self._msg = custom_msg if custom_msg else f"⏳ 처리중... ({current:02d}/{total:02d}) / {percentage}%"
        self._broadcast()

    def set_custom_status(self, msg):
        """자유 문구 세팅"""
        self._msg = msg
        self._broadcast()