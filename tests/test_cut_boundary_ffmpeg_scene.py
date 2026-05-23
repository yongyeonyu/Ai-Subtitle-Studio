import os
import tempfile
import types
import unittest
from unittest.mock import patch

from core.cut_boundary_ffmpeg_scene import (
    FFMPEG_SCENE_SOURCE,
    detect_ffmpeg_scene_boundaries,
    parse_ffmpeg_scene_showinfo,
)


class CutBoundaryFfmpegSceneTests(unittest.TestCase):
    def test_parse_showinfo_extracts_scene_times(self):
        stderr = "\n".join(
            [
                "[Parsed_showinfo_1] n:0 pts:100 pts_time:4.000 pos:0",
                "[Parsed_showinfo_1] n:1 pts:260 pts_time:10.400 pos:0 lavfi.scene_score=0.61",
            ]
        )

        rows = parse_ffmpeg_scene_showinfo(stderr, threshold=0.35)

        self.assertEqual(rows, [(4.0, 0.35), (10.4, 0.61)])

    def test_detect_scene_boundaries_applies_gap_and_metadata(self):
        stderr = "\n".join(
            [
                "[Parsed_showinfo_1] n:0 pts:100 pts_time:4.000 pos:0",
                "[Parsed_showinfo_1] n:1 pts:140 pts_time:5.600 pos:0",
                "[Parsed_showinfo_1] n:2 pts:360 pts_time:14.400 pos:0",
            ]
        )
        completed = types.SimpleNamespace(returncode=0, stdout="", stderr=stderr)
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "video.mp4")
            with open(media, "wb") as handle:
                handle.write(b"fake")
            with patch("core.cut_boundary_ffmpeg_scene.subprocess.run", return_value=completed):
                rows = detect_ffmpeg_scene_boundaries(
                    media,
                    clip_offset=100.0,
                    clip_idx=2,
                    fps=25.0,
                    threshold=0.3,
                    min_gap_sec=8.0,
                )

        self.assertEqual([row["clip_local_sec"] for row in rows], [4.0, 14.4])
        self.assertEqual(rows[0]["timeline_sec"], 104.0)
        self.assertEqual(rows[0]["source"], FFMPEG_SCENE_SOURCE)
        self.assertTrue(rows[0]["refine_pending"])
        self.assertEqual(rows[0]["clip_idx"], 2)

    def test_detect_scene_prefers_videotoolbox_on_macos(self):
        completed = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "video.mp4")
            with open(media, "wb") as handle:
                handle.write(b"fake")
            with patch("core.ffmpeg_acceleration.config.IS_MAC", True), \
                 patch("core.cut_boundary_ffmpeg_scene.subprocess.run", return_value=completed) as run:
                detect_ffmpeg_scene_boundaries(media)

        cmd = run.call_args.args[0]
        self.assertIn("-hwaccel", cmd)
        self.assertIn("videotoolbox", cmd)
        self.assertLess(cmd.index("-hwaccel"), cmd.index("-i"))

    def test_detect_scene_falls_back_when_videotoolbox_command_fails(self):
        stderr = "[Parsed_showinfo_1] n:1 pts:100 pts_time:4.000 pos:0 lavfi.scene_score=0.61"
        failed = types.SimpleNamespace(returncode=1, stdout="", stderr="hw failed")
        completed = types.SimpleNamespace(returncode=0, stdout="", stderr=stderr)
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "video.mp4")
            with open(media, "wb") as handle:
                handle.write(b"fake")
            with patch("core.ffmpeg_acceleration.config.IS_MAC", True), \
                 patch("core.cut_boundary_ffmpeg_scene.subprocess.run", side_effect=[failed, completed]) as run:
                rows = detect_ffmpeg_scene_boundaries(media)

        self.assertEqual([row["clip_local_sec"] for row in rows], [4.0])
        first_cmd = run.call_args_list[0].args[0]
        second_cmd = run.call_args_list[1].args[0]
        self.assertIn("videotoolbox", first_cmd)
        self.assertNotIn("videotoolbox", second_cmd)


if __name__ == "__main__":
    unittest.main()
