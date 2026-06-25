# Version: 03.00.26
# Phase: PHASE2
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.roughcut.edl_generator import (
    build_edl_segments,
    build_stitched_cut_boundaries,
    edl_to_dict,
    map_edl_segments_to_clip_sources,
    save_edl_json,
)
from core.roughcut.edit_decision_engine import build_edit_decisions, classify_cut_safety
from core.roughcut.frame_sampler import build_ffmpeg_frame_command, sample_timestamps
from core.roughcut.gap_detector import detect_subtitle_gaps
from core.roughcut.guide_writer import build_markdown_guide, save_markdown_guide
from core.roughcut.models import ChapterMetadata, PackedPhrase
from core.roughcut.pipeline import run_roughcut_pipeline
from core.roughcut.roughcut_llm import RoughCutLLMActionResult
from core.roughcut.render_executor import run_render_plan, write_concat_file
from core.roughcut.renderer_skeleton import build_concat_render_plan, build_ffmpeg_subtitle_burnin_command
from core.roughcut.scene_change_detector import (
    FrameSample,
    classify_scene_change,
    detect_scene_changes,
    mean_abs_rgb_difference,
)
from core.roughcut.semantic_chunker import build_semantic_chunks, chunks_to_chapters
from core.roughcut.story_mapper import map_story_roles
from core.roughcut.subtitle_retimer import format_srt, retime_subtitles_for_edl, save_retimed_srt
from core.roughcut.topic_detector import detect_topic_shifts, extract_keywords, topic_shift_score
from core.roughcut.transcript_packer import format_packed_transcript, pack_transcript


