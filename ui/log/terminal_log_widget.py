# Version: 03.01.04
# Phase: PHASE2
"""Terminal log panel widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from ui.style import named_panel_style


def _normalize_log_line(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _friendly_log_entry(raw_line: str) -> tuple[str, str]:
    text = _normalize_log_line(raw_line)
    lower = text.lower()
    if not text:
        return "empty", ""

    if "설정 적용:" in text:
        return "settings", "준비: 자막 품질 설정을 적용했어요."
    if "[블록속도 스케줄러]" in text:
        return "settings", "준비: 긴 영상에 맞춰 처리 순서를 조정했어요."
    if "[llm-proaprofile]" in lower or "품질 검사/자동교정 보호" in text:
        return "settings", "준비: 자막 품질 점검 규칙을 불러왔어요."
    if "[텍스트 lora]" in lower or "교정 memory" in lower or "사용자 단어" in text:
        return "lora_setup", "준비: 사용자 말투와 교정 기록을 반영할 준비를 했어요."
    if "리소스 자동 모드" in text or "[lora/deep-전처리]" in lower:
        return "resource", "준비: 컴퓨터 속도에 맞춰 처리 강도를 자동 조절해요."
    if "[stt경계-다듬기판정]" in text or "문체 confidence" in lower:
        return "timing", "진행: 문장 경계와 끊는 위치를 다듬고 있어요."
    if "[정제-교정사전]" in text:
        return "cleanup", "진행: 자주 틀리는 표현을 자동으로 고치고 있어요."

    if any(token in lower for token in ("[컷 경계]", "컷 경계", "scan-cut", "cut boundary")):
        if any(token in lower for token in ("완료", "재사용", "verified", "confirmed", "cache")):
            return "cut_boundary", "완료: 장면 전환 위치를 확인했어요."
        return "cut_boundary", "진행: 장면이 바뀌는 지점을 찾고 있어요."
    if any(token in lower for token in ("[전처리]", "오디오 추출", "ffmpeg 오디오", "ffmpeg")):
        return "preprocess", "진행: 영상에서 자막 작업용 소리를 준비하고 있어요."
    if any(token in lower for token in ("[음성]", "clearvoice", "deepfilter", "rnnoise", "resemble")):
        return "audio", "진행: 소음을 줄이고 목소리를 또렷하게 정리하고 있어요."
    if any(token in lower for token in ("[vad]", "ten_vad", "ten vad", "silero", "음성 섹터")):
        return "vad", "진행: 말하는 구간을 찾고 있어요."
    if "[stt2]" in lower and "loading weights" in lower:
        return "stt", "진행: 보조 인식 모델을 준비하고 있어요."
    if "word_timestamp" in lower or "단어 정밀" in text:
        return "stt", "진행: 단어 위치를 더 정확하게 맞추고 있어요."
    if any(token in lower for token in ("[stt", "whisper", "병렬 인식", "진행 상황", "transcription completed")):
        return "stt", "진행: 음성을 자막 초안으로 바꾸고 있어요."
    if any(token in lower for token in ("[자막 llm]", "[llm-보정차단]", "최종 llm", "자동교정")):
        return "subtitle_llm", "진행: 문장을 자연스럽게 다듬고 있어요."
    if "roughcut" in lower or "러프컷" in text:
        return "roughcut", "진행: 장면 요약과 컷 초안을 만들고 있어요."
    if "[lora]" in lower or ("lora" in lower and "text lora" not in lower):
        return "lora", "진행: 사용자 말투와 선호 표현을 반영하고 있어요."
    if "[딥러닝]" in text or "deep learning" in lower or "deep subtitle" in lower:
        return "deep_learning", "진행: 애매한 자막을 한 번 더 점검하고 있어요."

    if any(token in text for token in ("프로젝트 저장 완료", "저장 완료:", ".srt 저장 완료", "💾 저장 완료", "📦 프로젝트 저장 완료")):
        return "save", "완료: 자막과 프로젝트를 저장했어요."
    if "자막 생성 완료" in text:
        return "done", "완료: 자막 생성이 끝났어요."
    if any(token in text for token in ("실패", "오류", "중단", "경고", "⚠️")):
        return "warning", "알림: 확인이 필요한 항목이 있어요."

    return "generic", text


class FriendlyTerminalLogTextEdit(QTextEdit):
    """Keep raw logs for internal logic while showing user-friendly summaries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_lines = 800
        self._raw_lines: list[str] = []
        self._display_entries: list[tuple[str, str]] = []

    def raw_log_text(self) -> str:
        return "\n".join(self._raw_lines)

    def append(self, text: str) -> None:  # type: ignore[override]
        self._ingest_lines([str(text or "")])
        self._render_display()

    def setPlainText(self, text: str) -> None:  # type: ignore[override]
        lines = str(text or "").splitlines()
        self._raw_lines = []
        self._display_entries = []
        self._ingest_lines(lines)
        self._render_display()

    def clear(self) -> None:  # type: ignore[override]
        self._raw_lines = []
        self._display_entries = []
        super().clear()

    def _ingest_lines(self, lines: list[str]) -> None:
        for raw_line in list(lines or []):
            line = str(raw_line or "")
            if not line.strip():
                continue
            self._raw_lines.append(line)
            if len(self._raw_lines) > self._max_lines:
                self._raw_lines = self._raw_lines[-self._max_lines:]
            category, summary = _friendly_log_entry(line)
            if not summary:
                continue
            if self._display_entries and self._display_entries[-1][0] == category:
                if self._display_entries[-1][1] == summary:
                    continue
                self._display_entries[-1] = (category, summary)
            else:
                self._display_entries.append((category, summary))
            if len(self._display_entries) > self._max_lines:
                self._display_entries = self._display_entries[-self._max_lines:]

    def _render_display(self) -> None:
        display_text = "\n".join(text for _category, text in self._display_entries)
        cursor = self.textCursor()
        had_selection = cursor.hasSelection()
        scroll_value = self.verticalScrollBar().value()
        scroll_max = self.verticalScrollBar().maximum()
        stick_to_bottom = scroll_value >= max(0, scroll_max - 4)
        super().setPlainText(display_text)
        if had_selection:
            self.setTextCursor(cursor)
        else:
            self.moveCursor(QTextCursor.MoveOperation.End)
        if not stick_to_bottom:
            self.verticalScrollBar().setValue(scroll_value)


class TerminalLogWidget(QWidget):
    """Terminal log panel that owns the QTextEdit used by MainWindow logging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("TerminalLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.log_text = FriendlyTerminalLogTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont()
        font.setPointSize(9)
        self.log_text.setFont(font)
        self.log_text.document().setMaximumBlockCount(800)
        self.log_text.setStyleSheet(
            "background: #151C20; color: #DCE6ED; border: none; padding: 6px 8px; line-height: 140%;"
        )
        layout.addWidget(self.log_text)
