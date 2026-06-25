# Version: 03.01.32
# Phase: PHASE2
import unittest
from pathlib import Path
import tempfile

from core.project.nle_snapshot import (
    build_concat_render_plan_from_snapshot,
    build_project_nle_snapshot,
    edl_segments_from_render_plan_snapshot,
)
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
        self.assertEqual([row["timeline_sec"] for row in payload["stitched_cut_boundaries"]], [4.0])
        self.assertEqual(payload["stitched_cut_boundaries"][0]["segment_before_id"], "chapter_0001")
        self.assertEqual(payload["stitched_cut_boundaries"][0]["segment_after_id"], "chapter_0002")
        self.assertEqual(payload["stitched_cut_boundaries"][0]["timeline_before_end"], 4.0)
        self.assertEqual(payload["stitched_cut_boundaries"][0]["timeline_after_start"], 5.0)

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
        self.assertEqual([row["timeline_sec"] for row in plan.stitched_cut_boundaries], [4.0])
        self.assertTrue(result.dry_run)
        self.assertEqual(result.segment_manifest[0]["segment_id"], "chapter_0001")
        self.assertEqual([row["timeline_sec"] for row in result.stitched_cut_boundaries], [4.0])

    def test_nle_snapshot_render_plan_matches_legacy_concat_builder(self):
        chapters, majors, _decisions, edl = self._v2_fixture()
        edl_payload = edl_to_dict(edl, metadata={"source": "demo"}, chapters=chapters, major_segments=majors)
        project = {
            "project_name": "nle_render_parity",
            "video": {"duration_sec": edl_payload["duration"], "primary_fps": 30.0},
            "roughcut_state": {
                "selected_candidate_id": "roughcut_a",
                "candidates": [
                    {
                        "candidate_id": "roughcut_a",
                        "name": "roughcut A",
                        "outputs": {
                            "edl": edl_payload,
                            "render_plan": {
                                "render_mode": "sync_safe",
                                "stitched_cut_boundaries": edl_payload["stitched_cut_boundaries"],
                            },
                        },
                    }
                ],
            },
        }
        snapshot = build_project_nle_snapshot(project)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.mp4"
            temp_dir = Path(tmp) / "parts"
            legacy_plan = build_concat_render_plan(edl, output, temp_dir, render_mode="sync_safe")
            nle_plan = build_concat_render_plan_from_snapshot(
                snapshot,
                str(output),
                str(temp_dir),
                render_mode="sync_safe",
            )

        self.assertEqual(edl_segments_from_render_plan_snapshot(snapshot), tuple(edl))
        self.assertEqual(snapshot.render_plans[0].output_duration, edl_payload["duration"])
        self.assertEqual(nle_plan.extract_commands, legacy_plan.extract_commands)
        self.assertEqual(nle_plan.concat_command, legacy_plan.concat_command)
        self.assertEqual(nle_plan.segment_manifest, legacy_plan.segment_manifest)
        self.assertEqual(nle_plan.stitched_cut_boundaries, legacy_plan.stitched_cut_boundaries)


if __name__ == "__main__":
    unittest.main()
