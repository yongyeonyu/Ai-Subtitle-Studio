import os
import unittest
from unittest.mock import patch

from core.audio.whisper_transformers import _huggingface_env
from core.audio.media_processor import VideoProcessor
from core.llm.secure_keys import get_api_key


class HuggingFaceTokenTests(unittest.TestCase):
    def test_secure_keys_accepts_huggingface_provider(self):
        with patch("core.llm.secure_keys._keyring_module", return_value=None), \
                patch("core.llm.secure_keys.platform.system", return_value="Linux"):
            self.assertEqual(get_api_key("huggingface"), "")

    def test_transformers_worker_env_injects_saved_hf_token(self):
        base_env = {k: v for k, v in os.environ.items() if k not in {"HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"}}
        with patch("core.audio.whisper_transformers.os.environ", base_env), \
                patch("core.audio.whisper_transformers.get_api_key", return_value="hf_test_token"):
            env = _huggingface_env()

        self.assertEqual(env["HF_TOKEN"], "hf_test_token")
        self.assertEqual(env["HUGGINGFACE_HUB_TOKEN"], "hf_test_token")

    def test_transformers_worker_env_keeps_existing_hf_token(self):
        with patch("core.audio.whisper_transformers.os.environ", {"HF_TOKEN": "hf_env_token"}), \
                patch("core.audio.whisper_transformers.get_api_key", return_value="hf_saved_token"):
            env = _huggingface_env()

        self.assertEqual(env["HF_TOKEN"], "hf_env_token")
        self.assertEqual(env["HUGGINGFACE_HUB_TOKEN"], "hf_env_token")

    def test_media_processor_hf_env_injects_saved_token_for_audio_enhancers(self):
        base_env = {k: v for k, v in os.environ.items() if k not in {"HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"}}
        with patch("core.audio.media_processor.os.environ", base_env), \
                patch("core.audio.media_processor.get_api_key", return_value="hf_audio_token"):
            env = VideoProcessor()._huggingface_env()

        self.assertEqual(env["HF_TOKEN"], "hf_audio_token")
        self.assertEqual(env["HUGGINGFACE_HUB_TOKEN"], "hf_audio_token")


if __name__ == "__main__":
    unittest.main()
