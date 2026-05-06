from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout

from core.engine.subtitle_why import build_subtitle_why_payload, format_subtitle_why_text
from core.engine.subtitle_one_click_fix import ONE_CLICK_FIX_ACTIONS
from ui.style import button_style, label_style, settings_dialog_stylesheet


class SubtitleWhyDialog(QDialog):
    def __init__(self, segment: dict[str, Any], *, index: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("왜 이렇게 생성됐나")
        self.setMinimumWidth(780)
        self.setMinimumHeight(520)
        self.setStyleSheet(settings_dialog_stylesheet())
        self.segment = dict(segment or {})
        self.payload = build_subtitle_why_payload(self.segment, index=index)
        self.selected_action: str = ""
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        summary = dict(self.payload.get("summary") or {})
        actions = " / ".join(str(item) for item in list(summary.get("actions") or [])[:4]) or "근거 없음"
        header = QLabel(f"자막 결정 근거 · LoRA {summary.get('lora_score', 0)}점")
        header.setStyleSheet(label_style("text", 13, bold=True))
        root.addWidget(header)

        action_lbl = QLabel(actions)
        action_lbl.setWordWrap(True)
        action_lbl.setStyleSheet(label_style("muted", 11))
        root.addWidget(action_lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(format_subtitle_why_text(self.payload))
        root.addWidget(self.text_edit, 1)

        btn_row = QHBoxLayout()
        for action, label in (
            ("re_recognize_region", ONE_CLICK_FIX_ACTIONS["re_recognize_region"]),
            ("recheck_cut_only", ONE_CLICK_FIX_ACTIONS["recheck_cut_only"]),
            ("restore_source_no_llm", ONE_CLICK_FIX_ACTIONS["restore_source_no_llm"]),
            ("reapply_similar_style", ONE_CLICK_FIX_ACTIONS["reapply_similar_style"]),
        ):
            btn = QPushButton(label)
            btn.setStyleSheet(button_style("toolbar"))
            btn.clicked.connect(lambda _checked=False, value=action: self._select_action(value))
            btn_row.addWidget(btn)
        btn_row.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.setStyleSheet(button_style("toolbar"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _select_action(self, action: str):
        self.selected_action = str(action or "")
        self.accept()


__all__ = ["SubtitleWhyDialog"]
