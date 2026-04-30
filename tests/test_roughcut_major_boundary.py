# Version: 03.01.29
# Phase: PHASE2
import unittest

from core.roughcut import (
    ChapterMetadata,
    PackedPhrase,
    SceneChange,
    SubtitleSegment,
    build_major_roughcut_segments,
    refine_major_boundaries,
    run_roughcut_pipeline,
    verify_major_boundary,
)
from core.roughcut.gap_detector import TimelineGap


class RoughCutMajorBoundaryTests(unittest.TestCase):
    def test_major_segmenter_assigns_major_and_minor_codes(self):
        chapters = [
            ChapterMetadata("chapter_0001", "외부", 0.0, 4.0, tags=("외부",), importance_score=0.7),
            ChapterMetadata("chapter_0002", "타이어", 4.0, 8.0, tags=("타이어",), importance_score=0.6),
            ChapterMetadata("chapter_0003", "실내", 9.0, 13.0, tags=("실내",), importance_score=0.8),
        ]
        subtitles = [
            SubtitleSegment(0.0, 2.0, "외부", subtitle_id=1),
            SubtitleSegment(4.5, 6.0, "타이어", subtitle_id=2),
            SubtitleSegment(10.0, 12.0, "실내", subtitle_id=3),
        ]

        majors, minors = build_major_roughcut_segments(
            chapters,
            subtitles=subtitles,
            max_major_duration=8.5,
        )

        self.assertEqual([segment.major_id for segment in majors], ["A", "B"])
        self.assertEqual([chapter.minor_code for chapter in minors], ["A1", "A2", "B1"])
        self.assertEqual(len(majors[0].minor_groups), 2)
        self.assertEqual(majors[0].minor_groups[0].subtitle_ids, (1,))

    def test_boundary_refiner_prefers_gap_then_scene_cut(self):
        phrases = [
            PackedPhrase("p1", 0.0, 4.0, "소개"),
            PackedPhrase("p2", 5.0, 8.0, "다음"),
        ]
        verification = verify_major_boundary(
            4.0,
            phrases=phrases,
            gaps=[TimelineGap(4.2, 4.8)],
            scene_changes=[SceneChange(3.9, 4.1, 32.0, True)],
            search_window=1.0,
        )

        self.assertEqual(verification.status, "confirmed")
        self.assertAlmostEqual(verification.adjusted_time, 4.5)
        self.assertIn("gap_mid", verification.reason)

    def test_refine_major_boundaries_updates_adjacent_chapters(self):
        chapters = [
            ChapterMetadata("chapter_0001", "A", 0.0, 4.0),
            ChapterMetadata("chapter_0002", "B", 5.0, 8.0),
        ]
        refined = refine_major_boundaries(
            chapters,
            phrases=[PackedPhrase("p1", 0.0, 4.0, "A"), PackedPhrase("p2", 5.0, 8.0, "B")],
            gaps=[TimelineGap(4.2, 4.8)],
            search_window=1.0,
        )

        self.assertAlmostEqual(refined[0].end, 4.5)
        self.assertAlmostEqual(refined[1].start, 4.5)
        self.assertEqual(refined[0].boundary_status, "confirmed")

    def test_pipeline_returns_major_segments_with_minor_groups(self):
        result = run_roughcut_pipeline(
            [
                {"start": 0.0, "end": 2.0, "text": "차량 외부를 봅니다"},
                {"start": 3.0, "end": 5.0, "text": "타이어와 휠을 봅니다"},
                {"start": 7.0, "end": 9.0, "text": "실내를 봅니다"},
            ],
            settings={"roughcut_major_max_duration_sec": 6.0},
        )

        self.assertTrue(result.segments)
        self.assertTrue(result.segments[0].minor_groups)
        self.assertTrue(result.chapters[0].major_id)
        self.assertTrue(result.chapters[0].minor_code)


if __name__ == "__main__":
    unittest.main()
