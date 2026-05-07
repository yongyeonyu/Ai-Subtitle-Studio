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
    describe_editor_roughcut_llm_scope,
    editor_roughcut_draft_enabled,
    editor_roughcut_draft_llm_allowed,
    merge_editor_roughcut_draft_state,
)
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin
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
    def test_completion_schedules_roughcut_and_sync_after_cleanup(self):
        class _Timer:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

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
                self._spinner_timer = _Timer()
                self._last_live_processing_stage = "자막 LLM 검수 중"
                self._next_live_processing_stage_at = 123.0

            def window(self):
                return self._main

            def _schedule_post_generation_roughcut_draft(self, force=False):
                self.roughcut_schedule_count += 1
                self._roughcut_draft_status = "queued"

            def _post_completion_sync(self):
                self.post_sync_count += 1

            def _get_current_segments(self):
                return []

        scheduled = []

        def fake_single_shot(delay_ms, callback):
            scheduled.append((delay_ms, callback))

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_pipeline.QTimer.singleShot", side_effect=fake_single_shot):
            editor._set_process_completed()

            self.assertTrue(editor.sm.completed)
            self.assertEqual(editor._spinner_timer.stop_count, 1)
            self.assertEqual(editor._last_live_processing_stage, "")
            self.assertEqual(editor._next_live_processing_stage_at, 0.0)
            self.assertEqual([delay for delay, _callback in scheduled[:2]], [900, 200])

            scheduled[0][1]()
            self.assertEqual(editor.roughcut_schedule_count, 1)

            scheduled[1][1]()
            self.assertEqual(editor.post_sync_count, 1)
            self.assertEqual(main.release_calls, [])

            editor._roughcut_draft_status = "done"

        self.assertEqual(main.release_calls, [])

    def test_late_processing_stage_after_completion_is_ignored(self):
        class _Timer:
            def __init__(self):
                self.stop_count = 0

            def stop(self):
                self.stop_count += 1

        class _State:
            state = "ST_COMP"
            is_locked = False

            def __init__(self):
                self.custom_statuses = []

            def set_custom_status(self, msg):
                self.custom_statuses.append(msg)

        class _Label:
            def __init__(self):
                self.text = None

            def setText(self, text):
                self.text = text

        class _Editor(EditorPipelineMixin):
            def __init__(self):
                self.sm = _State()
                self.status_lbl = _Label()
                self._spinner_timer = _Timer()
                self._last_live_processing_stage = "자막 생성 중"
                self._next_live_processing_stage_at = 123.0

        editor = _Editor()

        editor.set_live_processing_stage("자막 LLM 검수 중 (10/10)")

        self.assertEqual(editor.sm.custom_statuses, [])
        self.assertIsNone(editor.status_lbl.text)
        self.assertEqual(editor._spinner_timer.stop_count, 1)
        self.assertEqual(editor._last_live_processing_stage, "")

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

    def test_long_editor_draft_uses_chunked_llm_scope_when_context_is_small(self):
        self.assertTrue(
            editor_roughcut_draft_llm_allowed(
                _segments(12),
                {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
            )
        )
        self.assertTrue(
            editor_roughcut_draft_llm_allowed(
                _segments(5),
                {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
            )
        )
        scope = describe_editor_roughcut_llm_scope(
            _segments(12),
            {"roughcut_llm_rows_auto_enabled": False, "roughcut_llm_max_context_rows": 5},
        )
        self.assertEqual(scope["mode"], "chunked")
        self.assertEqual(scope["max_context_rows"], 5)
        self.assertGreater(scope["chunk_count"], 1)
        for chunk in scope["chunks"]:
            self.assertLessEqual(
                chunk["prompt_end_index"] - chunk["prompt_start_index"] + 1,
                5,
            )

    def test_post_generation_long_video_runs_chunked_llm_instead_of_skipping(self):
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
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_rows_auto_enabled": False,
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
        class _ImmediateThread:
            def __init__(self, target, *args, **kwargs):
                self._target = target

            def start(self):
                self._target()

        llm_payload = {
            "major_segments": [
                {
                    "major_id": "A",
                    "title": "첫 묶음",
                    "start_subtitle_id": 0,
                    "end_subtitle_id": 5,
                    "confidence": 0.8,
                },
                {
                    "major_id": "B",
                    "title": "둘째 묶음",
                    "start_subtitle_id": 6,
                    "end_subtitle_id": 11,
                    "confidence": 0.8,
                },
            ]
        }
        with mock.patch("ui.editor.editor_roughcut_draft.threading.Thread", _ImmediateThread), \
             mock.patch("core.roughcut.run_editor_roughcut_llm_draft", return_value=llm_payload) as run_llm:
            editor._run_post_generation_roughcut_draft()

        self.assertIsNotNone(editor._roughcut_draft_thread)
        run_llm.assert_called_once()
        self.assertEqual(len(editor.sig_roughcut_draft_ready.calls), 1)
        result, segments, payload = editor.sig_roughcut_draft_ready.calls[0]
        self.assertEqual(payload["refinement_source"], "llm_refined")
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

    def test_editor_draft_llm_uses_roughcut_specific_model_gate(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        with mock.patch("core.roughcut.editor_draft._call_ollama_json") as call_ollama:
            disabled = run_editor_roughcut_llm_draft(
                _segments(3),
                settings={
                    "selected_model": "exaone3.5:7.8b",
                    "roughcut_llm_enabled": False,
                },
            )

        self.assertIsNone(disabled)
        call_ollama.assert_not_called()

        with mock.patch("core.roughcut.editor_draft._call_ollama_json", return_value={"major_segments": []}) as call_ollama:
            enabled = run_editor_roughcut_llm_draft(
                _segments(3),
                settings={
                    "selected_model": "사용 안함",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_use_override": True,
                    "roughcut_llm_provider": "ollama",
                    "roughcut_llm_model": "roughcut-local",
                },
            )

        self.assertEqual(enabled, {"major_segments": []})
        self.assertEqual(call_ollama.call_args.args[0], "roughcut-local")

    def test_editor_draft_prepares_different_roughcut_llm_before_ollama_call(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_llm_provider": "ollama",
            "selected_model": "subtitle-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }
        with mock.patch("core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run") as prepare, \
             mock.patch("core.roughcut.editor_draft._call_ollama_json", return_value={"major_segments": []}) as call_ollama:
            result = run_editor_roughcut_llm_draft(_segments(3), settings=settings)

        self.assertEqual(result, {"major_segments": []})
        prepare.assert_called_once()
        self.assertIs(prepare.call_args.args[0], settings)
        self.assertEqual(prepare.call_args.args[1].model, "roughcut-local")
        self.assertEqual(call_ollama.call_args.args[0], "roughcut-local")

    def test_failed_post_generation_draft_schedules_model_release(self):
        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self):
                self._roughcut_draft_generation = 0
                self._roughcut_draft_thread = object()
                self._roughcut_draft_status = "running"
                self.release_calls = 0

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status

            def _release_ai_models_after_roughcut_draft(self):
                self.release_calls += 1

        editor = _Editor()

        with mock.patch("ui.editor.editor_roughcut_draft.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            editor._apply_post_generation_roughcut_draft(
                None,
                [],
                {"_generation": 0, "refinement_source": "failed"},
            )

        self.assertEqual(editor._roughcut_draft_status, "failed")
        self.assertIsNone(editor._roughcut_draft_thread)
        self.assertEqual(editor.release_calls, 1)

    def test_successful_post_generation_draft_schedules_model_release(self):
        class _Main:
            def __init__(self):
                self._current_project_path = "/tmp/editor-post-generation.aistudio"
                self._roughcut_widget = None
                self._editor_roughcut_result = None
                self._multiclip_boundaries = []

        class _Editor(EditorRoughcutDraftMixin):
            def __init__(self, main):
                self._main = main
                self._roughcut_draft_generation = 0
                self._roughcut_draft_thread = object()
                self._roughcut_draft_status = "running"
                self._last_roughcut_draft_major_count = None
                self.settings = {}
                self.media_path = "/tmp/source.mp4"
                self.release_calls = 0
                self.redraw_calls = 0

            def window(self):
                return self._main

            def _draft_settings_snapshot(self):
                return dict(self.settings)

            def _set_roughcut_draft_status(self, status: str, count=None):
                self._roughcut_draft_status = status
                if count is not None:
                    self._last_roughcut_draft_major_count = count

            def _redraw_timeline(self):
                self.redraw_calls += 1

            def _release_ai_models_after_roughcut_draft(self):
                self.release_calls += 1

        segments = _segments(6)
        result = build_editor_roughcut_draft_result(segments, settings={"roughcut_major_min_subtitle_count": 2})
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            settings={},
            source_path="/tmp/source.mp4",
            source_media="현재 에디터",
            media_files=["/tmp/source.mp4"],
            clip_boundaries=[],
            editor_mode="single",
        )
        candidate["_generation"] = 0
        candidate["refinement_source"] = "llm_refined"

        main = _Main()
        editor = _Editor(main)

        with mock.patch("ui.editor.editor_roughcut_draft.QTimer.singleShot", side_effect=lambda _delay, callback: callback()), \
             mock.patch("core.project.project_manager.save_project") as save_project, \
             mock.patch("core.project.project_io.read_project_file", return_value={"roughcut_state": {}}), \
             mock.patch("ui.editor.editor_roughcut_draft.os.path.exists", return_value=False):
            editor._apply_post_generation_roughcut_draft(result, segments, candidate)

        save_project.assert_called_once()
        self.assertEqual(editor._roughcut_draft_status, "done")
        self.assertEqual(editor.release_calls, 1)
        self.assertEqual(editor.redraw_calls, 1)
        self.assertIs(main._editor_roughcut_result, result)
        self.assertIsNone(editor._roughcut_draft_thread)

    def test_chunked_editor_draft_merges_llm_chunks_using_global_subtitle_ids(self):
        from core.roughcut.editor_draft import run_editor_roughcut_llm_draft

        settings = {
            "selected_model": "roughcut-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
            "roughcut_llm_rows_auto_enabled": False,
            "roughcut_llm_max_context_rows": 5,
            "roughcut_llm_chunk_min_rows": 4,
            "roughcut_llm_chunk_max_rows": 5,
            "roughcut_llm_chunk_rows": 4,
            "roughcut_llm_lookahead_rows": 1,
        }
        llm_responses = [
            {
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "초반",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 3,
                        "confidence": 0.8,
                    }
                ]
            },
            {
                "major_segments": [
                    {
                        "major_id": "B",
                        "title": "중반",
                        "start_subtitle_id": 4,
                        "end_subtitle_id": 7,
                        "confidence": 0.8,
                    }
                ]
            },
            {
                "major_segments": [
                    {
                        "major_id": "C",
                        "title": "후반",
                        "start_subtitle_id": 8,
                        "end_subtitle_id": 11,
                        "confidence": 0.8,
                    }
                ]
            },
        ]

        with mock.patch("core.roughcut.editor_draft.prepare_roughcut_llm_model_for_run") as prepare, \
             mock.patch("core.roughcut.editor_draft._call_ollama_json", side_effect=llm_responses) as call_ollama:
            result = run_editor_roughcut_llm_draft(_segments(12), settings=settings)

        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(call_ollama.call_count, 3)
        self.assertEqual(result["_chunk_mode"], "cut_boundary_windowed")
        self.assertEqual(result["_chunk_count"], 3)
        self.assertEqual(
            [(row["start_subtitle_id"], row["end_subtitle_id"]) for row in result["major_segments"]],
            [(0, 3), (4, 7), (8, 11)],
        )

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
