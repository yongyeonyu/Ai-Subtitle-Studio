# Version: 03.01.25
# Phase: PHASE2
"""Subtitle quality candidate comparison dialog."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QVBoxLayout

from ui.style import button_style, label_style, settings_dialog_stylesheet


class QualityCandidateDialog(QDialog):
    def __init__(self, segment: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("자막 후보 비교")
        self.setMinimumWidth(760)
        self.setMinimumHeight(440)
        self.setStyleSheet(settings_dialog_stylesheet())
        self.segment = dict(segment or {})
        self.selected_candidate: dict[str, Any] | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        quality = dict(self.segment.get("quality") or {})
        score = quality.get("confidence_score")
        score_text = "-" if score is None else f"{float(score):.1f}"
        header = QLabel(f"현재 품질: {quality.get('confidence_label', 'gray')} · {score_text}점")
        header.setStyleSheet(label_style("text", 13, bold=True))
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_candidate_selected)
        body.addWidget(self.list_widget, 1)

        detail = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("후보를 선택하세요")
        detail.addWidget(self.text_edit, 1)
        self.reason_lbl = QLabel("")
        self.reason_lbl.setWordWrap(True)
        self.reason_lbl.setStyleSheet(label_style("muted", 11))
        detail.addWidget(self.reason_lbl)
        body.addLayout(detail, 2)
        root.addLayout(body, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_apply = QPushButton("적용")
        self.btn_apply.setStyleSheet(button_style("primary"))
        self.btn_apply.clicked.connect(self._apply_selected)
        btn_row.addWidget(self.btn_apply)
        btn_restore = QPushButton("원래대로")
        btn_restore.setStyleSheet(button_style("toolbar"))
        btn_restore.clicked.connect(self._restore_original)
        btn_row.addWidget(btn_restore)
        btn_close = QPushButton("닫기")
        btn_close.setStyleSheet(button_style("toolbar"))
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        self._populate_candidates()

    def _populate_candidates(self):
        candidates = list(self.segment.get("quality_candidates") or [])
        if not candidates:
            candidates = [
                {
                    "candidate_id": "existing",
                    "source": "existing",
                    "text": str(self.segment.get("text", "") or ""),
                    "score": dict(self.segment.get("quality") or {}).get("confidence_score"),
                    "reason": "저장된 후보가 없습니다.",
                    "safe_to_apply": False,
                }
            ]
        for candidate in candidates:
            score = candidate.get("score")
            score_text = "-" if score is None else f"{float(score):.1f}"
            safe = " · 자동가능" if candidate.get("safe_to_apply") else ""
            label = f"{candidate.get('source', 'candidate')} · {score_text}점{safe}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, dict(candidate))
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _on_candidate_selected(self, current, _previous):
        candidate = current.data(Qt.ItemDataRole.UserRole) if current else {}
        self.text_edit.setPlainText(str(candidate.get("text", "") or ""))
        reason = str(candidate.get("reason", "") or "")
        safety = str(candidate.get("safety_reason", "") or "")
        self.reason_lbl.setText(f"{reason}\n{safety}".strip())
        self.btn_apply.setEnabled(str(candidate.get("candidate_id", "")) != "existing")

    def _apply_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.selected_candidate = dict(item.data(Qt.ItemDataRole.UserRole) or {})
        self.accept()

    def _restore_original(self):
        self.selected_candidate = {
            "candidate_id": "restore_original",
            "source": "original",
            "text": str(self.segment.get("quality", {}).get("auto_corrected_from") or self.segment.get("text", "") or ""),
            "reason": "원래 자막으로 복원",
        }
        self.accept()
