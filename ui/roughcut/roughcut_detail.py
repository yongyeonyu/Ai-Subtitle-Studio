# Version: 03.01.12
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.roughcut.roughcut_format import fmt_time
from ui.style import COLORS, button_style, label_style, line_icon


class RoughcutDetailMixin:
    """Compact selected-chapter detail panel for the bottom roughcut controls."""

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: #151C20; border: 1px solid #2D3942; border-radius: 6px; }")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.detail_chapter_lbl = self._detail_value_label("챕터", "-")
        self.detail_subtitle_lbl = self._detail_value_label("사용 자막", "-")
        self.detail_story_lbl = self._detail_value_label("Story", "-")
        self.detail_risk_lbl = self._detail_value_label("위험도", "-")
        self.detail_output_lbl = self._detail_value_label("출력", "-")
        for item in (
            self.detail_chapter_lbl,
            self.detail_subtitle_lbl,
            self.detail_story_lbl,
            self.detail_risk_lbl,
            self.detail_output_lbl,
        ):
            row.addWidget(item, stretch=1)
        lay.addLayout(row)

        self.detail_reason_lbl = QLabel("상세: 선택 챕터의 컷 근거와 story role 정보가 표시됩니다.")
        self.detail_reason_lbl.setWordWrap(True)
        self.detail_reason_lbl.setStyleSheet(label_style("muted", 10))
        lay.addWidget(self.detail_reason_lbl)

        edit_row = QHBoxLayout()
        edit_row.setContentsMargins(0, 0, 0, 0)
        edit_row.setSpacing(6)
        edit_title = QLabel("컷 조정")
        edit_title.setStyleSheet(label_style("muted", 10, bold=True))
        edit_row.addWidget(edit_title)

        self.cut_action_combo = QComboBox()
        self.cut_action_combo.addItems(["keep", "trim", "remove", "highlight", "move"])
        self.cut_action_combo.setFixedHeight(30)
        self.cut_action_combo.setMinimumWidth(116)
        self.cut_action_combo.setStyleSheet(self._detail_input_style())
        edit_row.addWidget(self.cut_action_combo)

        self.cut_trim_start_spin = self._trim_spinbox()
        self.cut_trim_end_spin = self._trim_spinbox()
        for label_text, spinbox in (("In", self.cut_trim_start_spin), ("Out", self.cut_trim_end_spin)):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style("muted", 9, bold=True))
            edit_row.addWidget(lbl)
            edit_row.addWidget(spinbox)

        self.btn_apply_cut_edit = QPushButton("적용")
        self.btn_apply_cut_edit.setIcon(line_icon("check", "#FFFFFF", 15))
        self.btn_apply_cut_edit.setStyleSheet(button_style("primary", font_size="10px", padding="5px 9px"))
        self.btn_apply_cut_edit.setFixedHeight(30)
        self.btn_apply_cut_edit.clicked.connect(self._apply_cut_edit)
        edit_row.addWidget(self.btn_apply_cut_edit)
        edit_row.addStretch(1)
        lay.addLayout(edit_row)
        self._set_cut_edit_controls_enabled(False)
        return panel

    def _detail_value_label(self, title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setMinimumWidth(110)
        label.setStyleSheet(
            "QLabel { background: #10161A; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 5px; padding: 4px 6px; font-size: 10px; font-weight: 700; }"
        )
        return label

    def _set_detail_empty(self) -> None:
        self.detail_chapter_lbl.setText("챕터: -")
        self.detail_subtitle_lbl.setText("사용 자막: -")
        self.detail_story_lbl.setText("Story: -")
        self.detail_risk_lbl.setText("위험도: -")
        self.detail_output_lbl.setText("출력: -")
        self.detail_reason_lbl.setText("상세: 선택 챕터의 컷 근거와 story role 정보가 표시됩니다.")
        self.detail_risk_lbl.setStyleSheet(self._detail_status_style(COLORS["muted"]))
        self._set_cut_edit_controls_enabled(False)

    def _update_detail_panel(self, row: int, chapter, decision=None, edl_segment=None) -> None:
        subtitle_range = self._subtitle_range_for_chapter(chapter)
        role = chapter.story_role or "-"
        confidence = f"{float(chapter.role_confidence or 0.0):.2f}" if getattr(chapter, "role_confidence", 0.0) else "-"
        story = f"{role} / 신뢰 {confidence}"
        if chapter.move_recommendation and chapter.move_recommendation != "keep_order":
            story = f"{story} / {chapter.move_recommendation}"

        safety = decision.safety if decision else "acceptable"
        action = decision.action if decision else "-"
        risk_text = self._risk_text(chapter, decision)
        risk_color = self._risk_color(safety, getattr(chapter, "needs_review", False))
        output = "제외"
        if edl_segment is not None:
            output = f"{fmt_time(edl_segment.output_start)}-{fmt_time(edl_segment.output_end)}"

        chapter_text = f"{row + 1} / {chapter.chapter_id}"
        self.detail_chapter_lbl.setText(f"챕터: {chapter_text}")
        self.detail_subtitle_lbl.setText(f"사용 자막: {subtitle_range}")
        self.detail_story_lbl.setText(f"Story: {story}")
        self.detail_risk_lbl.setText(f"위험도: {risk_text}")
        self.detail_output_lbl.setText(f"출력: {output}")
        self.detail_risk_lbl.setStyleSheet(self._detail_status_style(risk_color))

        reason = decision.reason if decision and decision.reason else chapter.story_reason or "컷 근거 없음"
        time_range = f"{fmt_time(chapter.start)}-{fmt_time(chapter.end)}"
        trim = "-"
        if decision is not None and decision.source_start is not None and decision.source_end is not None:
            trim = f"{fmt_time(decision.source_start)}-{fmt_time(decision.source_end)}"
        elif edl_segment is not None:
            trim = f"{fmt_time(edl_segment.source_start)}-{fmt_time(edl_segment.source_end)}"
        safety_detail = self._format_safety_reason(reason)
        self.detail_reason_lbl.setText(
            f"상세: 원본 {time_range} / 판단 {action} / Trim {trim} / {safety_detail}"
        )
        self._sync_cut_edit_controls(chapter, decision, edl_segment)

    def _subtitle_range_for_chapter(self, chapter) -> str:
        segments = []
        try:
            segments = list(self._editor_segments())
        except Exception:
            segments = []
        used = []
        start = float(getattr(chapter, "start", 0.0) or 0.0)
        end = float(getattr(chapter, "end", start) or start)
        for index, segment in enumerate(segments, start=1):
            seg_start = float(segment.get("start", 0.0) or 0.0)
            seg_end = float(segment.get("end", seg_start) or seg_start)
            if seg_end > start and seg_start < end:
                used.append(segment.get("subtitle_id") or segment.get("id") or index)
        if not used:
            return "없음"
        return f"{used[0]}-{used[-1]} ({len(used)}개)"

    def _risk_text(self, chapter, decision) -> str:
        if decision is not None and decision.safety == "risky":
            return "risky / 위험"
        if decision is not None and decision.safety == "ideal":
            return "ideal / 안전"
        if getattr(chapter, "needs_review", False):
            return "acceptable / 검토"
        return "acceptable / 주의"

    def _risk_color(self, safety: str, needs_review: bool) -> str:
        if safety == "risky":
            return COLORS["danger"]
        if needs_review:
            return COLORS["warning"]
        if safety == "ideal":
            return COLORS["accent"]
        return COLORS["muted"]

    def _detail_status_style(self, color: str) -> str:
        return (
            "QLabel { background: #10161A; "
            f"color: {color}; border: 1px solid #2D3942; "
            "border-radius: 5px; padding: 4px 6px; font-size: 10px; font-weight: 800; }"
        )

    def _format_safety_reason(self, reason: str) -> str:
        reason = str(reason or "").strip()
        if not reason:
            return "근거 컷 안전도 정보 없음"
        parts = []
        for raw in reason.split(";"):
            item = raw.strip()
            if not item:
                continue
            label = self._safety_reason_label(item)
            if label:
                parts.append(label)
        if not parts:
            parts = [reason]
        return "근거 " + " / ".join(parts)

    def _safety_reason_label(self, item: str) -> str:
        if item.startswith("cut_safety:"):
            return f"안전도 {item.split(':', 1)[1]}"
        if item.startswith("start:"):
            return f"시작 {self._boundary_reason_text(item.split(':', 1)[1])}"
        if item.startswith("end:"):
            return f"종료 {self._boundary_reason_text(item.split(':', 1)[1])}"
        if item.startswith("inside_gap:"):
            return f"gap boundary {item.split(':', 1)[1]}"
        if item.startswith("inside_short_gap:"):
            return f"short gap boundary {item.split(':', 1)[1]}"
        if item in {"near_phrase_boundary", "near_gap_edge", "inside_phrase_body", "no_gap_or_phrase_boundary"}:
            return self._boundary_reason_text(item)
        if item.startswith("user_manual_cut_edit"):
            return "사용자 수동 조정"
        return item

    def _boundary_reason_text(self, value: str) -> str:
        mapping = {
            "inside_gap": "gap boundary",
            "inside_short_gap": "short gap boundary",
            "near_phrase_boundary": "phrase boundary",
            "near_gap_edge": "gap edge",
            "inside_phrase_body": "inside phrase",
            "no_gap_or_phrase_boundary": "boundary 없음",
        }
        if value.startswith("inside_gap:"):
            return f"gap boundary {value.split(':', 1)[1]}"
        if value.startswith("inside_short_gap:"):
            return f"short gap boundary {value.split(':', 1)[1]}"
        return mapping.get(value, value)

    def _detail_input_style(self) -> str:
        return (
            "QComboBox, QDoubleSpinBox { background: #10161A; color: #F5F7FA; "
            "border: 1px solid #2D3942; border-radius: 5px; padding: 3px 6px; "
            "font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )

    def _trim_spinbox(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setSingleStep(0.10)
        spin.setRange(0.0, 999999.0)
        spin.setFixedHeight(30)
        spin.setMinimumWidth(82)
        spin.setStyleSheet(self._detail_input_style())
        return spin

    def _set_cut_edit_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.cut_action_combo,
            self.cut_trim_start_spin,
            self.cut_trim_end_spin,
            self.btn_apply_cut_edit,
        ):
            widget.setEnabled(bool(enabled))

    def _sync_cut_edit_controls(self, chapter, decision=None, edl_segment=None) -> None:
        self._updating_cut_controls = True
        try:
            start = float(getattr(chapter, "start", 0.0) or 0.0)
            end = float(getattr(chapter, "end", start) or start)
            source_start = start
            source_end = end
            if decision is not None and decision.source_start is not None and decision.source_end is not None:
                source_start = float(decision.source_start)
                source_end = float(decision.source_end)
            elif edl_segment is not None:
                source_start = float(edl_segment.timeline_start if edl_segment.timeline_start is not None else edl_segment.source_start)
                source_end = float(edl_segment.timeline_end if edl_segment.timeline_end is not None else edl_segment.source_end)
            max_end = max(end, source_end, source_start + 0.05)
            self.cut_trim_start_spin.setRange(0.0, max_end)
            self.cut_trim_end_spin.setRange(0.05, max_end)
            self.cut_trim_start_spin.setValue(max(0.0, min(source_start, max_end)))
            self.cut_trim_end_spin.setValue(max(source_start + 0.05, min(source_end, max_end)))
            action = decision.action if decision is not None else "keep"
            index = self.cut_action_combo.findText(action)
            self.cut_action_combo.setCurrentIndex(index if index >= 0 else 0)
            self._set_cut_edit_controls_enabled(True)
        finally:
            self._updating_cut_controls = False

    def _apply_cut_edit(self) -> None:
        if getattr(self, "_updating_cut_controls", False):
            return
        row = int(getattr(self, "_preview_row", -1))
        chapter = self._chapter_for_row(row)
        if chapter is None:
            return
        trim_start = float(self.cut_trim_start_spin.value())
        trim_end = float(self.cut_trim_end_spin.value())
        if trim_end <= trim_start:
            trim_end = trim_start + 0.05
            self.cut_trim_end_spin.setValue(trim_end)
        edit = self._user_edits.setdefault(chapter.chapter_id, {})
        edit["action"] = self.cut_action_combo.currentText().strip() or "keep"
        edit["trim_start"] = round(trim_start, 3)
        edit["trim_end"] = round(trim_end, 3)
        edit["status"] = "사용자 수정됨"
        edit["reason"] = "user_manual_cut_edit"
        result = self._result_with_user_edits(self._result)
        if result is not None:
            self._result = result
        self._populate_result()
        if row >= 0 and row < self.table.rowCount():
            self.table.selectRow(row)
            self._preview_row_data(row)
        self._persist_roughcut_state()
