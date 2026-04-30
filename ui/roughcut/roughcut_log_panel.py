# Version: 03.01.30
# Phase: PHASE2
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from ui.style import COLORS, label_style, panel_style


class RoughcutLogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: list[str] = []
        self.setStyleSheet(panel_style("surface"))
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(6)
        self.title_lbl = QLabel("실시간 로그")
        self.title_lbl.setStyleSheet(label_style("text", 12, bold=True))
        root.addWidget(self.title_lbl)
        self.status_lbl = QLabel("분석 대기")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_lbl.setStyleSheet(
            "QLabel { background: #10161A; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 5px 7px; font-size: 10px; font-weight: 700; }"
        )
        root.addWidget(self.status_lbl)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(116)
        self.text.setStyleSheet(
            "QTextEdit { background: #0F1518; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 7px; font-size: 10px; }"
        )
        root.addWidget(self.text, stretch=1)

    def clear(self) -> None:
        self._lines = []
        self.status_lbl.setText("분석 대기")
        self.text.setPlainText("")

    def set_status(self, text: str, progress: int | None = None) -> None:
        prefix = str(text or "분석 대기")
        if progress is not None:
            prefix = f"{prefix} · {max(0, min(100, int(progress)))}%"
        self.status_lbl.setText(prefix)

    def append_log(self, text: str, level: str = "info") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        tone = {"warning": "주의", "error": "오류", "done": "완료"}.get(level, "정보")
        self._lines.append(f"[{stamp}] {tone} · {text}")
        self._lines = self._lines[-80:]
        self.text.setPlainText("\n".join(self._lines))
        self.text.moveCursor(QTextCursor.MoveOperation.End)

    def set_result(self, result) -> None:
        chapters = len(tuple(getattr(result, "chapters", ()) or ()))
        majors = len(tuple(getattr(result, "segments", ()) or ()))
        warnings = tuple(getattr(result, "warnings", ()) or ())
        self.set_status("분석 완료", 100)
        if not self._lines:
            self.append_log(f"중분류 {majors}개 / 소분류 {chapters}개 분석 완료", "done")
        for warning in warnings[-8:]:
            self.append_log(str(warning), "warning")
        if not warnings:
            self.append_log("경고 없이 러프컷 결과를 구성했습니다.", "done")

    def set_reading_rows(self, count: int) -> None:
        self.set_status("읽는 중", 35)
        self.append_log(f"자막 row {int(count)}개를 중분류 후보로 읽는 중")


__all__ = ["RoughcutLogPanel"]
