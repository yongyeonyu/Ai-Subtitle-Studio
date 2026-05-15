from types import SimpleNamespace
import unittest

from core.runtime.logger import get_logger
from core.project.project_runtime_capture import collect_editor_project_aux_state


class _Canvas:
    def __init__(self):
        self.voice_activity_segments = [{"start": 1.0, "end": 2.0, "kind": "speech"}]
        self.scan_boundary_times = [{"timeline_sec": 3.0, "status": "provisional"}]
        self.refresh_calls = 0

    def _refresh_voice_activity_segments(self):
        self.refresh_calls += 1


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


if __name__ == "__main__":
    unittest.main()
