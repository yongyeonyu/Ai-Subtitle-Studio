# Version: 03.01.31
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

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

            self.assertEqual(widget.main_tabs.count(), 2)
            self.assertGreaterEqual(widget.bottom_tabs.tabs.count(), 6)
            self.assertEqual(widget.table.rowCount(), 1)
            self.assertIn("chapter_0001", widget.major_panel._minor_buttons)
            self.assertEqual(widget.title_panel._suggestions[0].title, "EV6 외부 디자인 총정리")
            self.assertIn("분석 완료", widget.log_panel.status_lbl.text())
            self.assertIn("chapter_0001", widget.bottom_tabs.edl_text.toPlainText())

            widget.style_panel.set_style({"transition": "fade", "font_size": 50})
            widget._save_roughcut_export_style(widget.style_panel.style_payload())
            payload = widget._current_candidate_payload(widget._result)
            self.assertEqual(payload["roughcut_export_style"]["transition"], "fade")
            self.assertEqual(payload["roughcut_export_style"]["font_size"], 50)
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
