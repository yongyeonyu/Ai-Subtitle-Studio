from types import SimpleNamespace
import unittest

from core.runtime.logger import get_logger
from core.project.project_runtime_capture import collect_editor_project_aux_state, count_editor_project_aux_state
from core.project.project_session_service import editor_session_row_counts, editor_session_save_view


class _Canvas:
    def __init__(self):
        self.voice_activity_segments = [{"start": 1.0, "end": 2.0, "kind": "speech"}]
        self.scan_boundary_times = [{"timeline_sec": 3.0, "status": "provisional"}]
        self.refresh_calls = 0

    def _refresh_voice_activity_segments(self):
        self.refresh_calls += 1


class _LenOnlyRows:
    def __init__(self, count: int):
        self.count = int(count)

    def __len__(self):
        return self.count

    def __iter__(self):
        raise AssertionError("status counts must not copy row payloads")


class _StreamingRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("runtime capture rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


class _SessionModel:
    stt_preview_segments = ({"text": "session-preview"},)
    voice_activity_segments = ({"kind": "session-voice"},)
    provisional_boundaries = ({"timeline_sec": 4.0, "status": "session"},)

    def project_save_view(self):
        return {
            "segments": [],
            "stt_preview_segments": [{"text": "session-preview"}],
            "voice_activity_segments": [{"kind": "session-voice"}],
            "provisional_boundaries": [{"timeline_sec": 4.0, "status": "session"}],
        }


class _PartialSessionModel:
    stt_preview_segments = ({"text": "session-preview"},)
    voice_activity_segments = ()
    provisional_boundaries = ()

    def project_save_view(self):
        return {
            "segments": [],
            "stt_preview_segments": [{"text": "session-preview"}],
            "voice_activity_segments": [],
            "provisional_boundaries": [],
        }


class ProjectRuntimeCaptureTests(unittest.TestCase):
    def setUp(self):
        clearer = getattr(get_logger(), "clear_recent_lines", None)
        if callable(clearer):
            clearer()

    def test_collect_editor_project_aux_state_copies_rows_and_prefers_editor_boundary_policy(self):
        canvas = _Canvas()
        editor = SimpleNamespace(
            _live_stt_preview_segments=[{"text": "preview", "start": 0.1, "end": 0.5}],
            timeline=SimpleNamespace(canvas=canvas),
        )
        editor._project_provisional_cut_boundaries_for_save = lambda: [
            {"timeline_sec": 9.0, "status": "editor-policy"}
        ]

        captured = collect_editor_project_aux_state(editor)
        captured["stt_preview_segments"][0]["text"] = "changed"
        captured["voice_activity_segments"][0]["kind"] = "changed"
        captured["provisional_cut_boundaries"][0]["status"] = "changed"

        self.assertEqual(canvas.refresh_calls, 1)
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "preview")
        self.assertEqual(canvas.voice_activity_segments[0]["kind"], "speech")
        self.assertEqual(captured["provisional_cut_boundaries"][0]["timeline_sec"], 9.0)
        self.assertEqual(editor._project_provisional_cut_boundaries_for_save()[0]["status"], "editor-policy")

    def test_collect_editor_project_aux_state_falls_back_to_canvas_when_no_editor_policy_exists(self):
        canvas = _Canvas()
        editor = SimpleNamespace(
            _live_stt_preview_segments=[],
            _auto_cut_boundary_scan_lines=[{"timeline_sec": 7.0, "status": "auto"}],
            timeline=SimpleNamespace(canvas=canvas),
        )

        captured = collect_editor_project_aux_state(editor)

        self.assertEqual(captured["provisional_cut_boundaries"][0]["timeline_sec"], 3.0)
        self.assertEqual(captured["voice_activity_segments"][0]["start"], 1.0)

    def test_collect_editor_project_aux_state_logs_and_falls_back_when_editor_policy_helper_fails(self):
        canvas = _Canvas()
        editor = SimpleNamespace(
            _live_stt_preview_segments=[],
            _auto_cut_boundary_scan_lines=[{"timeline_sec": 7.0, "status": "auto"}],
            timeline=SimpleNamespace(canvas=canvas),
        )

        def _broken_helper():
            raise RuntimeError("boundary helper boom")

        editor._project_provisional_cut_boundaries_for_save = _broken_helper

        captured = collect_editor_project_aux_state(editor)

        self.assertEqual(captured["provisional_cut_boundaries"][0]["timeline_sec"], 3.0)
        self.assertTrue(
            any(
                "프로젝트 보조 상태 수집 실패 [project provisional cut boundaries]" in line
                for line in get_logger().recent_lines(10)
            )
        )

    def test_count_editor_project_aux_state_uses_lengths_without_copying_rows(self):
        canvas = _Canvas()
        canvas.voice_activity_segments = _LenOnlyRows(7)
        canvas.scan_boundary_times = _LenOnlyRows(3)
        editor = SimpleNamespace(
            _live_stt_preview_segments=_LenOnlyRows(5),
            timeline=SimpleNamespace(canvas=canvas),
        )

        counts = count_editor_project_aux_state(editor)

        self.assertEqual(canvas.refresh_calls, 1)
        self.assertEqual(
            counts,
            {
                "stt_preview_segment_count": 5,
                "voice_activity_segment_count": 7,
                "provisional_cut_boundary_count": 3,
            },
        )

    def test_collect_editor_project_aux_state_accepts_streaming_boundary_rows_without_truth_testing(self):
        canvas = _Canvas()
        canvas.voice_activity_segments = _StreamingRows([{"start": 1.0, "end": 2.0, "kind": "speech"}])
        canvas.scan_boundary_times = _StreamingRows([{"timeline_sec": 3.0, "status": "canvas"}])
        editor = SimpleNamespace(
            _live_stt_preview_segments=_StreamingRows([{"text": "preview", "start": 0.1, "end": 0.5}]),
            timeline=SimpleNamespace(canvas=canvas),
        )
        editor._project_provisional_cut_boundaries_for_save = lambda: _StreamingRows(
            [{"timeline_sec": 9.0, "status": "editor-policy"}]
        )

        captured = collect_editor_project_aux_state(editor)

        self.assertEqual(captured["stt_preview_segments"][0]["text"], "preview")
        self.assertEqual(captured["voice_activity_segments"][0]["kind"], "speech")
        self.assertEqual(captured["provisional_cut_boundaries"][0]["status"], "editor-policy")

    def test_collect_editor_project_aux_state_uses_editor_session_service_view(self):
        canvas = _Canvas()
        editor = SimpleNamespace(
            editor_session_model=_SessionModel(),
            _live_stt_preview_segments=[{"text": "legacy"}],
            timeline=SimpleNamespace(canvas=canvas),
        )

        captured = collect_editor_project_aux_state(editor)
        counts = count_editor_project_aux_state(editor)

        self.assertEqual(canvas.refresh_calls, 0)
        self.assertEqual(captured["stt_preview_segments"], [{"text": "session-preview"}])
        self.assertEqual(captured["voice_activity_segments"], [{"kind": "session-voice"}])
        self.assertEqual(captured["provisional_cut_boundaries"], [{"timeline_sec": 4.0, "status": "session"}])
        self.assertEqual(counts["stt_preview_segment_count"], 1)
        self.assertEqual(counts["voice_activity_segment_count"], 1)
        self.assertEqual(counts["provisional_cut_boundary_count"], 1)

    def test_count_editor_project_aux_state_merges_partial_session_counts_with_runtime_counts(self):
        canvas = _Canvas()
        canvas.voice_activity_segments = _LenOnlyRows(7)
        canvas.scan_boundary_times = _LenOnlyRows(3)
        editor = SimpleNamespace(
            editor_session_model=_PartialSessionModel(),
            _live_stt_preview_segments=_LenOnlyRows(5),
            timeline=SimpleNamespace(canvas=canvas),
        )

        counts = count_editor_project_aux_state(editor)

        self.assertEqual(counts["stt_preview_segment_count"], 1)
        self.assertEqual(counts["voice_activity_segment_count"], 7)
        self.assertEqual(counts["provisional_cut_boundary_count"], 3)

    def test_project_session_service_accepts_streaming_views_without_truth_testing(self):
        class _StreamingSession:
            stt_preview_segments = _StreamingRows([{"text": "preview"}])
            voice_activity_segments = _StreamingRows([{"kind": "voice"}])
            provisional_boundaries = _StreamingRows([{"timeline_sec": 1.0}])

            def project_save_view(self):
                return {
                    "segments": _StreamingRows([{"text": "final"}]),
                    "stt_preview_segments": _StreamingRows([{"text": "preview"}]),
                    "voice_activity_segments": _StreamingRows([{"kind": "voice"}]),
                    "boundary_times": _StreamingRows([0.5]),
                    "provisional_boundaries": _StreamingRows([{"timeline_sec": 1.0}]),
                }

        editor = SimpleNamespace(editor_session_model=_StreamingSession())

        self.assertEqual(editor_session_save_view(editor)["segments"], [{"text": "final"}])
        self.assertEqual(
            editor_session_row_counts(editor),
            {
                "stt_preview_segment_count": 1,
                "voice_activity_segment_count": 1,
                "provisional_cut_boundary_count": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
