import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.renderer import render_subtitle_mov, render_subtitle_overlay_video_gpu


class RendererOverlayTests(unittest.TestCase):
    def test_render_subtitle_mov_creates_qt_app_when_run_standalone(self):
        commands = []

        def fake_make_png(path, _text, _width, _height, _style):
            with open(path, "wb") as handle:
                handle.write(b"png")

        def fake_run(cmd, **_kwargs):
            commands.append(list(cmd))
            with open(cmd[-1], "wb") as handle:
                handle.write(b"mov")
            return SimpleNamespace(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "clip.mp4")
            srt_path = os.path.join(tmp, "clip.srt")
            with open(media_path, "wb") as handle:
                handle.write(b"video")
            with open(srt_path, "w", encoding="utf-8") as handle:
                handle.write("1\n00:00:00,000 --> 00:00:01,000\nhello\n")

            with patch("core.renderer.subprocess.run", side_effect=fake_run), \
                 patch("ui.dialogs.export_dialog._make_png", side_effect=fake_make_png):
                ok = render_subtitle_mov(
                    srt_path,
                    media_path,
                    {"res": "FHD (1920px)", "size": 40, "font": "Apple SD Gothic Neo", "icloud": False},
                )

        self.assertTrue(ok)
        self.assertTrue(commands)

    def test_overlay_video_uses_transparent_mov_instead_of_subtitles_filter(self):
        commands = []
        render_settings = []

        def fake_render_subtitle_mov(_srt_path, target_file, settings, *_args):
            render_settings.append(dict(settings))
            base = os.path.splitext(os.path.basename(target_file))[0]
            mov_path = os.path.join(os.path.dirname(target_file), f"{base}_자막소스.mov")
            with open(mov_path, "wb") as handle:
                handle.write(b"mov")
            return True

        def fake_run(cmd, **_kwargs):
            commands.append(list(cmd))
            with open(cmd[-1], "wb") as handle:
                handle.write(b"mp4")
            return SimpleNamespace(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "clip.mp4")
            srt_path = os.path.join(tmp, "clip.srt")
            output_path = os.path.join(tmp, "clip_자막입힘.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"video")
            with open(srt_path, "w", encoding="utf-8") as handle:
                handle.write("1\n00:00:00,000 --> 00:00:01,000\nhello\n")

            with patch("core.renderer._ffprobe_video_info", return_value={"width": 1920, "height": 1080, "codec_name": "h264"}), \
                 patch("core.renderer.render_subtitle_mov", side_effect=fake_render_subtitle_mov), \
                 patch("core.renderer.subprocess.run", side_effect=fake_run):
                ok = render_subtitle_overlay_video_gpu(
                    srt_path,
                    media_path,
                    {"icloud": True, "res": "4K (3840px)"},
                    output_path=output_path,
                )

        self.assertTrue(ok)
        self.assertTrue(commands)
        flat = " ".join(str(part) for part in commands[-1])
        self.assertIn("overlay=", flat)
        self.assertNotIn("subtitles=", flat)
        self.assertEqual(render_settings[0]["icloud"], False)
        self.assertEqual(render_settings[0]["res"], "FHD (1920px)")


if __name__ == "__main__":
    unittest.main()
