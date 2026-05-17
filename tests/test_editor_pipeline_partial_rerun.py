import unittest
from types import SimpleNamespace
from unittest import mock

from ui.editor.editor_pipeline_partial_rerun import EditorPipelinePartialRerunMixin


class _PartialEditor(EditorPipelinePartialRerunMixin):
    def __init__(self, window=None):
        self.settings = {}
        self._window = window or SimpleNamespace()
        self.scheduled = []

    def window(self):
        return self._window

    def _schedule_post_generation_roughcut_draft(self, **kwargs):
        self.scheduled.append(dict(kwargs))


class EditorPipelinePartialRerunTests(unittest.TestCase):
    def test_partial_runtime_settings_snapshot_uses_current_mode_override(self):
        window = SimpleNamespace(
            _runtime_settings_override={
                "simple_operation_mode": "high",
                "roughcut_llm_enabled": True,
                "roughcut_llm_use_override": True,
                "roughcut_llm_provider": "ollama",
                "roughcut_llm_model": "roughcut-high",
            }
        )
        editor = _PartialEditor(window)
        editor.settings = {"simple_operation_mode": "fast", "stt_quality_preset": "fast"}

        with mock.patch(
            "core.settings.load_settings",
            return_value={
                "simple_operation_mode": "auto",
                "stt_quality_preset": "balanced",
                "selected_model": "subtitle-model",
            },
        ), mock.patch("core.settings.runtime_settings_override", return_value={}):
            snapshot = editor._partial_runtime_settings_snapshot()

        self.assertEqual(snapshot["simple_operation_mode"], "high")
        self.assertEqual(snapshot["stt_quality_preset"], "precise")
        self.assertEqual(snapshot["roughcut_llm_model"], "roughcut-high")
        self.assertTrue(snapshot["roughcut_llm_enabled"])

    def test_partial_rerun_roughcut_uses_manual_mode_settings(self):
        editor = _PartialEditor()

        editor._schedule_partial_rerun_roughcut(
            {"stt_quality_preset": "precise", "roughcut_llm_model": "roughcut-high"},
            inserted_any=True,
        )

        self.assertEqual(
            editor.scheduled,
            [
                {
                    "force": True,
                    "require_autorun": False,
                    "settings_override": {
                        "stt_quality_preset": "precise",
                        "roughcut_llm_model": "roughcut-high",
                    },
                }
            ],
        )

    def test_partial_rerun_roughcut_skips_when_nothing_was_inserted(self):
        editor = _PartialEditor()

        editor._schedule_partial_rerun_roughcut({"stt_quality_preset": "precise"}, inserted_any=False)

        self.assertEqual(editor.scheduled, [])

    def test_prepare_partial_rerun_defers_clearing_until_new_segments_arrive(self):
        editor = _PartialEditor()
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(vad_segments=[]))
        editor._live_stt_preview_segments = []
        editor.clear_segments_in_range = mock.Mock()

        editor._prepare_partial_rerun_state(4.0, 10.0)

        editor.clear_segments_in_range.assert_not_called()
        self.assertEqual(editor._partial_rerun_replace_range, (4.0, 10.0))
        self.assertFalse(editor._partial_rerun_replace_committed)

    def test_commit_partial_rerun_segments_clears_once_and_ignores_empty_results(self):
        editor = _PartialEditor()
        editor.clear_segments_in_range = mock.Mock()
        editor.insert_partial_segments = mock.Mock()
        editor._partial_rerun_replace_range = (4.0, 10.0)
        editor._partial_rerun_replace_committed = False

        self.assertFalse(editor._commit_partial_rerun_segments([]))
        editor.clear_segments_in_range.assert_not_called()
        editor.insert_partial_segments.assert_not_called()

        first = [{"start": 4.0, "end": 5.0, "text": "새 자막"}]
        second = [{"start": 5.0, "end": 6.0, "text": "다음 자막"}]
        self.assertTrue(editor._commit_partial_rerun_segments(first))
        self.assertTrue(editor._commit_partial_rerun_segments(second))

        editor.clear_segments_in_range.assert_called_once_with(4.0, 10.0)
        self.assertEqual(editor.insert_partial_segments.call_args_list, [
            mock.call(first),
            mock.call(second),
        ])


if __name__ == "__main__":
    unittest.main()
