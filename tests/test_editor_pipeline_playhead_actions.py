import unittest
from unittest.mock import Mock, patch

from ui.editor.editor_pipeline_playhead_actions import EditorPipelinePlayheadActionsMixin
from ui.editor.editor_multiclip_owner_bridge import EditorMulticlipOwnerBridgeMixin


class _PlayheadEditor(EditorPipelinePlayheadActionsMixin):
    def __init__(self):
        self._segments = [
            {"start": 1.0, "end": 2.0, "text": "A"},
            {"start": 2.0, "end": 4.0, "text": "B"},
        ]
        self.calls = []

    def _get_current_segments(self):
        return list(self._segments)

    def _run_partial_backend(self, start_sec, end_sec, is_single):
        self.calls.append((start_sec, end_sec, is_single))

    def _partial_rerun_total_end(self):
        return 9.0


class _OwnerBridge(EditorMulticlipOwnerBridgeMixin):
    def __init__(self, owner=None, should_fail=False):
        self._owner = owner
        self._should_fail = should_fail

    def window(self):
        if self._should_fail:
            raise RuntimeError("gone")
        return self._owner


class EditorPipelinePlayheadActionsTests(unittest.TestCase):
    def test_re_recognize_segment_uses_matching_segment_range(self):
        editor = _PlayheadEditor()

        editor._re_recognize_segment(2.5)

        self.assertEqual(editor.calls, [(2.0, 4.0, True)])

    def test_re_recognize_from_uses_segment_start_and_total_end(self):
        editor = _PlayheadEditor()

        editor._re_recognize_from(2.5)

        self.assertEqual(editor.calls, [(2.0, 9.0, False)])

    def test_show_playhead_menu_routes_cut_boundary_and_partial_actions(self):
        editor = _PlayheadEditor()
        editor._set_cut_boundary_level_from_menu = Mock()
        editor._re_recognize_segment = Mock()
        editor._re_recognize_from = Mock()

        with patch("ui.editor.editor_pipeline_playhead_actions.show_context_menu", return_value="cut_boundary:low"):
            editor._show_playhead_menu(object(), 2.5)
        editor._set_cut_boundary_level_from_menu.assert_called_once_with("low")

        with patch("ui.editor.editor_pipeline_playhead_actions.show_context_menu", return_value="re_segment"):
            editor._show_playhead_menu(object(), 2.5)
        editor._re_recognize_segment.assert_called_once_with(2.5)

        with patch("ui.editor.editor_pipeline_playhead_actions.show_context_menu", return_value="re_from"):
            editor._show_playhead_menu(object(), 2.5)
        editor._re_recognize_from.assert_called_once_with(2.5)

    def test_owner_bridge_handles_missing_or_invalid_owner_state(self):
        bridge = _OwnerBridge(should_fail=True)
        self.assertIsNone(bridge._multiclip_owner())
        self.assertEqual(bridge._multiclip_files_from_owner(), [])

        owner = type("Owner", (), {"_active_clip_idx": "bad", "_multiclip_boundaries": [{"end": "bad"}]})()
        bridge = _OwnerBridge(owner=owner)
        self.assertEqual(bridge._multiclip_active_clip_idx(), 0)
        self.assertEqual(bridge._multiclip_total_duration(), 0.0)


if __name__ == "__main__":
    unittest.main()
