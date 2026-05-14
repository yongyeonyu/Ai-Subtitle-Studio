import unittest

from core.roughcut.model_capability import roughcut_llm_is_capable, roughcut_llm_parameter_b


class RoughcutModelCapabilityTests(unittest.TestCase):
    def test_codex_cli_variants_are_allowed(self):
        item = {
            "name": "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
            "details": {"provider": "openai"},
        }
        self.assertTrue(roughcut_llm_is_capable(item))

    def test_small_flash_cloud_model_is_blocked(self):
        item = {
            "name": "gemini 2.5 flash",
            "display_name": "Gemini 2.5 Flash",
            "details": {"provider": "google"},
        }
        self.assertFalse(roughcut_llm_is_capable(item))

    def test_parameter_parser_reads_b_suffix(self):
        item = {
            "name": "exaone3.5:7.8b",
            "details": {"provider": "ollama"},
        }
        self.assertEqual(roughcut_llm_parameter_b(item), 7.8)
        self.assertTrue(roughcut_llm_is_capable(item))

    def test_small_local_model_without_known_latest_alias_is_rejected(self):
        item = {
            "name": "toy-model:3b",
            "details": {"provider": "ollama"},
            "size": 1_000_000_000,
        }
        self.assertFalse(roughcut_llm_is_capable(item))


if __name__ == "__main__":
    unittest.main()
