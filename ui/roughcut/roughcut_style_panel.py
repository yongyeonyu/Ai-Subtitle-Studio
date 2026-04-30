# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ui.style import button_style, label_style, panel_style


DEFAULT_ROUGHCUT_EXPORT_STYLE = {
    "transition": "cut",
    "duration_sec": 0.5,
    "font_family": "Noto Sans KR",
    "font_size": 42,
    "position": "bottom_center",
    "scope": "roughcut_project",
}


class RoughcutStylePanel(QWidget):
    styleSaved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(panel_style("surface"))
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(7)

        title = QLabel("글로벌 스타일")
        title.setStyleSheet(label_style("text", 12, bold=True))
        root.addWidget(title)
        note = QLabel("러프컷 프로젝트 전용 export style입니다. 미지원 렌더 경로에서는 렌더 계획 metadata로만 저장됩니다.")
        note.setWordWrap(True)
        note.setStyleSheet(label_style("muted", 10))
        root.addWidget(note)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        self.transition_combo = self._combo(("cut", "fade", "none"))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.0, 5.0)
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.setDecimals(1)
        self.font_combo = self._combo(("Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(16, 96)
        self.position_combo = self._combo(("bottom_center", "center", "top_center"))
        for widget in (self.duration_spin, self.size_spin):
            widget.setStyleSheet(
                "QSpinBox, QDoubleSpinBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
                "border-radius: 6px; padding: 4px 7px; min-height: 26px; }"
            )
        form.addRow("전환", self.transition_combo)
        form.addRow("지속", self.duration_spin)
        form.addRow("폰트", self.font_combo)
        form.addRow("크기", self.size_spin)
        form.addRow("위치", self.position_combo)
        root.addLayout(form)

        self.save_btn = QPushButton("스타일 저장")
        self.save_btn.setStyleSheet(button_style("toolbar", font_size="10px", padding="5px 9px"))
        self.save_btn.clicked.connect(lambda: self.styleSaved.emit(self.style_payload()))
        root.addWidget(self.save_btn)
        self.set_style(DEFAULT_ROUGHCUT_EXPORT_STYLE)

    def set_style(self, payload: dict | None) -> None:
        style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        if isinstance(payload, dict):
            style.update(payload)
        self._set_combo(self.transition_combo, style.get("transition"))
        self.duration_spin.setValue(float(style.get("duration_sec", 0.5) or 0.5))
        self._set_combo(self.font_combo, style.get("font_family"))
        self.size_spin.setValue(int(style.get("font_size", 42) or 42))
        self._set_combo(self.position_combo, style.get("position"))

    def style_payload(self) -> dict:
        return {
            "transition": self.transition_combo.currentText(),
            "duration_sec": float(self.duration_spin.value()),
            "font_family": self.font_combo.currentText(),
            "font_size": int(self.size_spin.value()),
            "position": self.position_combo.currentText(),
            "scope": "roughcut_project",
        }

    def _combo(self, values: tuple[str, ...]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(values))
        combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 7px; min-height: 26px; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        return combo

    def _set_combo(self, combo: QComboBox, value) -> None:
        index = combo.findText(str(value or ""))
        if index >= 0:
            combo.setCurrentIndex(index)


__all__ = ["DEFAULT_ROUGHCUT_EXPORT_STYLE", "RoughcutStylePanel"]