class RoughCutEngine1Tests(unittest.TestCase):
    def test_transcript_packer_splits_on_long_gap_and_speaker_change(self):
        source = [
            {"start": 0.0, "end": 1.0, "text": "안녕하세요", "speaker": "A"},
            {"start": 1.2, "end": 2.0, "text": "반갑습니다", "speaker": "A"},
            {"start": 4.0, "end": 5.0, "text": "다음 이야기", "speaker": "A"},
            {"start": 5.1, "end": 6.0, "text": "화자가 바뀜", "speaker": "B"},
        ]

        packed = pack_transcript(source, silence_gap_threshold=1.0, max_phrase_duration=10.0)

        self.assertEqual(len(packed), 3)
        self.assertEqual(packed[0].text, "안녕하세요 반갑습니다")
        self.assertEqual(packed[0].source_indices, (0, 1))
        self.assertEqual(packed[2].speaker, "B")
        self.assertEqual(source[0]["text"], "안녕하세요")

    def test_format_packed_transcript_is_stable(self):
        packed = pack_transcript([{"start": 0, "end": 1, "text": "hello"}])

        self.assertEqual(format_packed_transcript(packed), "[00000.00-00001.00] S?: hello")

    def test_detect_subtitle_gaps_includes_middle_and_trailing(self):
        gaps = detect_subtitle_gaps(
            [
                {"start": 1.0, "end": 2.0, "text": "a"},
                {"start": 5.0, "end": 6.0, "text": "b"},
            ],
            media_duration=8.0,
            min_gap=1.0,
        )

        self.assertEqual([(round(g.start, 1), round(g.end, 1)) for g in gaps], [(0.0, 1.0), (2.0, 5.0), (6.0, 8.0)])

    def test_scene_change_detector_uses_pixel_delta(self):
        score = mean_abs_rgb_difference(bytes([0, 0, 0]), bytes([30, 30, 30]))
        changes = detect_scene_changes(
            [
                FrameSample(0.0, bytes([0, 0, 0])),
                FrameSample(1.0, bytes([30, 30, 30])),
                FrameSample(2.0, bytes([31, 31, 31])),
            ],
            threshold=18.0,
        )

        self.assertEqual(score, 30.0)
        self.assertTrue(classify_scene_change(score, threshold=18.0))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].start, 0.0)
        self.assertEqual(changes[0].end, 1.0)

    def test_frame_sampler_stays_inside_edges_and_builds_command(self):
        timestamps = sample_timestamps(10.0, 20.0, max_frames=3, avoid_edges=1.0)
        command = build_ffmpeg_frame_command("/tmp/in.mp4", timestamps[0], "/tmp/out.jpg", width=240, quality=4)

        self.assertEqual(timestamps, [11.0, 15.0, 19.0])
        self.assertIn("-ss", command)
        self.assertIn("/tmp/in.mp4", command)
        self.assertIn("/tmp/out.jpg", command)
        self.assertIn("scale=240:-2", command)

    def test_topic_detector_scores_keyword_shift(self):
        score = topic_shift_score("오늘은 카메라 렌즈와 촬영 이야기를 합니다", "다음으로 자동차 시승과 엔진 이야기를 합니다")
        keywords = extract_keywords("카메라 카메라 렌즈 촬영 자동차")

        self.assertGreaterEqual(score, 0.55)
        self.assertEqual(keywords[0], "카메라")

    def test_semantic_chunker_builds_chapters(self):
        phrases = pack_transcript(
            [
                {"start": 0.0, "end": 2.0, "text": "카메라 렌즈 촬영 이야기를 시작합니다"},
                {"start": 2.2, "end": 4.0, "text": "렌즈 선택과 조명 설명입니다"},
                {"start": 20.0, "end": 22.0, "text": "다음으로 자동차 시승과 엔진 이야기를 합니다"},
            ],
            silence_gap_threshold=1.0,
        )
        shifts = detect_topic_shifts(phrases, threshold=0.55)
        chunks = build_semantic_chunks(phrases, topic_shift_threshold=0.55, min_chunk_duration=0.0)
        chapters = chunks_to_chapters(chunks)

        self.assertEqual(len(shifts), 1)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chapters), 2)
        self.assertTrue(chapters[0].title)

    def test_story_mapper_assigns_roles_without_reordering(self):
        phrases = pack_transcript(
            [
                {"start": 0.0, "end": 2.0, "text": "오늘은 카메라 선택의 목표와 배경을 소개합니다"},
                {"start": 4.0, "end": 6.0, "text": "이어서 촬영 과정과 렌즈 설정 방법을 설명합니다"},
                {"start": 8.0, "end": 10.0, "text": "하지만 현장에서 생기는 문제와 핵심 전환점을 봅니다"},
                {"start": 12.0, "end": 14.0, "text": "마지막으로 결과를 정리하고 추천을 남깁니다"},
            ],
            silence_gap_threshold=1.0,
        )
        chapters = chunks_to_chapters(build_semantic_chunks(phrases, min_chunk_duration=0.0))

        mapped = map_story_roles(chapters)

        self.assertEqual([chapter.chapter_id for chapter in mapped], [chapter.chapter_id for chapter in chapters])
        self.assertEqual([chapter.story_role for chapter in mapped], ["기", "승", "전", "결"])
        self.assertTrue(all(chapter.story_reason for chapter in mapped))
        self.assertTrue(all(chapter.move_recommendation for chapter in mapped))

    def test_story_mapper_keeps_order_and_marks_position_hint_conflict(self):
        chapters = chunks_to_chapters(
            build_semantic_chunks(
                pack_transcript(
                    [
                        {"start": 0.0, "end": 2.0, "text": "결론부터 정리하면 오늘 결과와 추천은 명확합니다"},
                        {"start": 5.0, "end": 7.0, "text": "이어서 본론의 과정과 설명으로 이어갑니다"},
                        {"start": 10.0, "end": 12.0, "text": "마지막으로 요약하고 마무리합니다"},
                    ],
                    silence_gap_threshold=1.0,
                ),
                min_chunk_duration=0.0,
            )
        )

        mapped = map_story_roles(chapters)

        self.assertEqual([chapter.chapter_id for chapter in mapped], [chapter.chapter_id for chapter in chapters])
        self.assertEqual(mapped[0].story_role, "결")
        self.assertEqual(mapped[0].move_recommendation, "review_move_toward_결")
        self.assertIn("position_hint_conflict", mapped[0].story_reason)

    def test_cut_safety_prefers_gap_then_phrase_boundary(self):
        phrases = [
            PackedPhrase("p1", 0.0, 2.0, "첫 문장"),
            PackedPhrase("p2", 3.0, 5.0, "둘째 문장"),
        ]
        gaps = detect_subtitle_gaps(
            [
                {"start": 0.0, "end": 2.0, "text": "첫 문장"},
                {"start": 3.0, "end": 5.0, "text": "둘째 문장"},
            ],
            media_duration=5.0,
            min_gap=0.1,
            include_leading=False,
            include_trailing=False,
        )

        ideal = classify_cut_safety(2.5, phrases, gaps)
        acceptable = classify_cut_safety(2.02, phrases, gaps=[])
        risky = classify_cut_safety(1.0, phrases, gaps)

        self.assertEqual(ideal.safety, "ideal")
        self.assertEqual(acceptable.safety, "acceptable")
        self.assertEqual(risky.safety, "risky")
        self.assertEqual(risky.reason, "inside_phrase_body")

    def test_edit_decision_engine_adds_padding_and_move_hint(self):
        phrases = [
            PackedPhrase("p1", 0.0, 4.0, "소개"),
            PackedPhrase("p2", 5.0, 9.0, "핵심 전환"),
        ]
        gaps = detect_subtitle_gaps(
            [
                {"start": 0.0, "end": 4.0, "text": "소개"},
                {"start": 5.0, "end": 9.0, "text": "핵심 전환"},
            ],
            media_duration=9.0,
            min_gap=0.1,
            include_leading=False,
            include_trailing=False,
        )
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, importance_score=0.5, role_confidence=0.8),
            ChapterMetadata(
                "chapter_0002",
                "결론",
                5.0,
                9.0,
                importance_score=0.5,
                story_role="결",
                move_recommendation="review_move_toward_결",
                role_confidence=0.9,
            ),
        ]

        decisions = build_edit_decisions(chapters, phrases, gaps, safe_padding=0.2)

        self.assertEqual([decision.action for decision in decisions], ["keep", "move"])
        self.assertEqual(decisions[0].safety, "acceptable")
        self.assertEqual(decisions[0].source_start, 0.0)
        self.assertAlmostEqual(decisions[0].source_end, 4.2)
        self.assertIn("review_move_toward_결", decisions[1].reason)

    def test_edit_decision_engine_keeps_risky_long_segment_instead_of_trim(self):
        phrases = [PackedPhrase("p1", 0.0, 120.0, "아주 긴 단일 문장")]
        chapter = ChapterMetadata("chapter_0001", "긴 문장", 10.0, 110.0, importance_score=0.5)

        decisions = build_edit_decisions([chapter], phrases, gaps=[], trim_duration_threshold=30.0)

        self.assertEqual(decisions[0].action, "keep")
        self.assertEqual(decisions[0].safety, "risky")
        self.assertIn("trim_skipped:risky_cut", decisions[0].reason)
        self.assertEqual(decisions[0].source_start, 10.0)
        self.assertEqual(decisions[0].source_end, 110.0)

    def test_edl_generator_excludes_remove_and_preserves_metadata(self):
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, story_role="기"),
            ChapterMetadata("chapter_0002", "삭제", 4.0, 5.0, story_role="승"),
            ChapterMetadata("chapter_0003", "핵심", 5.0, 9.0, story_role="전"),
        ]
        decisions = [
            build_edit_decisions([chapters[0]], phrases=[], gaps=[])[0],
            build_edit_decisions([chapters[1]], phrases=[], gaps=[])[0],
            build_edit_decisions([chapters[2]], phrases=[], gaps=[])[0],
        ]
        decisions[1] = type(decisions[1])(
            segment_id=decisions[1].segment_id,
            action="remove",
            reason="low_importance",
            source_start=4.0,
            source_end=5.0,
            output_order=1,
            safety="ideal",
        )

        edl = build_edl_segments("/tmp/source.mp4", decisions, chapters)
        payload = edl_to_dict(edl, metadata={"project": "demo"})

        self.assertEqual([segment.segment_id for segment in edl], ["chapter_0001", "chapter_0003"])
        self.assertEqual(edl[0].output_start, 0.0)
        self.assertEqual(edl[1].output_start, edl[0].output_end)
        self.assertEqual(edl[1].chapter_id, "chapter_0003")
        self.assertEqual(edl[1].story_role, "전")
        self.assertEqual(payload["metadata"]["project"], "demo")
        self.assertEqual(len(payload["segments"]), 2)

    def test_save_edl_json_writes_utf8_payload(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, story_role="기")
        decision = build_edit_decisions([chapter], phrases=[], gaps=[])[0]
        edl = build_edl_segments("/tmp/source.mp4", [decision], [chapter])

        with tempfile.TemporaryDirectory() as tmp:
            path = save_edl_json(Path(tmp) / "roughcut_edl.json", edl, metadata={"제목": "테스트"})
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], "ai_subtitle_studio.roughcut.edl.v1")
        self.assertEqual(payload["metadata"]["제목"], "테스트")
        self.assertEqual(payload["segments"][0]["source_path"], "/tmp/source.mp4")

    def test_stitched_cut_boundaries_follow_output_joins_exactly(self):
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, story_role="기"),
            ChapterMetadata("chapter_0002", "핵심", 5.0, 8.0, story_role="전"),
        ]
        edl = build_edl_segments("/tmp/source.mp4", build_edit_decisions(chapters, phrases=[], gaps=[]), chapters)

        rows = build_stitched_cut_boundaries(edl)
        payload = edl_to_dict(edl, metadata={"project": "demo"})

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["timeline_sec"], edl[0].output_end)
        self.assertEqual(rows[0]["segment_before_id"], "chapter_0001")
        self.assertEqual(rows[0]["segment_after_id"], "chapter_0002")
        self.assertEqual(payload["stitched_cut_boundaries"][0]["timeline_sec"], rows[0]["timeline_sec"])

    def test_markdown_guide_contains_summary_tables_and_review_points(self):
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, summary="시작 설명", story_role="기"),
            ChapterMetadata("chapter_0002", "핵심", 5.0, 9.0, summary="전환점", story_role="전"),
        ]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = build_edl_segments("/tmp/source.mp4", decisions, chapters)

        markdown = build_markdown_guide(chapters, decisions, edl, title="테스트 가이드")

        self.assertIn("# 테스트 가이드", markdown)
        self.assertIn("## 전체 요약", markdown)
        self.assertIn("## 챕터 표", markdown)
        self.assertIn("| 챕터 | 중분류 | 소분류 | 시간 | 역할 | 판단 | 안전도 | 출력 | 요약 |", markdown)
        self.assertIn("chapter_0002", markdown)
        self.assertIn("## 검토 필요 컷", markdown)

    def test_save_markdown_guide_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_markdown_guide(Path(tmp) / "guide.md", "# 제목\n\n본문")
            text = path.read_text(encoding="utf-8")

        self.assertEqual(text, "# 제목\n\n본문\n")

    def test_run_roughcut_pipeline_returns_result(self):
        result = run_roughcut_pipeline(
            [
                {"start": 0.0, "end": 2.0, "text": "오늘은 카메라 선택의 목표를 소개합니다", "speaker": "A"},
                {"start": 4.0, "end": 6.0, "text": "이어서 렌즈 설정 방법을 설명합니다", "speaker": "A"},
                {"start": 8.0, "end": 10.0, "text": "마지막으로 결과와 추천을 정리합니다", "speaker": "A"},
            ],
            media_duration=12.0,
            source_path="/tmp/source.mp4",
        )

        self.assertTrue(result.chapters)
        self.assertEqual(len(result.segments), len(result.chapters))
        self.assertTrue(result.edit_decisions)
        self.assertTrue(result.edl_segments)
        self.assertIn("## 전체 요약", result.guide_markdown)
        self.assertEqual(result.warnings, ())

    def test_run_roughcut_pipeline_applies_llm_major_segments(self):
        with mock.patch("core.roughcut.pipeline.run_roughcut_llm_action") as action:
            action.return_value = RoughCutLLMActionResult(
                action="propose_major_segment",
                ok=True,
                used_llm=True,
                data={
                    "major_segments": [
                        {
                            "major_id": "A",
                            "title": "LLM 소개",
                            "summary": "LLM이 제안한 첫 중분류",
                            "start": 0.0,
                            "end": 6.0,
                            "minor_codes": ["A1"],
                            "confidence": 0.91,
                            "status": "confirmed",
                        }
                    ]
                },
            )
            result = run_roughcut_pipeline(
                [
                    {"start": 0.0, "end": 2.0, "text": "오늘은 목표를 소개합니다", "speaker": "A"},
                    {"start": 4.0, "end": 6.0, "text": "이어서 설정 방법을 설명합니다", "speaker": "A"},
                ],
                media_duration=8.0,
                source_path="/tmp/source.mp4",
                settings={"roughcut_llm_enabled": True, "roughcut_llm_model": "dummy"},
            )

        self.assertEqual(result.segments[0].title, "LLM 소개")
        self.assertIn("roughcut_llm_applied:1", result.warnings)

    def test_run_roughcut_pipeline_handles_empty_input(self):
        result = run_roughcut_pipeline([], use_llm=True)

        self.assertEqual(result.segments, ())
        self.assertIn("no_subtitle_segments", result.warnings)
        self.assertIn("use_llm=True requested", result.warnings[0])

    def test_renderer_skeleton_builds_concat_plan_without_remove_segments(self):
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0, story_role="기"),
            ChapterMetadata("chapter_0002", "삭제", 4.0, 5.0, story_role="승"),
        ]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = build_edl_segments("/tmp/source.mp4", decisions, chapters)
        plan = build_concat_render_plan(edl, "/tmp/out.mp4", "/tmp/roughcut_temp", ffmpeg_binary="ffmpeg")

        self.assertEqual(len(plan.extract_commands), len(edl))
        self.assertEqual(plan.extract_commands[0][0], "ffmpeg")
        self.assertEqual(plan.render_mode, "sync_safe")
        self.assertIn("-vf", plan.extract_commands[0])
        self.assertIn("setpts=PTS-STARTPTS,fps=30", plan.extract_commands[0])
        self.assertIn("-map", plan.extract_commands[0])
        self.assertIn("0:a?", plan.extract_commands[0])
        self.assertIn("-c:v", plan.extract_commands[0])
        self.assertIn("-c", plan.concat_command)
        self.assertEqual(plan.concat_command[plan.concat_command.index("-c") + 1], "copy")
        self.assertIn("roughcut_concat.txt", plan.concat_file_path)
        self.assertEqual(plan.concat_command[-1], "/tmp/out.mp4")

    def test_renderer_skeleton_keeps_stream_copy_as_explicit_unsafe_mode(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0)
        decision = build_edit_decisions([chapter], phrases=[], gaps=[])[0]
        edl = build_edl_segments("/tmp/source.mp4", [decision], [chapter])
        plan = build_concat_render_plan(
            edl,
            "/tmp/out.mp4",
            "/tmp/roughcut_temp",
            ffmpeg_binary="ffmpeg",
            render_mode="copy",
        )

        self.assertEqual(plan.render_mode, "copy")
        self.assertIn("-c", plan.extract_commands[0])
        self.assertEqual(plan.extract_commands[0][plan.extract_commands[0].index("-c") + 1], "copy")
        self.assertNotIn("setpts=PTS-STARTPTS", " ".join(plan.extract_commands[0]))

    def test_renderer_skeleton_supports_lossless_mezzanine_mode(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0)
        decision = build_edit_decisions([chapter], phrases=[], gaps=[])[0]
        edl = build_edl_segments("/tmp/source.mp4", [decision], [chapter])
        plan = build_concat_render_plan(
            edl,
            "/tmp/out.mkv",
            "/tmp/roughcut_temp",
            ffmpeg_binary="ffmpeg",
            render_mode="lossless",
        )

        self.assertEqual(plan.render_mode, "lossless")
        self.assertIn("-vf", plan.extract_commands[0])
        self.assertIn("setpts=PTS-STARTPTS,fps=30", plan.extract_commands[0])
        self.assertIn("-c:v", plan.extract_commands[0])
        self.assertEqual(plan.extract_commands[0][plan.extract_commands[0].index("-c:v") + 1], "ffv1")
        self.assertIn("-c:a", plan.extract_commands[0])
        self.assertEqual(plan.extract_commands[0][plan.extract_commands[0].index("-c:a") + 1], "flac")
        self.assertIn("-c", plan.concat_command)
        self.assertEqual(plan.concat_command[plan.concat_command.index("-c") + 1], "copy")

    def test_renderer_skeleton_refuses_source_overwrite(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0)
        decision = build_edit_decisions([chapter], phrases=[], gaps=[])[0]
        edl = build_edl_segments("/tmp/source.mp4", [decision], [chapter])

        with self.assertRaises(ValueError):
            build_concat_render_plan(edl, "/tmp/source.mp4", "/tmp/roughcut_temp")

    def test_renderer_skeleton_builds_subtitle_burnin_as_last_stage(self):
        command = build_ffmpeg_subtitle_burnin_command(
            "/tmp/roughcut.mp4",
            "/tmp/roughcut.srt",
            "/tmp/roughcut_subtitled.mp4",
        )

        self.assertEqual(command[:2], ("ffmpeg", "-y"))
        self.assertIn("-i", command)
        self.assertIn("-vf", command)
        self.assertIn("subtitles=", command[command.index("-vf") + 1])
        self.assertIn("-c:v", command)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertIn("-crf", command)
        self.assertEqual(command[command.index("-crf") + 1], "0")
        self.assertEqual(command[-1], "/tmp/roughcut_subtitled.mp4")

    def test_subtitle_retimer_clips_and_maps_to_output_time(self):
        chapters = [
            ChapterMetadata("chapter_0001", "소개", 0.0, 4.0),
            ChapterMetadata("chapter_0002", "핵심", 10.0, 14.0),
        ]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = build_edl_segments("/tmp/source.mp4", decisions, chapters)

        retimed = retime_subtitles_for_edl(
            [
                {"id": 10, "start": 1.0, "end": 3.0, "text": "첫 자막"},
                {"id": 11, "start": 13.5, "end": 15.0, "text": "잘리는 자막"},
                {"id": 12, "start": 20.0, "end": 21.0, "text": "제외"},
            ],
            edl,
        )

        self.assertEqual(len(retimed), 2)
        self.assertEqual(retimed[0]["start"], 1.0)
        self.assertEqual(retimed[0]["end"], 3.0)
        self.assertEqual(retimed[1]["source_end"], 14.0)
        self.assertAlmostEqual(retimed[1]["start"], 7.5)
        self.assertEqual(retimed[1]["source_id"], 11)

    def test_multiclip_edl_maps_global_ranges_to_clip_local_sources(self):
        chapters = [
            ChapterMetadata("chapter_0001", "클립1", 3.0, 5.0),
            ChapterMetadata("chapter_0002", "경계", 9.0, 12.0),
        ]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = build_edl_segments("", decisions, chapters)

        mapped = map_edl_segments_to_clip_sources(
            edl,
            [
                {"start": 0.0, "end": 10.0, "file": "/tmp/a.mp4"},
                {"start": 10.0, "end": 20.0, "file": "/tmp/b.mp4"},
            ],
        )

        self.assertEqual([item.source_path for item in mapped], ["/tmp/a.mp4", "/tmp/a.mp4", "/tmp/b.mp4"])
        self.assertEqual((mapped[0].source_start, mapped[0].source_end), (3.0, 5.0))
        self.assertEqual((mapped[1].source_start, mapped[1].source_end), (9.0, 10.0))
        self.assertEqual((mapped[2].source_start, mapped[2].source_end), (0.0, 2.0))
        self.assertEqual((mapped[2].timeline_start, mapped[2].timeline_end), (10.0, 12.0))
        self.assertEqual(mapped[2].output_start, mapped[1].output_end)

    def test_subtitle_retimer_uses_timeline_range_for_multiclip_mapped_edl(self):
        chapters = [ChapterMetadata("chapter_0001", "클립2", 10.0, 12.0)]
        decisions = build_edit_decisions(chapters, phrases=[], gaps=[])
        edl = map_edl_segments_to_clip_sources(
            build_edl_segments("", decisions, chapters),
            [{"start": 10.0, "end": 20.0, "file": "/tmp/b.mp4"}],
        )

        retimed = retime_subtitles_for_edl(
            [{"id": 22, "start": 10.5, "end": 11.5, "text": "클립2 자막"}],
            edl,
        )

        self.assertEqual(len(retimed), 1)
        self.assertEqual(retimed[0]["start"], 0.5)
        self.assertEqual(retimed[0]["end"], 1.5)
        self.assertEqual(retimed[0]["source_start"], 10.5)

    def test_format_and_save_retimed_srt(self):
        subtitles = [{"start": 0.0, "end": 1.234, "text": "안녕하세요"}]
        text = format_srt(subtitles)

        self.assertIn("00:00:00,000 --> 00:00:01,234", text)
        self.assertIn("안녕하세요", text)
        with tempfile.TemporaryDirectory() as tmp:
            path = save_retimed_srt(Path(tmp) / "roughcut.srt", subtitles)
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_render_executor_writes_concat_and_supports_dry_run(self):
        chapter = ChapterMetadata("chapter_0001", "소개", 0.0, 4.0)
        decision = build_edit_decisions([chapter], phrases=[], gaps=[])[0]
        edl = build_edl_segments("/tmp/source.mp4", [decision], [chapter])
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_concat_render_plan(edl, Path(tmp) / "out.mp4", Path(tmp) / "parts")
            concat_path = write_concat_file(plan)
            result = run_render_plan(plan, dry_run=True)

            self.assertTrue(concat_path.exists())
            self.assertIn("roughcut_part_0001.mp4", concat_path.read_text(encoding="utf-8"))
            self.assertIn(str(Path(tmp).resolve()), concat_path.read_text(encoding="utf-8"))
            self.assertTrue(result.dry_run)
            self.assertEqual(result.executed_commands[0][result.executed_commands[0].index("-c:v") + 1], "hevc_videotoolbox")
            self.assertEqual(result.executed_commands[-1][result.executed_commands[-1].index("-c") + 1], "copy")
            self.assertEqual(result.return_codes, (0, 0))


if __name__ == "__main__":
    unittest.main()
