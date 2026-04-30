# Version: 03.01.32
# Phase: PHASE2
import unittest
from pathlib import Path
import tempfile

from core.roughcut import (
    ChapterMetadata,
    RoughCutMinorGroup,
    RoughCutSegment,
    build_concat_render_plan,
    build_edit_decisions,
    build_edl_segments,
    build_markdown_guide,
    edl_to_dict,
    retime_subtitles_for_edl,
    run_render_plan,
)


class RoughcutV2OutputCompatTests(unittest.TestCase):
    def _v2_fixture(self):
        chapters = [
            ChapterMetadata(
                "chapter_0001",
                "외부",
                0.0,
                4.0,
                tags=("외부",),
                major_id="A",
                minor_code="A1",
                confidence=0.91,
                boundary_status="confirmed",
            ),
            ChapterMetadata(
                "chapter_0002",
                "실내",
                5.0,
                8.0,
                tags=("실내",),
                major_id="B",
                minor_code="B1",
                confidence=0.82,
                boundary_status="provisional",
            ),
        ]
        majors = [
            RoughCutSegment(
                "major_A",
                0.0,
                4.0,
                major_id="A",
                title="외부 리뷰",
                summary="외부 구간",
                tags=("외부",),
                minor_groups=(RoughCutMinorGroup("A1", "A", "A1", "외부", 0.0, 4.0, chapter_ids=("chapter_0001",)),),
            ),
            RoughCutSegment(
                "major_B",
                5.0,
                8.0,
                major_id="B",
                title="실내 리뷰",
                summary="실내 구간",
                tags=("실내",),
                minor_groups=(RoughCutMinorGroup("B1", "B", "B1", "실내", 5.0, 8.0, chapter_ids=("chapter_0002",)),),
            ),
        ]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = build_edl_segments(r"C:\Videos With Space\source.mp4", decisions, chapters)
        return chapters, majors, decisions, edl

    def test_edl_keeps_v1_fields_and_adds_v2_metadata(self):
        chapters, majors, _decisions, edl = self._v2_fixture()

        payload = edl_to_dict(edl, metadata={"source": "demo"}, chapters=chapters, major_segments=majors)

        self.assertEqual(payload["schema"], "ai_subtitle_studio.roughcut.edl.v1")
        self.assertIn("segments", payload)
        self.assertIn("source_start", payload["segments"][0])
        self.assertEqual(payload["metadata"]["roughcut_v2"]["major_segment_count"], 2)
        self.assertEqual(payload["segments"][0]["metadata"]["major_id"], "A")
        self.assertEqual(payload["segments"][0]["metadata"]["minor_code"], "A1")
        self.assertEqual(payload["segments"][0]["metadata"]["major"]["title"], "외부 리뷰")

    def test_guide_and_retimed_srt_keep_existing_output_with_v2_metadata(self):
        chapters, _majors, decisions, edl = self._v2_fixture()

        guide = build_markdown_guide(chapters, decisions, edl)
        retimed = retime_subtitles_for_edl(
            [{"id": 1, "start": 0.5, "end": 2.0, "text": "외부 설명"}],
            edl,
            chapters=chapters,
        )

        self.assertIn("## 중분류 / 소분류", guide)
        self.assertIn("| A | A1 | `chapter_0001`", guide)
        self.assertEqual(retimed[0]["roughcut_metadata"]["major_id"], "A")
        self.assertEqual(retimed[0]["roughcut_metadata"]["minor_code"], "A1")
        self.assertEqual(retimed[0]["text"], "외부 설명")

    def test_render_plan_and_dry_run_expose_segment_manifest(self):
        _chapters, _majors, _decisions, edl = self._v2_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            plan = build_concat_render_plan(edl, Path(tmp) / "out.mp4", Path(tmp) / "parts")
            result = run_render_plan(plan, dry_run=True)

        self.assertEqual(len(plan.segment_manifest), len(edl))
        self.assertEqual(plan.segment_manifest[0]["chapter_id"], "chapter_0001")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.segment_manifest[0]["segment_id"], "chapter_0001")


if __name__ == "__main__":
    unittest.main()
