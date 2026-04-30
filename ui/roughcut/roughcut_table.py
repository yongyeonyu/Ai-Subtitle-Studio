# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from ui.roughcut.roughcut_format import EDITABLE_COLUMNS, fmt_time


class RoughcutTableMixin:
    def _populate_result(self):
        result = self._result
        if result is None:
            self._set_empty_state()
            return

        decisions = {decision.segment_id: decision for decision in result.edit_decisions}
        edl = {segment.segment_id: segment for segment in result.edl_segments}
        highlights = sum(1 for decision in result.edit_decisions if decision.action == "highlight")
        risky = sum(1 for decision in result.edit_decisions if decision.safety == "risky")
        output_duration = result.edl_segments[-1].output_end if result.edl_segments else 0.0
        values = [len(result.chapters), len(result.edl_segments), highlights, risky, fmt_time(output_duration)]
        for label, value in zip(self.metric_labels, values):
            label.setText(str(value))
        if hasattr(self, "major_panel"):
            self.major_panel.set_result(result)
        if hasattr(self, "title_panel"):
            self.title_panel.set_suggestions(getattr(result, "title_suggestions", ()) or ())
        if hasattr(self, "log_panel"):
            self.log_panel.set_result(result)
        if hasattr(self, "bottom_tabs"):
            self.bottom_tabs.set_result(result, self._editor_segments())

        self._updating_table = True
        self._row_chapter_ids = []
        self.table.setRowCount(len(result.chapters))
        for row, chapter in enumerate(result.chapters):
            decision = decisions.get(chapter.chapter_id)
            segment = edl.get(chapter.chapter_id)
            self._row_chapter_ids.append(chapter.chapter_id)
            edit = self._user_edits.get(chapter.chapter_id, {})
            output = f"{fmt_time(segment.output_start)}-{fmt_time(segment.output_end)}" if segment else "제외"
            midpoint = (chapter.start + chapter.end) / 2.0
            status = edit.get("status") or self._status_for(chapter, decision)
            row_values = [
                f"{fmt_time(chapter.start)}-{fmt_time(chapter.end)}",
                f"대표 {fmt_time(midpoint)}",
                chapter.summary or chapter.title,
                edit.get("title") or chapter.title or chapter.chapter_id,
                edit.get("tags") or ", ".join(chapter.tags or (chapter.story_role,)).strip(", "),
                status,
                decision.action if decision else "-",
                decision.safety if decision else "-",
                output,
            ]
            for col, value in enumerate(row_values):
                item = self._table_item(str(value), editable=col in EDITABLE_COLUMNS)
                if col in (0, 1, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif col in (5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5:
                    self._style_status_item(item, status)
                elif col == 7 and decision is not None:
                    self._style_safety_item(item, decision.safety)
                self.table.setItem(row, col, item)
        self._updating_table = False
        self.table.resizeRowsToContents()
        self.guide_text.setPlainText(result.guide_markdown)
        self._apply_safety_filter()
        if result.chapters:
            self.table.selectRow(0)
            self._preview_row_data(0)

    def _table_item(self, text: str, editable: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        flags = item.flags()
        if editable:
            item.setFlags(flags | Qt.ItemFlag.ItemIsEditable)
        else:
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _status_for(self, chapter, decision) -> str:
        if decision is not None and (decision.safety == "risky" or decision.action in {"move", "trim"}):
            return "검토 필요"
        if getattr(chapter, "needs_review", False):
            return "검토 필요"
        return "확정"

    def _style_status_item(self, item: QTableWidgetItem, status: str) -> None:
        if status == "사용자 수정됨":
            item.setForeground(Qt.GlobalColor.yellow)
        elif status == "검토 필요":
            item.setForeground(Qt.GlobalColor.red)
        else:
            item.setForeground(Qt.GlobalColor.green)

    def _style_safety_item(self, item: QTableWidgetItem, safety: str) -> None:
        if safety == "risky":
            item.setForeground(Qt.GlobalColor.red)
            item.setToolTip("risky: inside phrase 또는 안전한 boundary 없음")
        elif safety == "ideal":
            item.setForeground(Qt.GlobalColor.green)
            item.setToolTip("ideal: 충분한 gap boundary")
        else:
            item.setForeground(Qt.GlobalColor.yellow)
            item.setToolTip("acceptable: phrase boundary 또는 짧은 gap/edge")

    def _set_empty_state(self):
        self._updating_table = True
        for label in self.metric_labels:
            label.setText("-")
        self.source_lbl.setText("대기 중")
        self._row_chapter_ids = []
        self.table.setRowCount(0)
        self._updating_table = False
        self.guide_text.setPlainText("러프컷 분석 결과 없음")
        if hasattr(self, "major_panel"):
            self.major_panel.clear()
        if hasattr(self, "title_panel"):
            self.title_panel.clear()
        if hasattr(self, "log_panel"):
            self.log_panel.clear()
        if hasattr(self, "bottom_tabs"):
            self.bottom_tabs.clear()
        self.preview_thumb_lbl.setText("대표\n프레임")
        self.preview_title_lbl.setText("세그먼트 선택 대기")
        self.preview_time_lbl.setText("-")
        self.preview_summary_lbl.setText("러프컷 분석 결과 없음")
        self.preview_action_lbl.setText("판단: -")
        self.preview_safety_lbl.setText("안전: -")
        self.preview_trim_lbl.setText("Trim: -")
        self.preview_role_lbl.setText("Role: -")
        self.preview_source_lbl.setText("Clip: -")
        self.preview_reason_lbl.setText("컷 근거 대기")
        self.render_status_lbl.setText("렌더 대기")
        self._set_detail_empty()
        if hasattr(self, "safety_filter_combo"):
            self.safety_filter_combo.setCurrentText("전체")

    def _activate_editor(self):
        owner = self.owner
        if owner is not None and hasattr(owner, "_activate_editor_for_main_action"):
            owner._activate_editor_for_main_action()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if self._updating_table or item.column() not in EDITABLE_COLUMNS:
            return
        row = item.row()
        if row < 0 or row >= len(self._row_chapter_ids):
            return
        chapter_id = self._row_chapter_ids[row]
        edit = self._user_edits.setdefault(chapter_id, {})
        edit["title" if item.column() == 3 else "tags"] = item.text().strip()
        edit["status"] = "사용자 수정됨"
        status_item = self.table.item(row, 5)
        if status_item is not None:
            self._updating_table = True
            status_item.setText("사용자 수정됨")
            self._style_status_item(status_item, "사용자 수정됨")
            self._updating_table = False
        self._preview_row_data(row)
        try:
            edited_result = self._result_with_user_edits(self._result)
            if edited_result is not None:
                self.guide_text.setPlainText(edited_result.guide_markdown)
        except Exception:
            pass
        self._persist_roughcut_state()

    def _on_table_item_entered(self, item: QTableWidgetItem):
        if item is not None:
            self._play_preview(item.row(), muted=True, hover=True)

    def _on_table_cell_clicked(self, row: int, _column: int):
        self._preview_row_data(row)
        self._play_preview(row, muted=False)

    def _on_table_selection_changed(self):
        selected = self.table.selectedItems()
        if selected:
            self._preview_row_data(selected[0].row())

    def _chapter_for_row(self, row: int):
        if self._result is None or row < 0 or row >= len(self._row_chapter_ids):
            return None
        chapter_id = self._row_chapter_ids[row]
        for chapter in self._result.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        return None

    def _edl_for_row(self, row: int):
        if self._result is None or row < 0 or row >= len(self._row_chapter_ids):
            return None
        chapter_id = self._row_chapter_ids[row]
        for segment in self._result.edl_segments:
            if segment.segment_id == chapter_id or segment.chapter_id == chapter_id:
                return segment
        return None

    def _decision_for_row(self, row: int):
        if self._result is None or row < 0 or row >= len(self._row_chapter_ids):
            return None
        chapter_id = self._row_chapter_ids[row]
        for decision in self._result.edit_decisions:
            if decision.segment_id == chapter_id:
                return decision
        return None

    def _preview_row_data(self, row: int):
        chapter = self._chapter_for_row(row)
        if chapter is None:
            return
        self._preview_row = row
        edit = self._user_edits.get(chapter.chapter_id, {})
        decision = self._decision_for_row(row)
        edl_segment = self._edl_for_row(row)
        title = edit.get("title") or chapter.title or chapter.chapter_id
        midpoint = (chapter.start + chapter.end) / 2.0
        self.preview_thumb_lbl.setText(f"{fmt_time(midpoint)}")
        self.preview_title_lbl.setText(title)
        self.preview_time_lbl.setText(f"{fmt_time(chapter.start)} - {fmt_time(chapter.end)}")
        self.preview_summary_lbl.setText(chapter.summary or "요약 없음")
        action = decision.action if decision else "-"
        safety = decision.safety if decision else "-"
        role = chapter.story_role or "-"
        if decision is not None and decision.source_start is not None and decision.source_end is not None:
            trim = f"{fmt_time(decision.source_start)}-{fmt_time(decision.source_end)}"
        elif edl_segment is not None:
            trim = f"{fmt_time(edl_segment.source_start)}-{fmt_time(edl_segment.source_end)}"
        else:
            trim = "-"
        reason = decision.reason if decision and decision.reason else chapter.story_reason or "컷 근거 없음"
        output = (
            f" / 출력 {fmt_time(edl_segment.output_start)}-{fmt_time(edl_segment.output_end)}"
            if edl_segment is not None
            else ""
        )
        self.preview_action_lbl.setText(f"판단: {action}")
        self.preview_safety_lbl.setText(f"안전: {safety}")
        self.preview_trim_lbl.setText(f"Trim: {trim}")
        self.preview_role_lbl.setText(f"Role: {role}")
        self.preview_source_lbl.setText(f"Clip: {self._source_label_for_edl(edl_segment)}")
        self.preview_safety_lbl.setStyleSheet(self._safety_badge_style(safety))
        self.preview_reason_lbl.setText(f"{self._format_safety_reason(reason)}{output}")
        self._update_detail_panel(row, chapter, decision, edl_segment)
        if hasattr(self, "major_panel"):
            self.major_panel.set_selected_chapter(chapter.chapter_id)

    def _source_label_for_edl(self, edl_segment) -> str:
        if edl_segment is None:
            return "-"
        name = os.path.basename(str(getattr(edl_segment, "source_path", "") or ""))
        clip_index = getattr(edl_segment, "clip_index", None)
        if clip_index is not None:
            clip_no = int(clip_index) + 1
            return f"{clip_no} / {name or 'clip'}"
        return name or "단일"

    def _apply_safety_filter(self) -> None:
        if self._result is None or not hasattr(self, "table"):
            return
        selected = "전체"
        if hasattr(self, "safety_filter_combo"):
            selected = self.safety_filter_combo.currentText() or "전체"
        decisions = {decision.segment_id: decision for decision in self._result.edit_decisions}
        first_visible = -1
        for row, chapter_id in enumerate(self._row_chapter_ids):
            decision = decisions.get(chapter_id)
            safety = decision.safety if decision is not None else ""
            hidden = selected != "전체" and safety != selected
            self.table.setRowHidden(row, hidden)
            if not hidden and first_visible < 0:
                first_visible = row
        current_row = self.table.currentRow()
        if first_visible >= 0 and (current_row < 0 or self.table.isRowHidden(current_row)):
            self.table.selectRow(first_visible)
            self._preview_row_data(first_visible)

    def _safety_badge_style(self, safety: str) -> str:
        color = "#DCE3EA"
        border = "#2D3942"
        if safety == "risky":
            color = "#FFB1AB"
            border = "#5B2528"
        elif safety == "ideal":
            color = "#9AF0B0"
            border = "#2B5A3A"
        elif safety == "acceptable":
            color = "#FFD68A"
            border = "#6A4B18"
        return (
            "QLabel { background: #10161A; "
            f"color: {color}; border: 1px solid {border}; "
            "border-radius: 6px; padding: 4px 6px; font-size: 10px; font-weight: 800; }"
        )
