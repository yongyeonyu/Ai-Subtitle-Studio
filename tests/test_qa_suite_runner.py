import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.qa_suite_runner as qa_suite_runner


class QASuiteRunnerTests(unittest.TestCase):
    def test_build_scenarios_major_includes_core_macau_sequences(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa_suite_runner, "MACAU_MEDIA", Path(tmp) / "missing.mp4"):
                scenarios = qa_suite_runner.build_scenarios("major", Path(tmp))

        self.assertEqual(
            [item["id"] for item in scenarios],
            [
                "editor_compact_macau",
                "video_menu_macau",
                "save_export_macau",
                "menu_stt_lora_macau",
                "roughcut_reopen_macau",
                "roughcut_interaction_macau",
                "roughcut_candidate_macau",
                "roughcut_release_audit_macau",
            ],
        )

    def test_build_scenarios_major_includes_release_style_roughcut_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa_suite_runner, "MACAU_MEDIA", Path(tmp) / "missing.mp4"):
                scenarios = qa_suite_runner.build_scenarios("major", Path(tmp))

        spec = next(item for item in scenarios if item["id"] == "roughcut_release_audit_macau")
        self.assertEqual(spec["type"], "app_sequence")
        step_names = [step["name"] for step in spec["steps"]]
        self.assertEqual(
            step_names,
            [
                "open_project",
                "open_roughcut",
                "status_ready",
                "select_candidate_draft",
                "thumbnail_preview_proxy",
                "move_chapter_down",
                "save_project",
                "reopen_project",
                "status_after_reopen",
                "roughcut_export_srt",
                "capture_release_audit",
            ],
        )
        export_step = next(step for step in spec["steps"] if step["name"] == "roughcut_export_srt")
        self.assertIn("roughcut_release_audit_export.srt", export_step["command"][-1])

    def test_build_scenarios_full_adds_x5_rolling_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(qa_suite_runner, "MACAU_MEDIA", Path(tmp) / "missing.mp4"):
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
                    with patch.object(qa_suite_runner, "MACAU_MEDIA", Path(tmp) / "missing.mp4"):
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
                    with patch.object(qa_suite_runner, "MACAU_MEDIA", Path(tmp) / "missing.mp4"):
                        exit_code = qa_suite_runner.run_suite("quick", output_dir, qa_suite_runner.DEFAULT_PYTHON)

            summary = json.loads((output_dir / "suite_result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["app_bootstrap"]["status"]["error"], "app_unreachable")
        run_scenario.assert_not_called()

    def test_run_suite_resolves_relative_output_dir_against_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(qa_suite_runner, "ROOT", root), patch.object(
                qa_suite_runner,
                "MACAU_MEDIA",
                root / "missing.mp4",
            ), patch(
                "tools.qa_suite_runner._ensure_app_ready",
                return_value={"ok": False, "started_app": False, "status": {"ok": False}},
            ):
                exit_code = qa_suite_runner.run_suite("quick", Path("relative_suite"), qa_suite_runner.DEFAULT_PYTHON)

            resolved_output_dir = (root / "relative_suite").resolve()
            summary_path = resolved_output_dir / "suite_result.json"
            summary_exists = summary_path.is_file()
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertTrue(summary_exists)
        self.assertEqual(summary["output_dir"], str(resolved_output_dir))

    def test_macau_project_for_suite_copies_existing_project_to_output_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "macau.aissproj"
            project_path.write_text("{}", encoding="utf-8")
            assets_dir = Path(tmp) / "macau.assets" / "subtitles"
            assets_dir.mkdir(parents=True)
            (assets_dir / "final.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n안녕\n", encoding="utf-8")
            output_root = Path(tmp) / "suite"
            with patch.object(qa_suite_runner, "MACAU_PROJECT", project_path), patch(
                "core.project.project_manager.create_project"
            ) as create_project:
                resolved = qa_suite_runner._macau_project_for_suite(output_root)

            self.assertEqual(resolved, output_root / "_suite_fixtures" / project_path.name)
            self.assertEqual(resolved.read_text(encoding="utf-8"), "{}")
            self.assertTrue((output_root / "_suite_fixtures" / "macau.assets" / "subtitles" / "final.srt").is_file())
            create_project.assert_not_called()

    def test_macau_project_for_suite_creates_output_fixture_when_default_project_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_path = root / "DJI_20260217224203_0075_D.MP4"
            media_path.write_bytes(b"media")
            srt_path = root / "DJI_20260217224203_0075_D_화자.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n안녕\n", encoding="utf-8")
            missing_project = root / "projects" / "DJI_20260217224203_0075_D.aissproj"
            output_root = root / "suite"
            created_project = output_root / "_suite_fixtures" / missing_project.name

            with patch.object(qa_suite_runner, "MACAU_PROJECT", missing_project), patch.object(
                qa_suite_runner,
                "MACAU_MEDIA",
                media_path,
            ), patch.object(
                qa_suite_runner,
                "MACAU_SRT_CANDIDATES",
                (srt_path,),
            ), patch(
                "core.project.project_manager.create_project",
                return_value=str(created_project),
            ) as create_project:
                scenarios = qa_suite_runner.build_scenarios("quick", output_root)

        open_project_step = scenarios[0]["steps"][0]
        self.assertEqual(open_project_step["command"], ["open-project", str(created_project)])
        create_project.assert_called_once()
        self.assertFalse(create_project.call_args.kwargs["prefill_analysis_artifacts"])
        self.assertEqual(create_project.call_args.kwargs["srt_path"], str(srt_path))

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

    def test_ensure_app_ready_accepts_ping_when_status_is_deferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "suite"
            fake_proc = type("P", (), {"pid": 4321})()
            with patch("tools.qa_suite_runner._app_status", side_effect=[(1, {"ok": False, "error": "app_unreachable"}), (1, {"ok": False, "error": "app_unreachable"})]), patch(
                "tools.qa_suite_runner._app_ping",
                side_effect=[(1, {"ok": False, "error": "app_unreachable"}), (0, {"ok": True, "message": "pong", "data": {"current_work_mode": "editor"}})],
            ), patch(
                "tools.qa_suite_runner.subprocess.Popen",
                return_value=fake_proc,
            ), patch("tools.qa_suite_runner.time.sleep", return_value=None), patch(
                "tools.qa_suite_runner.time.monotonic",
                side_effect=[0.0, 0.0],
            ):
                result = qa_suite_runner._ensure_app_ready(qa_suite_runner.DEFAULT_PYTHON, output_dir=output_dir)

        self.assertTrue(result["ok"])
        self.assertTrue(result["started_app"])
        self.assertEqual(result["pid"], 4321)
        self.assertEqual(result["status"]["data"]["readiness_probe"], "ping")
        self.assertTrue(result["status"]["data"]["status_deferred"])

    def test_app_launch_command_can_force_source_app(self):
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_QA_USE_SOURCE": "1"}):
            command = qa_suite_runner._app_launch_command(qa_suite_runner.DEFAULT_PYTHON)

        self.assertEqual(command, [str(qa_suite_runner.DEFAULT_PYTHON), str(qa_suite_runner.APP_MAIN)])

    def test_editor_compact_resolved_playhead_does_not_sync_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "editor_compact_macau"
            spec = {
                "id": "editor_compact_macau",
                "type": "app_sequence",
                "description": "",
                "output_dir": output_dir,
                "steps": [
                    {
                        "name": "set_playhead",
                        "command": ["editor-set-playhead", "1.5", "--center"],
                        "timeout": 30.0,
                    }
                ],
            }
            with patch(
                "tools.qa_suite_runner._resolve_editor_compact_playhead",
                return_value=(12.345, {"status_ok": True}),
            ), patch(
                "tools.qa_suite_runner._run_subprocess",
                return_value=(0, {"ok": True, "message": "editor_playhead_set"}),
            ) as run_subprocess:
                result = qa_suite_runner._run_app_sequence(spec, qa_suite_runner.DEFAULT_PYTHON)

        self.assertTrue(result["ok"])
        argv = run_subprocess.call_args.args[0]
        self.assertIn("--no-sync-video", argv)
        self.assertLess(argv.index("--center"), argv.index("--no-sync-video"))

    def test_resolve_editor_compact_playhead_uses_status_playhead_when_active_is_stale(self):
        payload = {
            "ok": True,
            "data": {
                "editor_runtime": {
                    "playhead_sec": 175.766667,
                    "total_duration": 178.833333,
                    "active_segment": {"start": 0.0, "end": 1.166667},
                    "next_segment": {"start": 1.533333, "end": 4.766667},
                    "previous_segment": {},
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.qa_suite_runner._app_status", return_value=(0, payload)):
                candidate, details = qa_suite_runner._resolve_editor_compact_playhead(
                    qa_suite_runner.DEFAULT_PYTHON,
                    output_dir=Path(tmp),
                )

        self.assertEqual(candidate, 175.7667)
        self.assertEqual(details["selected_from"], "status_playhead")

    def test_run_app_sequence_rejects_expect_data_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "roughcut_reopen_macau"
            spec = {
                "id": "roughcut_reopen_macau",
                "type": "app_sequence",
                "description": "",
                "output_dir": output_dir,
                "steps": [
                    {
                        "name": "status_after_reopen",
                        "command": ["status"],
                        "timeout": 30.0,
                        "expect_data": {"current_work_mode": "roughcut"},
                    }
                ],
            }
            with patch(
                "tools.qa_suite_runner._run_subprocess",
                return_value=(0, {"ok": True, "message": "status", "data": {"current_work_mode": "editor"}}),
            ):
                result = qa_suite_runner._run_app_sequence(spec, qa_suite_runner.DEFAULT_PYTHON)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_step"], "status_after_reopen")
        self.assertEqual(result["steps"][0]["error"], "expected_data_mismatch:current_work_mode")

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
                    "diamond_right": {
                        "side": "right",
                        "boundary_sec": 12.345,
                        "left": {"start": 10.0},
                        "right": {"start": 12.345},
                    },
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

        self.assertEqual(command, ["editor-merge-diamond", "--start-sec", "10.0", "--side", "right"])
        self.assertTrue(details["status_ok"])
        self.assertEqual(details["selected_start"], "10.0")

    def test_editor_compact_diamond_prefers_previous_runtime_pair_over_stale_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "editor_compact_macau"
            spec = {
                "id": "editor_compact_macau",
                "type": "app_sequence",
                "description": "",
                "output_dir": output_dir,
                "steps": [
                    {
                        "name": "move_segment_right",
                        "command": ["editor-move-segment-right", "--line", "1"],
                        "timeout": 30.0,
                    },
                    {
                        "name": "move_diamond",
                        "command": ["editor-move-diamond", "--line", "1", "--side", "right"],
                        "timeout": 30.0,
                    },
                ],
            }
            previous_runtime = {
                "diamond_right": {
                    "side": "right",
                    "boundary_sec": 13.6,
                    "left": {"start": 4.733333},
                    "right": {"start": 13.6},
                }
            }
            subprocess_results = [
                (0, {"ok": True, "message": "editor_segment_right_moved", "data": {"editor_runtime": previous_runtime}}),
                (0, {"ok": True, "message": "editor_diamond_moved", "data": {"editor_runtime": {}}}),
            ]
            with patch("tools.qa_suite_runner._app_status") as app_status, patch(
                "tools.qa_suite_runner._run_subprocess",
                side_effect=subprocess_results,
            ) as run_subprocess:
                result = qa_suite_runner._run_app_sequence(spec, qa_suite_runner.DEFAULT_PYTHON)

            resolved = json.loads((output_dir / "logs" / "move_diamond_resolved.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        second_argv = run_subprocess.call_args_list[1].args[0]
        self.assertNotIn("--start-sec", second_argv)
        self.assertEqual(second_argv[-2:], ["--side", "closest"])
        self.assertEqual(resolved["runtime_source"], "previous_step:move_segment_right")
        self.assertEqual(resolved["selected_start"], "4.733333")
        app_status.assert_not_called()

    def test_resolve_editor_compact_left_diamond_selects_right_segment_start(self):
        payload = {
            "ok": True,
            "data": {
                "editor_runtime": {
                    "diamond_left": {
                        "side": "left",
                        "boundary_sec": 21.0,
                        "left": {"start": 18.0},
                        "right": {"start": 21.0},
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.qa_suite_runner._app_status", return_value=(0, payload)):
                command, details = qa_suite_runner._resolve_editor_compact_diamond_command(
                    "editor-move-diamond",
                    "left",
                    qa_suite_runner.DEFAULT_PYTHON,
                    output_dir=Path(tmp),
                )

        self.assertEqual(command, ["editor-move-diamond", "--start-sec", "21.0", "--side", "left"])
        self.assertEqual(details["selected_start"], "21.0")


if __name__ == "__main__":
    unittest.main()
