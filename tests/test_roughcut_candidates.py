# Version: 03.01.28
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.roughcut.models import ChapterMetadata, EDLSegment, EditDecision, RoughCutResult, RoughCutSegment
from ui.roughcut.roughcut_widget import RoughcutWidget


def _result(title: str) -> RoughCutResult:
    return RoughCutResult(
        segments=(RoughCutSegment("chapter_0001", 0.0, 3.0, title=title),),
        chapters=(ChapterMetadata("chapter_0001", title, 0.0, 3.0, summary=title),),
        edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=3.0),),
        edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 3.0, 0.0, 3.0),),
        guide_markdown=f"# {title}",
        schema_version="roughcut_result.v2",
    )


class RoughcutCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_payload_keeps_multiple_candidates_and_selected_candidate(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-a"
            widget._result = _result("첫 후보")
            first = widget._roughcut_state_payload()
            first_id = first["selected_candidate_id"]

            widget._selected_candidate_id = ""
            widget._source_signature = "sig-b"
            widget._result = _result("둘째 후보")
            second = widget._roughcut_state_payload()

            self.assertEqual(second["schema"], "ai_subtitle_studio.roughcut_state.v2")
            self.assertEqual(second["candidates"][0]["schema"], "ai_subtitle_studio.roughcut_candidate.v2")
            self.assertIn("settings", second)
            self.assertEqual(second["candidate_count"], 2)
            self.assertNotEqual(second["selected_candidate_id"], first_id)
            self.assertEqual(second["chapters"][0]["title"], "둘째 후보")
            self.assertTrue(second["candidates"][0]["outputs"]["guide_markdown"])

            widget._apply_candidate_payload(second["candidates"][0], persist=False)
            self.assertEqual(widget._selected_candidate_id, first_id)
            self.assertEqual(widget._result.chapters[0].title, "첫 후보")
            self.assertEqual(widget._result.schema_version, "roughcut_result.v2")
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
