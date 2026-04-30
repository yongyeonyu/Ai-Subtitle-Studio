# Version: 03.01.36
# Phase: PHASE2
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
