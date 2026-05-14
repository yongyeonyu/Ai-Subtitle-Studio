# Version: 03.01.36
# Phase: PHASE2
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.pipeline.multiclip_pipeline import MulticlipPipelineMixin
from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin


class DummyMulticlipOps(EditorMulticlipOpsMixin):
    pass


class DummyActions(EditorActionsMixin):
    def __init__(self, boundaries):
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(_multiclip_boxes=list(boundaries))
        )
        self.media_path = boundaries[0]["file"]
        self._main = SimpleNamespace(
            _multiclip_boundaries=list(boundaries),
            _reuse_clip_indices=set(),
            _current_project_path="",
        )

    def window(self):
        return self._main


class Cp11MulticlipOffsetTests(unittest.TestCase):
    def test_existing_clip_srt_is_offset_once_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "clip2.mp4")
            srt = os.path.join(tmp, "clip2.srt")
            open(clip, "w", encoding="utf-8").close()
            with open(srt, "w", encoding="utf-8") as handle:
                handle.write(
                    "1\n00:00:24,500 --> 00:00:25,500\nB\n\n"
                    "2\n00:00:10,000 --> 00:00:11,000\nA\n"
                )

            result = DummyMulticlipOps()._collect_existing_clip_segments(
                clip, offset=78.04, clip_idx=1
            )

        self.assertEqual([seg["text"] for seg in result], ["A", "B"])
        self.assertAlmostEqual(result[0]["start"], 88.04)
        self.assertAlmostEqual(result[1]["start"], 102.54)
        self.assertTrue(all(seg["_clip_file"] == clip for seg in result))
        self.assertTrue(all(seg["_clip_idx"] == 1 for seg in result))

    def test_pipeline_offset_preserves_clip_metadata_and_word_times(self):
        mixin = MulticlipPipelineMixin()
        segs = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "hello",
                "words": [{"start": 1.1, "end": 1.5, "word": "hello"}],
                "asr_metadata": {"words": [{"start": 1.2, "end": 1.6}]},
            }
        ]

        out = mixin._offset_multiclip_segments(segs, 78.04, 1, "clip2.mp4")

        self.assertAlmostEqual(out[0]["start"], 79.04)
        self.assertAlmostEqual(out[0]["words"][0]["start"], 79.14)
        self.assertAlmostEqual(out[0]["asr_metadata"]["words"][0]["start"], 79.24)
        self.assertEqual(out[0]["_clip_idx"], 1)
        self.assertEqual(out[0]["_clip_file"], "clip2.mp4")

    def test_multiclip_save_uses_local_for_clip_and_global_for_integrated(self):
        boundaries = [
            {"start": 0.0, "end": 78.04, "file": "/tmp/clip1.mp4"},
            {"start": 78.04, "end": 130.0, "file": "/tmp/clip2.mp4"},
        ]
        editor = DummyActions(boundaries)
        segs = [
            {
                "start": 102.54,
                "end": 104.54,
                "text": "clip2 subtitle",
                "_clip_idx": 1,
                "_clip_file": "/tmp/clip2.mp4",
            }
        ]
        saved = {}

        def fake_get_srt_path(path):
            return path.replace(".mp4", ".srt")

        def fake_save_srt(items, path, *args, **kwargs):
            saved[path] = [dict(item) for item in items]

        with patch("ui.editor.editor_actions.get_srt_path", side_effect=fake_get_srt_path), \
             patch("ui.editor.editor_actions.save_srt", side_effect=fake_save_srt):
            ok = editor._save_multiclip_srts(segs, [b["file"] for b in boundaries])

        self.assertTrue(ok)
        self.assertAlmostEqual(saved["/tmp/clip2.srt"][0]["start"], 24.5)
        self.assertAlmostEqual(saved["/tmp/clip2.srt"][0]["end"], 26.5)
        self.assertAlmostEqual(saved["/tmp/clip1_통합.srt"][0]["start"], 102.54)
        self.assertAlmostEqual(saved["/tmp/clip1_통합.srt"][0]["end"], 104.54)

    def test_delete_clip_transaction_updates_owner_and_persists(self):
        owner = SimpleNamespace(
            _multiclip_files=["/tmp/a.mp4", "/tmp/b.mp4", "/tmp/c.mp4"],
            _active_clip_idx=0,
        )

        class _Editor(DummyMulticlipOps):
            def __init__(self):
                self._undo_mgr = SimpleNamespace(push_immediate=Mock())
                self._apply_multiclip_runtime_state = Mock()
                self._reload_apply_and_persist_multiclip = Mock()

            def window(self):
                return owner

            def _remap_segments_for_multiclip_files(self, files):
                return ([{"text": "kept"}], [{"file": path, "start": idx * 10.0, "end": (idx + 1) * 10.0} for idx, path in enumerate(files)])

        editor = _Editor()

        editor._on_clip_delete_requested(1)

        editor._undo_mgr.push_immediate.assert_called_once()
        editor._apply_multiclip_runtime_state.assert_called_once()
        self.assertEqual(editor._apply_multiclip_runtime_state.call_args.args[1], ["/tmp/a.mp4", "/tmp/c.mp4"])
        editor._reload_apply_and_persist_multiclip.assert_called_once_with([{"text": "kept"}])
        self.assertEqual(owner._active_clip_idx, 1)

    def test_add_clip_transaction_seeds_runtime_and_imports_existing_srt_when_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_clip = os.path.join(tmp, "base.mp4")
            added_clip = os.path.join(tmp, "added.mp4")
            added_srt = os.path.join(tmp, "added.srt")
            open(base_clip, "w", encoding="utf-8").close()
            open(added_clip, "w", encoding="utf-8").close()
            open(added_srt, "w", encoding="utf-8").close()
            owner = SimpleNamespace(
                _multiclip_files=[],
                _active_clip_idx=0,
            )

            class _Dialog:
                def __init__(self, files, _owner, **_kwargs):
                    self.received_files = list(files)
                    self.sorted_files = [base_clip, added_clip]

                def exec(self):
                    return True

            class _Editor(DummyMulticlipOps):
                def __init__(self):
                    self.media_path = base_clip
                    self._undo_mgr = SimpleNamespace(push_immediate=Mock())
                    self._apply_multiclip_runtime_state = Mock()
                    self._reload_apply_and_persist_multiclip = Mock()
                    self._append_existing_multiclip_segments = Mock(return_value=[{"text": "merged"}])

                def window(self):
                    return owner

                def _recompute_multiclip_boundaries(self, files):
                    return [{"file": path, "start": idx * 10.0, "end": (idx + 1) * 10.0} for idx, path in enumerate(files)]

                def _remap_segments_for_multiclip_files(self, files):
                    return ([{"text": "current"}], self._recompute_multiclip_boundaries(files))

            editor = _Editor()

            with patch("ui.project.multiclip_panel.MultiClipEditor", _Dialog), \
                 patch("ui.dialogs.message_box.ask_yes_no", return_value=True):
                editor._on_clip_add_requested()

            self.assertGreaterEqual(editor._apply_multiclip_runtime_state.call_count, 2)
            self.assertEqual(editor._undo_mgr.push_immediate.call_count, 1)
            editor._append_existing_multiclip_segments.assert_called_once()
            self.assertEqual(editor._append_existing_multiclip_segments.call_args.args[2], [added_clip])
            editor._reload_apply_and_persist_multiclip.assert_called_once_with([{"text": "merged"}])


if __name__ == "__main__":
    unittest.main()
