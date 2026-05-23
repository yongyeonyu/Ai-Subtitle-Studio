import unittest
from unittest.mock import patch

from core.ffmpeg_acceleration import ffmpeg_video_decode_accel_args, macos_videotoolbox_enabled


class FFmpegAccelerationTests(unittest.TestCase):
    def test_videotoolbox_args_enabled_on_macos(self):
        with patch("core.ffmpeg_acceleration.config.IS_MAC", True):
            self.assertTrue(macos_videotoolbox_enabled({}))
            self.assertEqual(ffmpeg_video_decode_accel_args({}), ["-hwaccel", "videotoolbox"])

    def test_videotoolbox_args_respect_disable_setting(self):
        with patch("core.ffmpeg_acceleration.config.IS_MAC", True):
            self.assertFalse(macos_videotoolbox_enabled({"ffmpeg_videotoolbox_decode_enabled": False}))
            self.assertEqual(ffmpeg_video_decode_accel_args({"ffmpeg_videotoolbox_decode_enabled": False}), [])


if __name__ == "__main__":
    unittest.main()
