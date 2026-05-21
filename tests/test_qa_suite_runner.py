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

    def test_build_scenarios_full_adds_x5_rolling_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenarios = qa_suite_runner.build_scenarios("full", Path(tmp))

        self.assertEqual(scenarios[-1]["id"], "x5_high_rolling_180s")
        self.assertEqual(scenarios[-1]["type"], "full_media")
        self.assertEqual(scenarios[-1]["mode"], "high")
        self.assertEqual(scenarios[-1]["duration_sec"], 180.0)
        self.assertIn("X5_", Path(scenarios[-1]["media"]).name)

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

    def test_run_full_media_rejects_verifier_empty_subtitle_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "x5_high_rolling_180s"
            spec = {
                "id": "x5_high_rolling_180s",
                "type": "full_media",
                "description": "X5 high-mode 3-minute rolling-window verification.",
                "output_dir": output_dir,
                "media": "/tmp/media.mp4",
                "mode": "high",
                "duration_sec": 180.0,
            }
            payload = {
                "ok": False,
                "mode": "auto",
                "final_segment_count": 0,
                "raw_segment_count": 0,
                "failure_reason": "empty_subtitle_output:raw_segments_zero",
            }
            with patch("tools.qa_suite_runner._run_subprocess", return_value=(1, payload)):
                result = qa_suite_runner._run_full_media(spec, qa_suite_runner.DEFAULT_PYTHON)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_step"], "full_media")
        self.assertEqual(result["result"]["failure_reason"], "empty_subtitle_output:raw_segments_zero")

    def test_main_app_pids_includes_bundle_python_main(self):
        calls = []

        def _fake_run(argv, capture_output=True, text=True):
            calls.append(list(argv))
            pattern = str(argv[-1])
            stdout = "123\n" if pattern == str(qa_suite_runner.APP_BUNDLE_MAIN) else ""
            returncode = 0 if stdout else 1
            return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

        import subprocess

        with patch("tools.qa_suite_runner.subprocess.run", side_effect=_fake_run):
            pids = qa_suite_runner._main_app_pids()

        self.assertEqual(pids, [123])
        searched_patterns = [call[-1] for call in calls]
        self.assertIn(str(qa_suite_runner.APP_BUNDLE_MAIN), searched_patterns)

    def test_wait_for_pids_exit_treats_non_alive_restart_pid_as_finished(self):
        with patch("tools.qa_suite_runner._pid_alive_for_restart", return_value=False):
            self.assertTrue(qa_suite_runner._wait_for_pids_exit([123], timeout_sec=0.5))

    def test_resolve_editor_compact_diamond_drops_stale_line_when_status_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.qa_suite_runner._app_status", return_value=(1, {"ok": False, "error": "app_unreachable"})):
                command, details = qa_suite_runner._resolve_editor_compact_diamond_command(
                    "editor-move-diamond",
                    "right",
                    qa_suite_runner.DEFAULT_PYTHON,
                    output_dir=Path(tmp),
                )

        self.assertEqual(command, ["editor-move-diamond", "--side", "closest"])
        self.assertFalse(details["status_ok"])
        self.assertEqual(details["pair"], {})

    def test_resolve_editor_compact_diamond_uses_boundary_when_status_has_pair(self):
        payload = {
            "ok": True,
            "data": {
                "editor_runtime": {
                    "diamond_right": {"side": "right", "boundary_sec": 12.345},
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.qa_suite_runner._app_status", return_value=(0, payload)):
                command, details = qa_suite_runner._resolve_editor_compact_diamond_command(
                    "editor-merge-diamond",
                    "right",
                    qa_suite_runner.DEFAULT_PYTHON,
                    output_dir=Path(tmp),
                )

        self.assertEqual(command, ["editor-merge-diamond", "--start-sec", "12.345", "--side", "right"])
        self.assertTrue(details["status_ok"])


if __name__ == "__main__":
    unittest.main()
