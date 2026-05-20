import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.qa_suite_runner as qa_suite_runner


class QASuiteRunnerTests(unittest.TestCase):
    def test_build_scenarios_major_includes_core_macau_sequences(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenarios = qa_suite_runner.build_scenarios("major", Path(tmp))

        self.assertEqual(
            [item["id"] for item in scenarios],
            [
                "editor_compact_macau",
                "video_menu_macau",
                "save_export_macau",
                "menu_stt_lora_macau",
            ],
        )

    def test_build_scenarios_full_adds_tinyping_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenarios = qa_suite_runner.build_scenarios("full", Path(tmp))

        self.assertEqual(
            [item["id"] for item in scenarios[-3:]],
            [
                "tinyping_fast_60s",
                "tinyping_auto_60s",
                "tinyping_high_60s",
            ],
        )

    def test_run_suite_writes_manifest_and_result_files(self):
        def _fake_run_scenario(spec, _python_bin):
            return {
                "id": spec["id"],
                "type": spec["type"],
                "output_dir": str(spec["output_dir"]),
                "ok": spec["id"] != "save_export_macau",
                "failed_step": "" if spec["id"] != "save_export_macau" else "export_subtitles",
            }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "suite"
            with patch("tools.qa_suite_runner._ensure_app_ready", return_value={"ok": True, "started_app": False, "status": {"ok": True}}):
                with patch("tools.qa_suite_runner._run_scenario", side_effect=_fake_run_scenario):
                    exit_code = qa_suite_runner.run_suite("major", output_dir, qa_suite_runner.DEFAULT_PYTHON)

            manifest = json.loads((output_dir / "suite_manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "suite_result.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "suite_result.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertEqual(manifest["scenario_ids"][0], "editor_compact_macau")
        self.assertEqual(summary["failed_count"], 1)
        self.assertIn("save_export_macau", markdown)
        self.assertIn("## Failed", markdown)

    def test_run_suite_fails_fast_when_app_bootstrap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "suite"
            with patch(
                "tools.qa_suite_runner._ensure_app_ready",
                return_value={"ok": False, "started_app": True, "status": {"ok": False, "error": "app_unreachable"}},
            ):
                with patch("tools.qa_suite_runner._run_scenario") as run_scenario:
                    exit_code = qa_suite_runner.run_suite("quick", output_dir, qa_suite_runner.DEFAULT_PYTHON)

            summary = json.loads((output_dir / "suite_result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["app_bootstrap"]["status"]["error"], "app_unreachable")
        run_scenario.assert_not_called()

    def test_prepare_app_for_scenario_reuses_app_for_quick(self):
        spec = {
            "id": "editor_compact_macau",
            "type": "app_sequence",
            "output_dir": Path(tempfile.gettempdir()) / "qa_suite_runner_quick_prepare",
        }
        with patch("tools.qa_suite_runner._restart_app") as restart_app:
            result = qa_suite_runner._prepare_app_for_scenario("quick", spec, qa_suite_runner.DEFAULT_PYTHON)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "reuse_app_quick")
        restart_app.assert_not_called()

    def test_prepare_app_for_scenario_restarts_app_for_major_app_sequence(self):
        spec = {
            "id": "video_menu_macau",
            "type": "app_sequence",
            "output_dir": Path(tempfile.gettempdir()) / "qa_suite_runner_major_prepare",
        }
        with patch(
            "tools.qa_suite_runner._restart_app",
            return_value={"ok": True, "terminated_pids": [123], "stopped": True, "started_app": True, "pid": 456, "status": {"ok": True}},
        ) as restart_app:
            result = qa_suite_runner._prepare_app_for_scenario("major", spec, qa_suite_runner.DEFAULT_PYTHON)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "restart_app_per_scenario")
        restart_app.assert_called_once()


if __name__ == "__main__":
    unittest.main()
