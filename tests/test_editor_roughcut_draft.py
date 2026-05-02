# Version: 03.09.24
# Phase: PHASE2
import json
import unittest
from unittest import mock

from core.roughcut import (
    EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
    apply_roughcut_order_to_subtitles,
    build_editor_roughcut_candidate_payload,
    build_editor_roughcut_draft_result,
    editor_roughcut_draft_enabled,
    editor_roughcut_draft_llm_allowed,
    merge_editor_roughcut_draft_state,
)
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.timeline.timeline_analysis import roughcut_major_markers


def _segments(count: int = 7) -> list[dict]:
    out = []
    cursor = 0.0
    for idx in range(count):
        out.append(
            {
                "start": cursor,
                "end": cursor + 1.0,
                "text": f"자막 내용 {idx + 1}입니다",
                "speaker": "00",
            }
        )
        cursor += 1.2
    return out


class EditorRoughcutDraftTests(unittest.TestCase):
    def test_completion_schedules_roughcut_before_editor_model_release(self):
        class _State:
            def __init__(self):
                self.completed = False

            def complete_ai(self):
                self.completed = True

        class _Main:
            def __init__(self):
                self.release_calls = []

            def sync_menu_from_editor(self, _editor):
                pass

            def _refresh_saved_status_label(self, **_kwargs):
                pass

            def _start_post_completion_idle_timer(self):
                pass

            def _release_ai_models_for_editor_mode(self, *, force=False, preserve_roughcut_status=False):
                self.release_calls.append((force, preserve_roughcut_status))

        class _Editor(EditorPipelineMixin):
            def __init__(self, main):
                self.sm = _State()
                self.is_auto_start = False
                self._roughcut_draft_status = "idle"
                self.roughcut_schedule_count = 0
                self.post_sync_count = 0
                self._main = main

            def window(self):
                return self._main

            def _schedule_post_generation_roughcut_draft(self, force=False):
                self.roughcut_schedule_count += 1
                self._roughcut_draft_status = "queued"

            def _post_completion_sync(self):
                self.post_sync_count += 1

        scheduled = []

        def fake_single_shot(delay_ms, callback):
            scheduled.append((delay_ms, callback))

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=fake_single_shot):
            editor._set_process_completed()

            self.assertTrue(editor.sm.completed)
            self.assertEqual([delay for delay, _callback in scheduled[:3]], [350, 450, 200])

            scheduled[0][1]()
            self.assertEqual(editor.roughcut_schedule_count, 1)

            scheduled[1][1]()
            self.assertEqual(main.release_calls, [])
            self.assertEqual(scheduled[-1][0], 500)

            editor._roughcut_draft_status = "done"
            scheduled[-1][1]()

        self.assertEqual(main.release_calls, [(True, True)])

    def test_fast_recognition_forces_editor_draft_off(self):
        self.assertFalse(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"}
            )
        )
        self.assertTrue(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "balanced"}
            )
        )

    def test_long_editor_draft_skips_llm_context_and_uses_local_segments(self):
        self.assertFalse(
            editor_roughcut_draft_llm_allowed(
                _segments(12),
                {"roughcut_llm_max_context_rows": 5},
            )
        )
        self.assertTrue(
            editor_roughcut_draft_llm_allowed(
                _segments(5),
                {"roughcut_llm_max_context_rows": 5},
            )
        )

    def test_post_generation_long_video_emits_local_roughcut_without_llm_thread(self):
        class _Signal:
            def __init__(self):
                self.calls = []

            def emit(self, result, segments, payload):
                self.calls.append((result, segments, payload))

        class _Main:
            _multiclip_files = []
            _multiclip_boundaries = []

        class _Player:
            total_time = 100.0

        class _Editor(EditorSegmentsMixin):
            def __init__(self):
                self.settings = {
                    "editor_roughcut_draft_enabled": True,
                    "selected_model": "gemma4:e4b",
                    "roughcut_llm_max_context_rows": 5,
                    "roughcut_major_min_subtitle_count": 1,
                    "editor_roughcut_draft_max_major_segments": 10,
                }
                self._roughcut_draft_status = "idle"
                self._roughcut_draft_thread = None
                self._roughcut_draft_generation = 0
                self._roughcut_llm_cooldown_until = 0.0
                self.sig_roughcut_draft_ready = _Signal()
                self.video_player = _Player()
                self.media_path = "/tmp/source.mp4"
                self._main = _Main()

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _get_current_segments(self):
                return _segments(12)

        editor = _Editor()
        with mock.patch("core.roughcut.run_editor_roughcut_llm_draft", side_effect=AssertionError("LLM should not run")):
            editor._run_post_generation_roughcut_draft()

        self.assertIsNone(editor._roughcut_draft_thread)
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(payload["refinement_source"], "local_after_generation_long_video")
        self.assertTrue(result.segments)
        self.assertEqual(len(segments), 12)

    def test_editor_draft_prompt_targets_post_generation_workflow(self):
        from core.roughcut import build_editor_roughcut_draft_prompt

        prompt = build_editor_roughcut_draft_prompt(_segments(3))
        payload = json.loads(prompt)

        self.assertEqual(payload["prompt_id"], "editor_post_generation_roughcut_draft_v1")
        self.assertIn("자막 생성이 완료된 뒤", payload["editor_instructions"])
        self.assertIn("전체를 먼저 훑어보고", payload["editor_instructions"])
        self.assertIn("화면 전환, 주제 전환, 장소 전환", payload["editor_instructions"])
        self.assertIn("단순한 말 끊김", payload["editor_instructions"])
        self.assertIn("10개 이하", payload["editor_instructions"])
        self.assertIn("공백 없이", payload["editor_instructions"])

    def test_builds_major_segments_with_subtitle_rows_as_minor_groups(self):
        result = build_editor_roughcut_draft_result(
            _segments(7),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        self.assertEqual(len(result.segments), 3)
        self.assertEqual(result.segments[0].major_id, "A")
        self.assertEqual(len(result.segments[0].minor_groups), 3)
        self.assertEqual(result.segments[0].minor_groups[0].subtitle_ids, (0,))
        self.assertEqual(len(result.chapters), 7)
        self.assertEqual(len(result.edl_segments), 3)

    def test_timeline_major_markers_expose_abc_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(6),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        markers = roughcut_major_markers(result)

        self.assertEqual([m["label"] for m in markers], ["A", "B"])
        self.assertEqual(markers[0]["kind"], "roughcut_major")
        self.assertLess(markers[0]["start"], markers[0]["end"])

    def test_llm_major_ids_are_renumbered_and_limited_to_a_to_z_for_timeline(self):
        payload = {
            "major_segments": [
                {
                    "major_id": f"M{idx + 40}",
                    "title": f"묶음 {idx}",
                    "start_subtitle_id": idx,
                    "end_subtitle_id": idx,
                    "confidence": 0.8,
                }
                for idx in range(30)
            ]
        }

        result = build_editor_roughcut_draft_result(
            _segments(30),
            settings={"editor_roughcut_draft_max_major_segments": 26},
            llm_payload=payload,
        )
        labels = [marker["label"] for marker in roughcut_major_markers(result)]

        self.assertEqual(len(labels), 26)
        self.assertEqual(labels[0], "A")
        self.assertEqual(labels[-1], "Z")
        self.assertNotIn("M56", labels)

    def test_local_draft_default_targets_ten_major_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(60),
            settings={
                "roughcut_major_min_subtitle_count": 1,
                "editor_roughcut_draft_max_subtitle_count": 1,
            },
        )
        labels = [marker["label"] for marker in roughcut_major_markers(result)]

        self.assertEqual(len(labels), 10)
        self.assertEqual(labels, list("ABCDEFGHIJ"))

    def test_editor_draft_major_segments_cover_full_media_without_gaps(self):
        result = build_editor_roughcut_draft_result(
            [
                {"start": 1.0, "end": 2.0, "text": "인트로"},
                {"start": 4.0, "end": 5.0, "text": "본론"},
                {"start": 9.0, "end": 10.0, "text": "마무리"},
            ],
            media_duration=12.0,
            settings={
                "roughcut_major_min_subtitle_count": 1,
                "editor_roughcut_draft_max_subtitle_count": 1,
            },
        )

        self.assertEqual(result.segments[0].start, 0.0)
        self.assertEqual(result.segments[-1].end, 12.0)
        for previous, current in zip(result.segments, result.segments[1:]):
            self.assertAlmostEqual(previous.end, current.start)
        for decision, segment in zip(result.edit_decisions, result.segments):
            self.assertAlmostEqual(decision.source_start, segment.start)
            self.assertAlmostEqual(decision.source_end, segment.end)

    def test_merges_editor_draft_candidate_without_dropping_existing_candidates(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state(
            {"candidates": [{"candidate_id": "manual_candidate", "name": "수동 후보"}]},
            candidate,
        )

        self.assertEqual(state["selected_candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidate_count"], 2)
        self.assertEqual(state["candidates"][0]["candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidates"][1]["candidate_id"], "manual_candidate")

    def test_editor_save_order_requires_explicit_roughcut_flag(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state({}, candidate)
        self.assertEqual(apply_roughcut_order_to_subtitles(segments, state), segments)

        state["candidates"][0]["editor_save_order_enabled"] = True
        ordered = apply_roughcut_order_to_subtitles(segments, state)
        self.assertEqual(len(ordered), len(segments))
        self.assertEqual(ordered[0]["start"], 0.0)


if __name__ == "__main__":
    unittest.main()
