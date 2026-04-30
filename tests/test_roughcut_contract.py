# Version: 03.01.27
# Phase: PHASE2
import tempfile
import unittest

from core.roughcut import (
    ChapterMetadata,
    EDLSegment,
    PackedPhrase,
    SemanticChunk,
    build_chapters,
    build_edit_decisions,
    detect_topic_shift,
    generate_cut_points,
    generate_edl,
    render_from_edl,
    run_roughcut_pipeline,
    write_markdown_guide,
)
from core.roughcut.chapter_segmenter import build_chapters as compat_build_chapters
from core.roughcut.renderer import render_from_edl as compat_render_from_edl
from core.roughcut.roughcut_pipeline import run_roughcut_pipeline as compat_run_roughcut_pipeline


class RoughCutContractTests(unittest.TestCase):
    def test_public_compat_imports_and_pipeline_intermediates(self):
        result = compat_run_roughcut_pipeline(
            [
                {"start": 0.0, "end": 2.0, "text": "오늘은 차량 외부 디자인을 소개합니다"},
                {"start": 3.0, "end": 5.0, "text": "다음으로 실내 공간과 편의 기능을 봅니다"},
            ],
            source_path="sample.mp4",
        )

        self.assertTrue(result.chapters)
        self.assertTrue(result.edit_decisions)
        self.assertTrue(result.edl)
        self.assertTrue(result.markdown_guide)
        self.assertTrue(result.video_summary)
        self.assertTrue(result.packed_phrases)
        self.assertTrue(result.chunks)
        self.assertTrue(result.cut_points)

    def test_topic_chapter_story_and_guide_aliases(self):
        score = detect_topic_shift("차량 외부 디자인", "다음으로 실내 공간")
        phrases = [
            PackedPhrase("p1", 0.0, 2.0, "차량 외부 디자인"),
            PackedPhrase("p2", 3.0, 5.0, "다음으로 실내 공간"),
        ]
        chapters = compat_build_chapters(
            run_roughcut_pipeline(
                [{"start": p.start, "end": p.end, "text": p.text} for p in phrases]
            ).chunks,
            min_chapter_duration=0.0,
        )
        decisions = build_edit_decisions(chapters, phrases, gaps=[])
        edl = generate_edl("sample.mp4", decisions, chapters)
        guide = write_markdown_guide(chapters, decisions, edl)

        self.assertGreaterEqual(score, 0.0)
        self.assertTrue(all(isinstance(chapter, ChapterMetadata) for chapter in chapters))
        self.assertIn("## 편집 판단", guide)
        self.assertIn("## 컷 포인트", guide)
        self.assertIn("## 위험 컷 / 검토 필요 구간", guide)
        self.assertIn("## 수동 검토 추천 지점", guide)

    def test_build_chapters_splits_long_and_marks_short_merge(self):
        chunks = [
            SemanticChunk(
                "chunk_0001",
                0.0,
                250.0,
                text="핵심 결론과 추천 내용을 길게 설명합니다",
                keywords=("핵심", "추천"),
                topic_shift_score=0.8,
            ),
            SemanticChunk(
                "chunk_0002",
                252.0,
                256.0,
                text="짧은 보충",
                keywords=("보충",),
                topic_shift_score=0.1,
            ),
            SemanticChunk(
                "chunk_0003",
                257.0,
                264.0,
                text="짧은 마무리",
                keywords=("마무리",),
                topic_shift_score=0.2,
            ),
        ]

        chapters = build_chapters(chunks, min_chapter_duration=15.0, max_chapter_duration=100.0)

        self.assertGreaterEqual(len(chapters), 3)
        self.assertIn("split_long_chapter", chapters[0].story_reason)
        self.assertIn("short", chapters[-1].story_reason)
        self.assertGreater(chapters[0].importance_score, 0.5)
        self.assertTrue(chapters[-1].needs_review)

    def test_cut_points_and_renderer_wrapper_contract(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0)
        decisions = build_edit_decisions([chapter], phrases=[], gaps=[])
        cut_points = generate_cut_points(decisions, phrases=[], gaps=[])
        edl = [
            EDLSegment(
                source_path=r"C:\Videos With Space\source.mp4",
                segment_id="chapter_0001",
                source_start=0.0,
                source_end=4.0,
                output_start=0.0,
                output_end=4.0,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            result = compat_render_from_edl(
                r"C:\Videos With Space\source.mp4",
                edl,
                f"{tmp}/out.mp4",
                tmp,
                dry_run=True,
                ffmpeg_path="ffmpeg",
            )

        self.assertEqual([point.boundary for point in cut_points], ["start", "end"])
        self.assertTrue(result.dry_run)
        self.assertEqual(len(result.executed_commands), 2)


if __name__ == "__main__":
    unittest.main()
