# Version: 03.09.11
# Phase: PHASE2
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QListView, QWidget

from core.roughcut.models import (
    ChapterMetadata,
    EDLSegment,
    EditDecision,
    RoughCutMinorGroup,
    RoughCutResult,
    RoughCutSegment,
    RoughCutTitleSuggestion,
)
from ui.roughcut.roughcut_widget import RoughcutWidget
from ui.settings.settings_gap import GapSettingsDialog
from ui.settings.settings_advanced import AdvancedSettingsDialog
from ui.settings.settings_ai import SettingsDialog
from ui.editor.editor_project_open_native import load_stitched_cut_boundaries_for_srt_open


class RoughcutUiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_major_log_and_title_panels_render_without_removing_legacy_table(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="차량 외부 리뷰",
                        major_id="A",
                        tags=("외부", "타이어"),
                        minor_groups=(
                            RoughCutMinorGroup(
                                "A1",
                                "A",
                                "A1",
                                "외부 디자인",
                                0.0,
                                4.0,
                                chapter_ids=("chapter_0001",),
                                confidence=0.9,
                                status="confirmed",
                            ),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                title_suggestions=(
                    RoughCutTitleSuggestion("title_001", "EV6 외부 디자인 총정리", 0.9, expected_reach="높음"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()

            self.assertTrue(hasattr(widget, "roughcut_frame"))
            self.assertEqual(widget.bottom_tabs.tabs.count(), 4)
            self.assertEqual(
                [widget.bottom_tabs.tabs.tabText(index) for index in range(widget.bottom_tabs.tabs.count())],
                ["챕터", "자막 세그먼트", "EDL", "로그"],
            )
            self.assertEqual(widget.table.rowCount(), 1)
            self.assertIn("chapter_0001", widget.major_panel._minor_buttons)
            self.assertEqual(widget.major_panel.summary_lbl.text(), "LLM 카드 1 / 세그먼트 1 / 검토 0")
            self.assertEqual(widget.major_panel.selection_lbl.text(), "선택 chapter_0001")
            self.assertIn("썸네일", widget.major_panel._preview_buttons["chapter_0001"].text())
            self.assertEqual(widget.major_panel.card_list.flow(), QListView.Flow.LeftToRight)
            self.assertEqual(widget.player_menu_frame.layout().itemAt(0).widget().text(), "핵심 메뉴")
            self.assertEqual(widget.player_core_section.toggle.text(), "AI 작업")
            self.assertFalse(widget.player_core_section.content.isVisible())
            self.assertEqual(widget.player_media_group.layout().itemAt(0).widget().text(), "재생")
            self.assertEqual(widget.player_export_section.toggle.text(), "내보내기")
            self.assertFalse(widget.player_export_section.content.isVisible())
            self.assertEqual(widget.export_menu_btn.text(), "내보내기")
            self.assertEqual(widget.bottom_tabs.section_title_lbl.text(), "보조 참조")
            self.assertFalse(widget.selection_status_section.content.isVisible())
            self.assertEqual(widget.title_panel._suggestions[0].title, "EV6 외부 디자인 총정리")
            self.assertIn("분석 완료", widget.log_panel.status_lbl.text())
            self.assertIn("chapter_0001", widget.bottom_tabs.edl_text.toPlainText())
            self.assertEqual(widget.filter_summary_lbl.text(), "표시 1 / 전체 1")
            self.assertEqual(widget.candidate_state_lbl.text(), "후보 없음")
            self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
            self.assertEqual(widget.player_order_lbl.text(), "카드 1/1 · major_A")
            self.assertEqual(widget.player_context_summary_lbl.text(), "후보 없음 · 표시 1 / 전체 1")
            self.assertEqual(widget.player_focus_summary_lbl.text(), "카드 1/1 · major_A · 선택 chapter_0001 · 확정")
            self.assertEqual(widget.player_reorder_summary_visible_lbl.text(), "재정렬 없음")
            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 자동 초안")
            self.assertFalse(widget.btn_revert_user_edit.isEnabled())
            self.assertEqual(widget.detail_delta_lbl.text(), "Δ In +0.00s / Δ Out +0.00s")
            self.assertEqual(widget.candidate_preview_filter_combo.count(), 2)
            self.assertEqual(widget.candidate_preview_filter_combo.itemText(0), "전체 후보")
            self.assertEqual(widget.candidate_preview_filter_combo.itemText(1), "LLM 결과만")

            widget.style_panel.set_style({"transition": "fade", "font_size": 50})
            widget._save_roughcut_export_style(widget.style_panel.style_payload())
            payload = widget._current_candidate_payload(widget._result)
            self.assertEqual(payload["roughcut_export_style"]["transition"], "fade")
            self.assertEqual(payload["roughcut_export_style"]["font_size"], 50)

            widget.cut_trim_start_spin.setValue(0.5)
            widget.cut_trim_end_spin.setValue(3.5)
            self.assertEqual(widget.detail_delta_lbl.text(), "Δ In +0.50s / Δ Out -0.50s")
            self.assertIn("#34C759", widget.detail_delta_lbl.styleSheet())
        finally:
            widget.close()

    def test_thumbnail_lookup_for_result_uses_cached_chapter_frames(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._media_path = lambda: "/tmp/source.mp4"
            widget._project_path = lambda: "/tmp/test.aissproj"
            with patch("ui.roughcut.roughcut_widget.ensure_thumbnail") as ensure_thumbnail:
                ensure_thumbnail.return_value = SimpleNamespace(status="cached", path="/tmp/thumb.png", reason="")
                lookup = widget._thumbnail_lookup_for_result(widget._result)
                self.assertEqual(lookup["chapter_0001"], "/tmp/thumb.png")
                ensure_thumbnail.assert_called_once()
                second = widget._thumbnail_lookup_for_result(widget._result)
                self.assertEqual(second["chapter_0001"], "/tmp/thumb.png")
                ensure_thumbnail.assert_called_once()
        finally:
            widget.close()

    def test_minor_card_shows_subtitle_segment_count_and_snippet(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(
                result,
                editor_segments=[
                    {"start": 0.0, "end": 1.8, "text": "첫 번째 자막 세그먼트"},
                    {"start": 1.8, "end": 3.9, "text": "두 번째 자막 세그먼트"},
                ],
            )

            minor_list = widget.major_panel._minor_lists["major_A"]
            row_widget = minor_list.itemWidget(minor_list.item(0))
            badge = row_widget.findChild(QLabel, "roughcutSubtitleCountBadge")
            snippet = row_widget.findChild(QLabel, "roughcutSubtitleSnippetLabel")

            self.assertIsNotNone(badge)
            self.assertIsNotNone(snippet)
            self.assertEqual(badge.text(), "자막 2")
            self.assertIn("첫 번째 자막 세그먼트", snippet.text())
        finally:
            widget.close()

    def test_thumbnail_button_emits_preview_request_for_minor_row(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            events: list[tuple[str, bool]] = []
            widget.major_panel.previewRequested.connect(lambda chapter_id, hover: events.append((chapter_id, hover)))

            button = widget.major_panel._preview_buttons["chapter_0001"]
            button.click()

            self.assertEqual(events, [("chapter_0001", False)])
            self.assertEqual(button.objectName(), "roughcutMinorThumbnailButton")
            self.assertGreaterEqual(button.width(), 56)
            self.assertGreaterEqual(button.height(), 28)
        finally:
            widget.close()

    def test_drag_handles_exist_for_major_and_minor_cards(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_handle = major_card.findChild(QLabel, "roughcutMajorDragHandle")
            self.assertIsNotNone(major_handle)
            self.assertIn("순서 변경", major_handle.toolTip())

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_handle = minor_row.findChild(QLabel, "roughcutMinorDragHandle")
            self.assertIsNotNone(minor_handle)
            self.assertIn("순서 변경", minor_handle.toolTip())
        finally:
            widget.close()

    def test_drag_surfaces_emit_major_and_minor_reorder_requests(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_surface = major_card if major_card.objectName() == "roughcutMajorCardSurface" else major_card.findChild(QWidget, "roughcutMajorCardSurface")
            major_calls: list[tuple[str, int]] = []
            original_major = widget.major_panel._move_segment_by_drag_delta
            widget.major_panel._move_segment_by_drag_delta = lambda sid, delta: major_calls.append((sid, delta))

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_surface = minor_row if minor_row.objectName() == "roughcutMinorRowSurface" else minor_row.findChild(QWidget, "roughcutMinorRowSurface")
            minor_calls: list[tuple[str, str, int]] = []
            original_minor = widget.major_panel._move_chapter_by_drag_delta
            widget.major_panel._move_chapter_by_drag_delta = lambda sid, cid, delta: minor_calls.append((sid, cid, delta))

            try:
                self.assertIsNotNone(major_surface)
                self.assertIsNotNone(minor_surface)
                major_surface.dragDelta.emit(80)
                minor_surface.dragDelta.emit(40)
            finally:
                widget.major_panel._move_segment_by_drag_delta = original_major
                widget.major_panel._move_chapter_by_drag_delta = original_minor

            self.assertEqual(major_calls, [("major_A", 80)])
            self.assertEqual(minor_calls, [("major_A", "chapter_0001", 40)])
        finally:
            widget.close()

    def test_drag_surfaces_request_native_major_and_minor_drag_start(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_surface = major_card if major_card.objectName() == "roughcutMajorCardSurface" else major_card.findChild(QWidget, "roughcutMajorCardSurface")
            major_handle = major_card.findChild(QLabel, "roughcutMajorDragHandle")

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_surface = minor_row if minor_row.objectName() == "roughcutMinorRowSurface" else minor_row.findChild(QWidget, "roughcutMinorRowSurface")
            minor_handle = minor_row.findChild(QLabel, "roughcutMinorDragHandle")

            major_calls: list[str] = []
            minor_calls: list[tuple[str, str]] = []
            original_major = widget.major_panel.card_list.start_drag_for_segment
            original_minor = widget.major_panel._start_minor_drag
            widget.major_panel.card_list.start_drag_for_segment = lambda sid: major_calls.append(sid)
            widget.major_panel._start_minor_drag = lambda sid, cid: minor_calls.append((sid, cid))
            try:
                self.assertIsNotNone(major_surface)
                self.assertIsNotNone(major_handle)
                self.assertIsNotNone(minor_surface)
                self.assertIsNotNone(minor_handle)
                major_surface.dragRequested.emit()
                major_handle.dragRequested.emit()
                minor_surface.dragRequested.emit()
                minor_handle.dragRequested.emit()
            finally:
                widget.major_panel.card_list.start_drag_for_segment = original_major
                widget.major_panel._start_minor_drag = original_minor

            self.assertEqual(major_calls, ["major_A", "major_A"])
            self.assertEqual(minor_calls, [("major_A", "chapter_0001"), ("major_A", "chapter_0001")])
        finally:
            widget.close()

    def test_unselected_major_cards_stay_compact_while_selected_card_expands(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 카드",
                        major_id="A",
                        summary="첫 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 카드",
                        major_id="B",
                        summary="둘째 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "셋째 장면", 8.0, 12.0, chapter_ids=("chapter_0003",)),
                            RoughCutMinorGroup("B2", "B", "B2", "넷째 장면", 12.0, 16.0, chapter_ids=("chapter_0004",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                    ChapterMetadata("chapter_0003", "셋째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                    ChapterMetadata("chapter_0004", "넷째 장면", 12.0, 16.0, major_id="B", minor_code="B2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                    EditDecision("chapter_0003", "keep", source_start=8.0, source_end=12.0),
                    EditDecision("chapter_0004", "keep", source_start=12.0, source_end=16.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0003", 8.0, 12.0, 8.0, 12.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0004", 12.0, 16.0, 12.0, 16.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            active = widget.major_panel._segment_cards["major_A"]
            inactive = widget.major_panel._segment_cards["major_B"]

            self.assertFalse(active["summary"].isHidden())
            self.assertTrue(inactive["summary"].isHidden())
            self.assertGreater(active["minor_list"].count(), 1)
            self.assertGreaterEqual(active["minor_list"].maximumHeight(), 58)
            self.assertGreater(active["minor_list"].maximumHeight(), inactive["minor_list"].maximumHeight())
            self.assertEqual(widget.player_order_lbl.text(), "카드 1/2 · major_A > major_B")

            widget._select_chapter_id_from_major_panel("chapter_0003")
            self.assertTrue(active["summary"].isHidden())
            self.assertFalse(inactive["summary"].isHidden())
            self.assertGreaterEqual(inactive["minor_list"].maximumHeight(), 58)
            self.assertGreater(inactive["minor_list"].maximumHeight(), active["minor_list"].maximumHeight())
            self.assertEqual(widget.player_order_lbl.text(), "카드 2/2 · major_A > major_B")
        finally:
            widget.close()

    def test_five_major_cards_keep_compact_card_budget(self):
        widget = RoughcutWidget()
        try:
            segments = []
            chapters = []
            edit_decisions = []
            edl_segments = []
            for index, major_id in enumerate(("A", "B", "C", "D", "E"), start=1):
                chapter_id = f"chapter_{index:04d}"
                start = float((index - 1) * 4)
                end = start + 4.0
                segments.append(
                    RoughCutSegment(
                        f"major_{major_id}",
                        start,
                        end,
                        title=f"{major_id} 카드",
                        major_id=major_id,
                        summary=f"{major_id} 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup(f"{major_id}1", major_id, f"{major_id}1", f"{major_id} 장면", start, end, chapter_ids=(chapter_id,)),
                        ),
                    )
                )
                chapters.append(ChapterMetadata(chapter_id, f"{major_id} 장면", start, end, major_id=major_id, minor_code=f"{major_id}1"))
                edit_decisions.append(EditDecision(chapter_id, "keep", source_start=start, source_end=end))
                edl_segments.append(EDLSegment("/tmp/source.mp4", chapter_id, start, end, start, end))

            widget._result = RoughCutResult(
                segments=tuple(segments),
                chapters=tuple(chapters),
                edit_decisions=tuple(edit_decisions),
                edl_segments=tuple(edl_segments),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()

            heights = []
            widths = []
            for segment_id in ("major_A", "major_B", "major_C", "major_D", "major_E"):
                item = widget.major_panel._segment_items[segment_id]
                heights.append(item.sizeHint().height())
                widths.append(item.sizeHint().width())
            self.assertEqual(widget.major_panel.card_list.flow(), QListView.Flow.LeftToRight)
            self.assertLessEqual(max(heights), 140)
            self.assertGreaterEqual(min(heights), 92)
            self.assertGreaterEqual(min(widths), 280)
            self.assertGreater(min(widths), max(heights))
            self.assertEqual(widget.major_panel._segment_cards["major_A"]["minor_list"].maximumHeight(), 36)
        finally:
            widget.close()

    def test_selected_major_card_expands_to_show_multiple_minor_rows(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        12.0,
                        title="첫 카드",
                        major_id="A",
                        summary="첫 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                            RoughCutMinorGroup("A3", "A", "A3", "셋째 장면", 8.0, 12.0, chapter_ids=("chapter_0003",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                    ChapterMetadata("chapter_0003", "셋째 장면", 8.0, 12.0, major_id="A", minor_code="A3"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                    EditDecision("chapter_0003", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0003", 8.0, 12.0, 8.0, 12.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()

            active = widget.major_panel._segment_cards["major_A"]
            item = widget.major_panel._segment_items["major_A"]

            self.assertGreaterEqual(active["minor_list"].maximumHeight(), 84)
            self.assertGreaterEqual(item.sizeHint().height(), 180)
            self.assertGreaterEqual(item.sizeHint().width(), 340)
        finally:
            widget.close()

    def test_major_card_reorder_updates_table_and_edl_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget._on_major_segment_order_changed(("major_B", "major_A"))

            self.assertEqual(widget._segment_order, ["major_B", "major_A"])
            self.assertEqual(widget.table.item(0, 3).text(), "둘째 장면")
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
            self.assertEqual(widget._result.edl_segments[0].chapter_id, "chapter_0002")
        finally:
            widget.close()

    def test_ordered_preview_sequence_follows_visible_row_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()
            played_rows: list[int] = []

            def _fake_play(row, muted=False, hover=False, update_preview_data=True):
                played_rows.append(int(row))
                widget._preview_row = int(row)

            widget._play_preview = _fake_play
            started = widget._start_ordered_preview_sequence()
            self.assertTrue(started)
            self.assertTrue(widget._sequence_preview_active)
            self.assertEqual(played_rows, [0])

            advanced = widget._advance_ordered_preview_sequence()
            self.assertTrue(advanced)
            self.assertEqual(played_rows, [0, 1])
            self.assertEqual(widget.player_order_lbl.text(), "카드 2/2 · major_A > major_B")
        finally:
            widget.close()

    def test_automation_move_selected_segment_updates_segment_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget.automation_select_chapter(chapter_id="chapter_0002")
            result = widget.automation_move_selected_segment(-1)

            self.assertTrue(result["changed"])
            self.assertEqual(result["selected_segment_id"], "major_B")
            self.assertEqual(result["segment_order"], ["major_B", "major_A"])
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
        finally:
            widget.close()

    def test_minor_card_reorder_updates_chapter_and_edl_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget._on_major_chapter_order_changed(("chapter_0002", "chapter_0001"))

            self.assertEqual(widget._chapter_order, ["chapter_0002", "chapter_0001"])
            self.assertEqual(widget.table.item(0, 3).text(), "둘째 장면")
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
            self.assertEqual(widget._result.edl_segments[0].chapter_id, "chapter_0002")
            self.assertEqual(widget.reorder_summary_lbl.text(), "챕터 재정렬 · chapter_0002 > chapter_0001")
            self.assertEqual(widget.player_reorder_lbl.text(), "챕터 재정렬 · chapter_0002 > chapter_0001")
        finally:
            widget.close()

    def test_minor_card_reorder_changes_exported_srt_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
            ]
            widget._populate_result()
            widget._on_major_chapter_order_changed(("chapter_0002", "chapter_0001"))

            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "roughcut_reordered.srt")
                result = widget.export_roughcut_srt_to_path(path)
                self.assertTrue(os.path.exists(result["path"]))
                text = open(path, "r", encoding="utf-8").read()

            self.assertLess(text.find("둘째 자막"), text.find("첫 자막"))
        finally:
            widget.close()

    def test_major_card_reorder_changes_exported_srt_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        4.0,
                        title="첫 카드",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 카드", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        4.0,
                        8.0,
                        title="둘째 카드",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 카드", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 카드", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 카드", 4.0, 8.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 카드 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 카드 자막", "speaker": "00"},
            ]
            widget._populate_result()
            widget.automation_select_chapter(chapter_id="chapter_0002")
            widget.automation_move_selected_segment(-1)

            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "roughcut_segment_reordered.srt")
                result = widget.export_roughcut_srt_to_path(path)
                self.assertTrue(os.path.exists(result["path"]))
                text = open(path, "r", encoding="utf-8").read()

            self.assertLess(text.find("둘째 카드 자막"), text.find("첫 카드 자막"))
        finally:
            widget.close()

    def test_exported_roughcut_srt_writes_exact_join_sidecars_for_reopen(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
            ]

            with tempfile.TemporaryDirectory() as tmp:
                target = os.path.join(tmp, "clip_roughcut.srt")
                export = widget.export_roughcut_srt_to_path(target)
                render_plan_path = Path(export["render_plan_path"])
                edl_path = Path(export["edl_path"])
                export_exists = os.path.exists(export["path"])
                render_plan_exists = render_plan_path.exists()
                edl_exists = edl_path.exists()
                render_payload = json.loads(render_plan_path.read_text(encoding="utf-8"))
                edl_payload = json.loads(edl_path.read_text(encoding="utf-8"))
                stitched_rows, stitched_sidecar_path = load_stitched_cut_boundaries_for_srt_open(target)

            self.assertTrue(export_exists)
            self.assertEqual(export["stitched_cut_boundary_count"], 1)
            self.assertTrue(render_plan_exists)
            self.assertTrue(edl_exists)
            self.assertEqual(render_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(render_payload["render_plan"]["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(edl_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual([row["timeline_sec"] for row in stitched_rows], [4.0])
            self.assertEqual(Path(stitched_sidecar_path).name, "clip_roughcut_edl.json")
        finally:
            widget.close()

    def test_rendered_roughcut_video_writes_exact_join_sidecars_for_reopen(self):
        widget = RoughcutWidget()
        try:
            widget._active_editor = lambda: SimpleNamespace(media_path="/tmp/source.mov")
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "clip_roughcut.mov"
                plan = widget._build_render_plan_for_srt_target(output.with_suffix(".srt"), widget._result)
                sidecars = widget._write_exact_join_sidecars_for_rendered_video(output, plan, widget._result)
                render_plan_path = Path(sidecars["render_plan_path"])
                edl_path = Path(sidecars["edl_path"])
                render_plan_exists = render_plan_path.exists()
                edl_exists = edl_path.exists()
                render_payload = json.loads(render_plan_path.read_text(encoding="utf-8"))
                edl_payload = json.loads(edl_path.read_text(encoding="utf-8"))
                stitched_rows, stitched_sidecar_path = load_stitched_cut_boundaries_for_srt_open(
                    str(output.with_suffix(".srt")),
                    str(output),
                )

            self.assertEqual(sidecars["stitched_cut_boundary_count"], 1)
            self.assertTrue(render_plan_exists)
            self.assertTrue(edl_exists)
            self.assertEqual(render_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(edl_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual([row["timeline_sec"] for row in stitched_rows], [4.0])
            self.assertEqual(Path(stitched_sidecar_path).name, "clip_roughcut_edl.json")
        finally:
            widget.close()

    def test_attach_and_release_editor_video_frame_uses_external_host(self):
        widget = RoughcutWidget()
        frame = QWidget()

        class _FakeVideoPlayer:
            def restore_after_navigation(self):
                return None

        class _FakeEditor:
            def __init__(self, owned_frame):
                self._owned_frame = owned_frame
                self.video_player = _FakeVideoPlayer()
                self.detached = 0
                self.restored = 0

            def detach_video_frame_for_external_host(self):
                self.detached += 1
                return self._owned_frame

            def restore_video_frame_from_external_host(self, restored_frame=None):
                self.restored += 1
                self._owned_frame = restored_frame or self._owned_frame

        editor = _FakeEditor(frame)
        try:
            self.assertTrue(widget.attach_editor_video_frame(editor))
            self.assertEqual(widget._attached_video_editor, editor)
            self.assertEqual(widget._attached_video_frame, frame)
            self.assertEqual(widget.video_host_layout.indexOf(frame), 0)
            self.assertFalse(widget.video_host_placeholder.isVisible())
            widget.release_editor_video_frame()
            self.assertEqual(editor.restored, 1)
            self.assertIsNone(widget._attached_video_editor)
            self.assertIsNone(widget._attached_video_frame)
            self.assertGreaterEqual(widget.video_host_layout.indexOf(widget.video_host_placeholder), 0)
        finally:
            widget.close()

    def test_detail_panel_surfaces_user_edit_summary(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._user_edits = {
                "chapter_0001": {
                    "title": "외관 오프닝",
                    "trim_start": 0.2,
                    "trim_end": 3.8,
                    "status": "사용자 수정됨",
                }
            }

            widget._populate_result()

            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 사용자 수정됨 · 제목 / 컷 조정")
            self.assertIn("#FFD60A", widget.detail_edit_state_lbl.styleSheet())
            self.assertTrue(widget.btn_revert_user_edit.isEnabled())
        finally:
            widget.close()

    def test_revert_button_restores_auto_draft_state(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._user_edits = {
                "chapter_0001": {
                    "title": "외관 오프닝",
                    "trim_start": 0.2,
                    "trim_end": 3.8,
                    "status": "사용자 수정됨",
                }
            }

            widget._populate_result()
            widget._revert_user_edit()

            self.assertEqual(widget._user_edits, {})
            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 자동 초안")
            self.assertFalse(widget.btn_revert_user_edit.isEnabled())
        finally:
            widget.close()

    def test_candidate_state_and_filter_badges_follow_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment("major_A", 0.0, 8.0, title="첫 장면", major_id="A"),
                    RoughCutSegment("major_B", 8.0, 16.0, title="둘째 장면", major_id="B"),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "trim", safety="risky", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            current["candidate_id"] = "candidate_current"
            current["source_signature"] = "sig-current"
            current["name"] = "현재 후보"

            previous = dict(current)
            previous["candidate_id"] = "candidate_old"
            previous["source_signature"] = "sig-previous"
            previous["name"] = "이전 후보"

            widget._roughcut_candidates = [previous, current]
            widget._selected_candidate_id = "candidate_current"
            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._populate_result()
                widget._refresh_candidate_combo()

                self.assertEqual(widget.candidate_state_lbl.text(), "현재 자막 기준")
                self.assertEqual(widget.filter_summary_lbl.text(), "표시 2 / 전체 2")
                self.assertEqual(widget.major_panel.summary_lbl.text(), "LLM 카드 2 / 세그먼트 0 / 검토 0")
                self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
                self.assertFalse(widget.candidate_combo.isVisible())
                self.assertEqual(len(widget._candidate_preview_buttons), 2)
                self.assertIn("현재 후보", widget._candidate_preview_buttons[1].text())
                self.assertIn("major_A", widget._candidate_preview_buttons[0].text())
                self.assertLess(widget._candidate_preview_buttons[0].maximumWidth(), widget._candidate_preview_buttons[0].minimumHeight())
                self.assertLessEqual(widget._candidate_preview_buttons[0].maximumWidth(), 142)
                self.assertGreaterEqual(widget._candidate_preview_buttons[0].minimumHeight(), 300)

                widget.safety_filter_combo.setCurrentText("risky")
                self.assertEqual(widget.filter_summary_lbl.text(), "표시 1 / 전체 2")
                self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0002 · 검토 필요")

                widget._apply_candidate_payload(previous, persist=False)
                self.assertEqual(widget.candidate_state_lbl.text(), "저장된 자막 기준")
        finally:
            widget.close()

    def test_candidate_preview_frames_limit_to_three_and_apply_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            candidates = []
            for index, title in enumerate(("첫 후보", "둘째 후보", "셋째 후보", "넷째 후보"), start=1):
                candidate = dict(current)
                candidate["candidate_id"] = f"candidate_{index}"
                candidate["name"] = title
                candidate["source_signature"] = "sig-current" if index == 1 else f"sig-{index}"
                candidate["segments"] = [{
                    "segment_id": f"major_{index}",
                    "major_id": chr(64 + index),
                    "title": title,
                    "start": 0.0,
                    "end": 3.0,
                    "minor_groups": (),
                    "tags": (),
                }]
                candidate["chapters"] = [{
                    "chapter_id": f"chapter_{index:04d}",
                    "title": title,
                    "summary": title,
                    "start": 0.0,
                    "end": 3.0,
                    "major_id": chr(64 + index),
                    "minor_code": f"{chr(64 + index)}1",
                    "tags": (),
                }]
                candidate["edit_decisions"] = [{
                    "segment_id": f"chapter_{index:04d}",
                    "action": "keep",
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "safety": "ideal",
                }]
                candidate["edl_segments"] = [{
                    "source_path": "/tmp/source.mp4",
                    "segment_id": f"chapter_{index:04d}",
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "output_start": 0.0,
                    "output_end": 3.0,
                    "action": "keep",
                    "chapter_id": f"chapter_{index:04d}",
                    "clip_index": 0,
                }]
                candidates.append(candidate)
            widget._roughcut_candidates = candidates
            widget._selected_candidate_id = "candidate_1"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                self.assertEqual(len(widget._candidate_preview_buttons), 3)
                self.assertNotIn("넷째 후보", "\n".join(button.text() for button in widget._candidate_preview_buttons))
                self.assertLess(widget._candidate_preview_buttons[0].maximumWidth(), widget._candidate_preview_buttons[0].minimumHeight())
                self.assertLessEqual(widget._candidate_preview_buttons[0].maximumWidth(), 142)
                self.assertGreaterEqual(widget._candidate_preview_buttons[0].minimumHeight(), 300)
                widget._on_candidate_frame_clicked("candidate_2")
                self.assertEqual(widget._selected_candidate_id, "candidate_2")
        finally:
            widget.close()

    def test_candidate_preview_toggle_applies_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            current["candidate_id"] = "candidate_1"
            current["name"] = "첫 후보"
            current["source_signature"] = "sig-current"
            previous = dict(current)
            previous["candidate_id"] = "candidate_2"
            previous["name"] = "둘째 후보"
            previous["source_signature"] = "sig-previous"
            widget._roughcut_candidates = [current, previous]
            widget._selected_candidate_id = "candidate_1"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                widget._candidate_preview_buttons[1].setChecked(True)
                self.assertEqual(widget._selected_candidate_id, "candidate_2")
                self.assertEqual(widget.candidate_state_lbl.text(), "저장된 자막 기준")
        finally:
            widget.close()

    def test_candidate_preview_filter_shows_only_llm_candidates(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            llm_candidate = widget._roughcut_state_payload()
            llm_candidate["candidate_id"] = "editor_post_generation_roughcut_draft"
            llm_candidate["name"] = "LLM 초안"
            llm_candidate["candidate_origin"] = "llm"

            local_candidate = dict(llm_candidate)
            local_candidate["candidate_id"] = "candidate_local"
            local_candidate["name"] = "로컬 초안"
            local_candidate["candidate_origin"] = "local"

            placeholder_candidate = dict(llm_candidate)
            placeholder_candidate["candidate_id"] = "cut_boundary_topicless"
            placeholder_candidate["name"] = "임시 후보"
            placeholder_candidate["candidate_origin"] = "placeholder"

            widget._roughcut_candidates = [local_candidate, llm_candidate, placeholder_candidate]
            widget._selected_candidate_id = "editor_post_generation_roughcut_draft"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                self.assertEqual(len(widget._candidate_preview_buttons), 3)
                self.assertIn("실제 LLM", widget._candidate_preview_buttons[1].text())

                widget.candidate_preview_filter_combo.setCurrentIndex(1)
                self.assertEqual(widget._candidate_preview_filter, "llm")
                self.assertEqual(len(widget._candidate_preview_buttons), 1)
                self.assertIn("LLM 초안", widget._candidate_preview_buttons[0].text())
                self.assertIn("실제 LLM", widget._candidate_preview_buttons[0].text())
        finally:
            widget.close()

    def test_settings_dialog_collects_roughcut_llm_without_plain_api_keys(self):
        dialog = SettingsDialog({
            "selected_model": "base-model",
            "selected_llm_provider": "ollama",
            "editor_roughcut_draft_enabled": True,
            "editor_roughcut_draft_prompt": "editor roughcut draft prompt",
            "llm_threads": 5,
            "subtitle_quality_enabled": True,
            "review_auto_correct_apply_threshold": 94,
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": "gpt-roughcut",
            "roughcut_llm_prompt": "roughcut prompt",
            "roughcut_llm_threads": 3,
        })
        try:
            self.assertFalse(hasattr(dialog, "tabs"))
            labels = [label.text().replace("&", "") for label in dialog.findChildren(QLabel)]
            self.assertNotIn("Mode", labels)
            self.assertNotIn("Mode:", labels)
            self.assertIsNone(dialog.combo_stt_quality_preset.parent())
            self.assertEqual(dialog.combo_stt_quality_preset.currentData(), "auto")
            collected = dialog._collect_settings()
            self.assertTrue(collected["settings_simplified_ui_enabled"])
            self.assertTrue(collected["subtitle_bundle_autopilot_enabled"])
            self.assertEqual(collected["user_prompt"], "")
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
            self.assertEqual(collected["llm_threads"], 5)
            self.assertTrue(collected["llm_threads_auto_enabled"])
            self.assertTrue(collected["llm_workers_auto_enabled"])
            self.assertFalse(collected["subtitle_quality_enabled"])
            self.assertEqual(collected["review_auto_correct_apply_threshold"], 94)
            self.assertFalse(collected["roughcut_llm_enabled"])
            self.assertFalse(collected["roughcut_llm_use_override"])
            self.assertEqual(collected["roughcut_llm_provider"], "none")
            self.assertEqual(collected["roughcut_llm_model"], "사용 안함")
            self.assertEqual(collected["roughcut_llm_prompt"], "")
            self.assertEqual(collected["roughcut_llm_threads"], 3)
            self.assertTrue(collected["roughcut_llm_threads_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_lora_enabled"])
            self.assertFalse(hasattr(dialog, "spin_roughcut_context_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_chunk_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_lookahead_rows"))
            self.assertNotIn("google_api_key", collected)
            self.assertNotIn("openai_api_key", collected)
            self.assertNotIn("huggingface_token", collected)
        finally:
            dialog.close()

    def test_collect_roughcut_llm_settings_enables_post_generation_autorun(self):
        dialog = SettingsDialog(
            {
                "selected_model": "base-model",
                "selected_llm_provider": "ollama",
                "editor_roughcut_draft_enabled": True,
            }
        )
        try:
            dialog.chk_roughcut_llm_enabled.setChecked(True)
            dialog.chk_roughcut_llm_override.setChecked(True)
            dialog._set_combo_data(dialog.combo_roughcut_llm_provider, "openai")
            dialog.input_roughcut_llm_model.setText("gpt-roughcut")

            collected = dialog._collect_roughcut_llm_settings()

            self.assertTrue(collected["roughcut_llm_enabled"])
            self.assertTrue(collected["roughcut_run_after_subtitle_generation"])
        finally:
            dialog.close()

    def test_collect_roughcut_llm_settings_disables_post_generation_autorun_when_llm_is_off(self):
        dialog = SettingsDialog(
            {
                "selected_model": "base-model",
                "selected_llm_provider": "ollama",
                "editor_roughcut_draft_enabled": True,
            }
        )
        try:
            dialog.chk_roughcut_llm_enabled.setChecked(False)
            dialog.chk_roughcut_llm_override.setChecked(False)
            dialog._set_combo_data(dialog.combo_roughcut_llm_provider, "none")
            dialog.input_roughcut_llm_model.setText("사용 안함")

            collected = dialog._collect_roughcut_llm_settings()

            self.assertFalse(collected["roughcut_llm_enabled"])
            self.assertFalse(collected["roughcut_run_after_subtitle_generation"])
        finally:
            dialog.close()

    def test_ai_tab_exposes_api_tokens_and_model_download_controls(self):
        dialog = SettingsDialog({})
        try:
            self.assertIsNotNone(dialog.findChild(QLineEdit, "GoogleApiKeyInput"))
            self.assertIsNotNone(dialog.findChild(QLineEdit, "OpenAiApiKeyInput"))
            self.assertIsNotNone(dialog.findChild(QLineEdit, "HuggingFaceTokenInput"))
            self.assertIsNotNone(dialog.findChild(QWidget, "AiModelDownloadPanel"))

            labels = {label.text() for label in dialog.findChildren(QLabel)}
            self.assertIn("Google API Key:", labels)
            self.assertIn("OpenAI API Key:", labels)
            self.assertIn("Hugging Face Token:", labels)
            self.assertIn("모델 관리:", labels)
            self.assertIn("설치 가능한 LLM:", labels)
            self.assertIn("필수/STT 모델:", labels)
            self.assertNotIn("STT1 Whisper 모델:", labels)
            self.assertNotIn("자막 품질 검사:", labels)
            self.assertNotIn("텍스트 LoRA 보조:", labels)
        finally:
            dialog.close()

    def test_settings_dialog_hides_manual_llm_thread_control(self):
        dialog = SettingsDialog({"llm_workers": 6})
        try:
            self.assertFalse(hasattr(dialog, "spin_editor_llm_threads"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["llm_threads_auto_enabled"])
        finally:
            dialog.close()

    def test_auto_settings_mode_uses_same_quality_presets_and_syncs_auto_scopes(self):
        with patch(
            "ui.settings.settings_ai.load_path_settings",
            return_value={
                "auto_start_mode": "quality",
                "icloud_stt_quality_preset": "fast",
                "nas_stt_quality_preset": "balanced",
            },
        ), patch("ui.settings.settings_ai.save_path_settings") as save_mock:
            dialog = SettingsDialog({})
            try:
                labels = [dialog.combo_auto_start_mode.itemText(i) for i in range(dialog.combo_auto_start_mode.count())]
                values = [dialog.combo_auto_start_mode.itemData(i) for i in range(dialog.combo_auto_start_mode.count())]
                self.assertEqual(labels, ["Fast", "Auto", "High", "STT"])
                self.assertEqual(values, ["fast", "balanced", "precise", "stt"])
                self.assertEqual(dialog.combo_auto_start_mode.currentData(), "precise")

                self.assertFalse(hasattr(dialog, "combo_simple_operation_mode"))
                collected = dialog._collect_settings()

                self.assertEqual(collected["auto_start_mode"], "balanced")
                self.assertEqual(collected["simple_operation_mode"], "auto")
                self.assertFalse(collected["operation_mode_choices_visible"])
                saved = save_mock.call_args.args[0]
                self.assertEqual(saved["auto_start_mode"], "balanced")
                self.assertEqual(saved["icloud_stt_quality_preset"], "fast")
                self.assertEqual(saved["nas_stt_quality_preset"], "balanced")
            finally:
                dialog.close()

    def test_gap_dialog_hides_manual_sliders_behind_simple_mode(self):
        dialog = GapSettingsDialog({"settings_simplified_ui_enabled": True, "simple_operation_mode": "precise"})
        try:
            self.assertFalse(hasattr(dialog, "chk_show_manual_gap_settings"))
            self.assertFalse(dialog._manual_gap_scroll_area.isHidden())
            dialog._collect_data()
            self.assertIn("continuous_threshold", dialog.result)
            self.assertIn("split_length_threshold", dialog.result)
        finally:
            dialog.close()

    def test_fast_preset_disables_editor_roughcut_draft_option(self):
        dialog = SettingsDialog({"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"})
        try:
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
        finally:
            dialog.close()

    def test_advanced_settings_no_longer_shows_llm_prompt_or_quality_tabs(self):
        dialog = AdvancedSettingsDialog({})
        try:
            tab_names = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
            self.assertIn("시스템", tab_names)
            self.assertNotIn("Silero", tab_names)
            self.assertNotIn("DeepFilter", tab_names)
            self.assertNotIn("Whisper", tab_names)
            self.assertNotIn("ffmpeg", tab_names)
            self.assertNotIn("LLM 프롬프트", tab_names)
            self.assertNotIn("자막 품질", tab_names)
            self.assertFalse(hasattr(dialog, "edit_user_prompt"))
            self.assertFalse(hasattr(dialog, "chk_subtitle_quality_enabled"))
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
