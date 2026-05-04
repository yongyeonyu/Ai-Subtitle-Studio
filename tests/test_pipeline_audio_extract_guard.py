import os
import tempfile
import unittest
from unittest import mock

from core.audio.media_processor import VideoProcessor
from core.pipeline.pipeline_helpers import PipelineHelpersMixin


class _PipelineGuardHarness(PipelineHelpersMixin):
    pass


class PipelineAudioExtractGuardTests(unittest.TestCase):
    def test_empty_audio_extract_result_is_rejected_by_common_guard(self):
        harness = _PipelineGuardHarness()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("core.pipeline.pipeline_helpers.get_logger") as get_logger:
                self.assertIsNone(
                    harness._validate_audio_extract_result(
                        (tmp, []),
                        os.path.join(tmp, "clip.mp4"),
                    )
                )

        get_logger.return_value.log.assert_called()

    def test_audio_extract_result_with_wav_chunk_is_accepted(self):
        harness = _PipelineGuardHarness()
        with tempfile.TemporaryDirectory() as tmp:
            chunk_path = os.path.join(tmp, "chunk_0001.wav")
            with open(chunk_path, "wb") as f:
                f.write(b"RIFF")

            result = (tmp, [{"start": 0.0, "end": 1.0}])
            self.assertIs(harness._validate_audio_extract_result(result, "clip.mp4"), result)

    def test_windows_tool_resolution_keeps_exe_suffix_without_shell(self):
        processor = VideoProcessor()
        with mock.patch("core.audio.media_processor_audio.config.IS_WINDOWS", True), \
             mock.patch("core.audio.media_processor_audio.shutil.which", return_value=None):
            self.assertEqual(processor._resolve_python_cli("resemble-enhance"), "resemble-enhance.exe")


if __name__ == "__main__":
    unittest.main()
