# Version: 03.24.01
# Phase: PHASE2
import os
import tempfile
import unittest
from unittest import mock

from core.audio import live_stt


class LiveSTTCleanupTests(unittest.TestCase):
    def test_transcribe_wav_file_releases_live_worker_after_local_stt(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            with mock.patch("core.audio.live_stt._prepare_live_wav", return_value=wav_path), \
                 mock.patch("core.audio.live_stt._select_live_model", return_value="mlx-live-model"), \
                 mock.patch("core.audio.live_stt._transcribe_local_whisper", return_value="테스트 음성"), \
                 mock.patch("core.audio.live_stt.stop_live_stt_worker") as stop_worker, \
                 mock.patch("core.audio.live_stt.clear_audio_model_memory_caches") as clear_memory:
                result = live_stt.transcribe_wav_file(wav_path, settings={}, start_ts=0.0)

            self.assertEqual(result.text, "테스트 음성")
            stop_worker.assert_called_once()
            clear_memory.assert_called_once_with(include_gpu=True)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def test_live_stt_prefers_coreml_route_when_npu_ready(self):
        with mock.patch("core.audio.live_stt.config.IS_MAC", True), \
             mock.patch(
                 "core.audio.npu_acceleration.prefer_npu_whisper_model",
                 return_value="coreml:large-v3-v20240930_626MB",
             ), \
             mock.patch("core.audio.live_stt._transcribe_coreml", return_value="코어ml"), \
             mock.patch("core.audio.live_stt._transcribe_mlx") as mlx:
            text = live_stt._transcribe_local_whisper(
                "/tmp/fake.wav",
                "mlx-community/whisper-large-v3-mlx",
                settings={"runtime_npu_acceleration_enabled": True, "live_stt_npu_prefer_enabled": True},
            )

        self.assertEqual(text, "코어ml")
        mlx.assert_not_called()

    def test_live_stt_falls_back_from_transformers_when_runtime_is_unavailable(self):
        with mock.patch("core.audio.live_stt.config.IS_MAC", True), \
             mock.patch(
                 "core.audio.npu_acceleration.prefer_npu_whisper_model",
                 return_value="o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
             ), \
             mock.patch(
                 "core.audio.whisper_transformers.transformers_whisper_runtime_status",
                 return_value=(False, "transformers_disabled_torch (torch=2.1.1 / transformers=4.57.1)"),
             ), \
             mock.patch(
                 "core.audio.whisper_transformers.transformers_whisper_fallback_model",
                 return_value="mlx-community/whisper-large-v3-turbo",
             ), \
             mock.patch("core.audio.live_stt._transcribe_transformers") as transformers_route, \
             mock.patch("core.audio.live_stt._transcribe_mlx", return_value="mlx fallback") as mlx:
            text = live_stt._transcribe_local_whisper(
                "/tmp/fake.wav",
                "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
                settings={},
            )

        self.assertEqual(text, "mlx fallback")
        transformers_route.assert_not_called()
        mlx.assert_called_once_with("/tmp/fake.wav", "mlx-community/whisper-large-v3-turbo")

    def test_live_stt_uses_whisperkit_native_model_first(self):
        with mock.patch("core.audio.live_stt.config.IS_MAC", True), \
             mock.patch(
                 "core.audio.npu_acceleration.prefer_npu_whisper_model",
                 return_value="whisperkit-persistent:large-v3",
             ), \
             mock.patch("core.audio.live_stt._transcribe_whisperkit", return_value="위스퍼킷") as whisperkit, \
             mock.patch("core.audio.live_stt._transcribe_mlx") as mlx:
            text = live_stt._transcribe_local_whisper(
                "/tmp/fake.wav",
                "whisperkit-persistent:large-v3",
                settings={},
            )

        self.assertEqual(text, "위스퍼킷")
        whisperkit.assert_called_once_with("/tmp/fake.wav", "whisperkit-persistent:large-v3")
        mlx.assert_not_called()


if __name__ == "__main__":
    unittest.main()
