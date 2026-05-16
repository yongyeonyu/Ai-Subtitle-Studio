# Version: 01.00.00
# Phase: PHASE2
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.llm import codex_provider
from core.llm.codex_provider import DEFAULT_CODEX_LABEL, is_codex_model
from core.llm import openai_provider


class CodexProviderTests(unittest.TestCase):
    def test_is_codex_model_recognizes_aliases(self):
        for label in codex_provider.CODEX_MODEL_ALIASES:
            self.assertTrue(is_codex_model(label), label)
        self.assertTrue(is_codex_model(DEFAULT_CODEX_LABEL))

    def test_is_codex_model_rejects_normal_openai_labels(self):
        self.assertFalse(is_codex_model("OpenAI GPT-5 Mini [유료/API 균형]"))
        self.assertFalse(is_codex_model("gpt-5-mini"))

    def test_parse_chunks_accepts_exact_json(self):
        self.assertEqual(codex_provider._parse_chunks('{"result": ["a", "b"]}'), ["a", "b"])

    def test_parse_json_object_accepts_roughcut_payload(self):
        payload = '{"major_segments": [{"major_id": "A", "title": "도입"}]}'
        self.assertEqual(codex_provider._parse_json_object(payload)["major_segments"][0]["major_id"], "A")

    def test_parse_chunks_recovers_json_from_surrounding_text(self):
        text = 'progress...\n{"result": ["첫 줄", "둘째 줄"]}\ndone'
        self.assertEqual(codex_provider._parse_chunks(text), ["첫 줄", "둘째 줄"])

    def test_parse_chunks_returns_none_for_empty_or_malformed_output(self):
        self.assertIsNone(codex_provider._parse_chunks(""))
        self.assertIsNone(codex_provider._parse_chunks("{not-json"))
        self.assertIsNone(codex_provider._parse_chunks('{"result": []}'))

    def test_missing_codex_binary_raises_clear_error(self):
        with patch("core.llm.codex_provider.shutil.which", return_value=None), \
                patch.dict(os.environ, {"AI_SUBTITLE_CODEX_BIN": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "Codex CLI를 찾을 수 없습니다"):
                codex_provider.split_text(DEFAULT_CODEX_LABEL, "prompt")

    def test_codex_cli_available_reports_missing_binary_without_raising(self):
        with patch("core.llm.codex_provider.shutil.which", return_value=None), \
                patch.dict(os.environ, {"AI_SUBTITLE_CODEX_BIN": ""}, clear=False):
            available, detail = codex_provider.codex_cli_available()

        self.assertFalse(available)
        self.assertIn("Codex CLI를 찾을 수 없습니다", detail)

    def test_split_text_invokes_codex_exec_safely(self):
        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            schema_path = Path(cmd[cmd.index("--output-schema") + 1])
            self.assertTrue(schema_path.exists())
            output_path.write_text(json.dumps({"result": ["a", "b"]}), encoding="utf-8")
            return _Result()

        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            result = codex_provider.split_text(DEFAULT_CODEX_LABEL, "split this", timeout=7)

        self.assertEqual(result, ["a", "b"])
        cmd = captured["cmd"]
        self.assertEqual(cmd[0], "/usr/local/bin/codex")
        self.assertIn("exec", cmd)
        self.assertIn("--ephemeral", cmd)
        self.assertIn("--sandbox", cmd)
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")
        self.assertIn("--skip-git-repo-check", cmd)
        self.assertIn("--output-schema", cmd)
        self.assertIn("--output-last-message", cmd)
        self.assertIn("--config", cmd)
        self.assertEqual(cmd[cmd.index("--config") + 1], 'model_reasoning_effort="low"')
        self.assertFalse(captured["kwargs"].get("shell"))
        self.assertEqual(captured["kwargs"]["timeout"], 7)
        self.assertIn("AI Subtitle Studio's subtitle segmentation engine", captured["kwargs"]["input"])

    def test_split_text_retries_low_effort_when_minimal_conflicts_with_tools(self):
        calls = []
        codex_provider._MINIMAL_EFFORT_TOOL_CONFLICT_SEEN = False

        class _Result:
            def __init__(self, returncode=0, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        def fake_run(cmd, **_kwargs):
            if not cmd or "codex" not in str(cmd[0]):
                return _Result(returncode=1)
            calls.append(cmd)
            effort = cmd[cmd.index("--config") + 1]
            if 'model_reasoning_effort="minimal"' in effort:
                return _Result(
                    returncode=1,
                    stderr="ERROR: The following tools cannot be used with reasoning.effort 'minimal': image_gen, web_search.",
                )
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            output_path.write_text(json.dumps({"result": ["복구"]}), encoding="utf-8")
            return _Result()

        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch.dict(os.environ, {"AI_SUBTITLE_CODEX_SPLIT_EFFORT": "minimal"}, clear=False), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            result = codex_provider.split_text(DEFAULT_CODEX_LABEL, "split this", timeout=7)

        self.assertEqual(result, ["복구"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][calls[0].index("--config") + 1], 'model_reasoning_effort="minimal"')
        self.assertEqual(calls[1][calls[1].index("--config") + 1], 'model_reasoning_effort="low"')
        self.assertTrue(codex_provider._MINIMAL_EFFORT_TOOL_CONFLICT_SEEN)

    def test_split_text_skips_minimal_after_tool_conflict_seen(self):
        calls = []
        codex_provider._MINIMAL_EFFORT_TOOL_CONFLICT_SEEN = True

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **_kwargs):
            if not cmd or "codex" not in str(cmd[0]):
                return _Result()
            calls.append(cmd)
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            output_path.write_text(json.dumps({"result": ["바로 low"]}), encoding="utf-8")
            return _Result()

        try:
            with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                    patch.dict(os.environ, {"AI_SUBTITLE_CODEX_SPLIT_EFFORT": "minimal"}, clear=False), \
                    patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
                result = codex_provider.split_text(DEFAULT_CODEX_LABEL, "split this", timeout=7)
        finally:
            codex_provider._MINIMAL_EFFORT_TOOL_CONFLICT_SEEN = False

        self.assertEqual(result, ["바로 low"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index("--config") + 1], 'model_reasoning_effort="low"')

    def test_split_text_raises_on_timeout(self):
        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 1)):
            with self.assertRaisesRegex(RuntimeError, "시간이 초과"):
                codex_provider.split_text(DEFAULT_CODEX_LABEL, "prompt", timeout=1)

    def test_split_text_retries_timeout_when_retry_configured(self):
        calls = {"count": 0}
        original_run = subprocess.run

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            if not cmd or "codex" not in str(cmd[0]):
                return original_run(cmd, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                raise subprocess.TimeoutExpired("codex", 1)
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            output_path.write_text(json.dumps({"result": ["a", "b"]}), encoding="utf-8")
            return _Result()

        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch.dict(os.environ, {"AI_SUBTITLE_CODEX_RETRIES": "1", "AI_SUBTITLE_CODEX_RETRY_BACKOFF_SEC": "0"}, clear=False), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            result = codex_provider.split_text(DEFAULT_CODEX_LABEL, "split this", timeout=7)

        self.assertEqual(result, ["a", "b"])
        self.assertEqual(calls["count"], 2)

    def test_run_json_invokes_codex_without_output_schema(self):
        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            output_path.write_text(
                json.dumps({"major_segments": [{"major_id": "A", "title": "도입"}]}),
                encoding="utf-8",
            )
            return _Result()

        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            result = codex_provider.run_json(DEFAULT_CODEX_LABEL, "roughcut this", timeout=9)

        self.assertEqual(result["major_segments"][0]["major_id"], "A")
        cmd = captured["cmd"]
        self.assertEqual(cmd[0], "/usr/local/bin/codex")
        self.assertIn("--output-last-message", cmd)
        self.assertNotIn("--output-schema", cmd)
        self.assertIn("--config", cmd)
        self.assertEqual(cmd[cmd.index("--config") + 1], 'model_reasoning_effort="low"')
        self.assertIn("AI Subtitle Studio's roughcut planning engine", captured["kwargs"]["input"])

    def test_run_json_prefers_task_specific_effort_override(self):
        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            output_path = Path(cmd[cmd.index("--output-last-message") + 1])
            output_path.write_text(
                json.dumps({"major_segments": [{"major_id": "A", "title": "도입"}]}),
                encoding="utf-8",
            )
            return _Result()

        with patch("core.llm.codex_provider.shutil.which", return_value="/usr/local/bin/codex"), \
                patch.dict(os.environ, {"AI_SUBTITLE_CODEX_JSON_EFFORT": "medium"}, clear=False), \
                patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            codex_provider.run_json(DEFAULT_CODEX_LABEL, "roughcut this", timeout=9)

        cmd = captured["cmd"]
        self.assertIn("--config", cmd)
        self.assertEqual(cmd[cmd.index("--config") + 1], 'model_reasoning_effort="medium"')

    def test_openai_provider_treats_codex_as_openai_like_without_api_key(self):
        self.assertTrue(openai_provider.is_openai_model(DEFAULT_CODEX_LABEL))
        with patch("core.llm.codex_provider.split_text", return_value=["a", "b"]) as split:
            result = openai_provider.split_text("", DEFAULT_CODEX_LABEL, "prompt")
        self.assertEqual(result, ["a", "b"])
        split.assert_called_once()

    def test_startup_ollama_preflight_skips_codex_and_cloud_models(self):
        from ui.main.main_signals import _is_preflight_local_ollama_model

        self.assertFalse(_is_preflight_local_ollama_model(DEFAULT_CODEX_LABEL))
        self.assertFalse(_is_preflight_local_ollama_model("OpenAI GPT-5 Mini [유료/API 균형]"))
        self.assertFalse(_is_preflight_local_ollama_model("Gemini 2.5 Flash [무료/제한 API]"))
        self.assertFalse(_is_preflight_local_ollama_model("사용 안함 (Whisper 단독 진행)"))
        self.assertTrue(_is_preflight_local_ollama_model("exaone3.5:7.8b"))

    def test_startup_preflight_does_not_probe_codex_as_ollama(self):
        from ui.main.main_signals import SignalHandlersMixin

        class _ImmediateThread:
            def __init__(self, target, **_kwargs):
                self._target = target

            def start(self):
                self._target()

        class _Dummy(SignalHandlersMixin):
            pass

        with patch("ui.main.main_signals.threading.Thread", side_effect=lambda target, **kwargs: _ImmediateThread(target, **kwargs)), \
                patch("core.settings.load_settings", return_value={"selected_model": DEFAULT_CODEX_LABEL}), \
                patch("core.llm.ollama_provider.resolve_ollama_model_for_request") as resolve:
            _Dummy()._preflight_selected_local_llm_models()

        resolve.assert_not_called()

    def test_openai_provider_non_codex_without_key_still_returns_none(self):
        result = openai_provider.split_text("", "OpenAI GPT-5 Mini [유료/API 균형]", "prompt")
        self.assertIsNone(result)

    def test_subtitle_engine_codex_empty_key_does_not_emit_missing_key_error(self):
        from core.engine import subtitle_engine

        logger = Mock()
        with patch("core.engine.subtitle_engine.get_logger", return_value=logger), \
                patch("core.engine.subtitle_engine.openai_split_text", return_value=["안녕하세요", "반갑습니다"]):
            subtitle_engine.ask_openai_to_split(
                "안녕하세요 반갑습니다",
                8,
                {},
                DEFAULT_CODEX_LABEL,
                "",
                "",
            )

        messages = [str(call.args[0]) for call in logger.log.call_args_list]
        self.assertFalse(any("API 키가 없습니다" in msg for msg in messages))
        self.assertTrue(any("Codex CLI" in msg for msg in messages))

    def test_roughcut_openai_json_uses_codex_without_api_key(self):
        from core.roughcut.editor_draft import _call_openai_json

        expected = {"major_segments": [{"major_id": "A", "title": "도입"}]}
        with patch("core.llm.codex_provider.run_json", return_value=expected) as run_json:
            result = _call_openai_json(DEFAULT_CODEX_LABEL, "roughcut prompt", timeout=11)

        self.assertEqual(result, expected)
        run_json.assert_called_once_with(DEFAULT_CODEX_LABEL, "roughcut prompt", timeout=11)

    def test_subtitle_engine_non_codex_empty_key_still_blocks(self):
        from core.engine import subtitle_engine

        logger = Mock()
        with patch("core.engine.subtitle_engine.get_logger", return_value=logger):
            result = subtitle_engine.ask_openai_to_split(
                "안녕하세요 반갑습니다",
                8,
                {},
                "OpenAI GPT-5 Mini [유료/API 균형]",
                "",
                "",
            )

        self.assertIsNone(result)
        messages = [str(call.args[0]) for call in logger.log.call_args_list]
        self.assertTrue(any("API 키가 없습니다" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
