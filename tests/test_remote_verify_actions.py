import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tools.remote_verify as remote_verify


def _args(tmp: str, actions: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        output_dir=tmp,
        label="remote_verify_actions",
        open_media="",
        open_srt="",
        open_project="",
        timeout=1.0,
        snapshot_each_step=False,
        settle_sec=0.0,
        playhead_sec=None,
        playhead_center=False,
        no_sync_video=False,
        select_line=None,
        select_start_sec=None,
        select_at_playhead=False,
        select_center=False,
        select_sync_playhead=False,
        cursor_pos=None,
        diamond_side="closest",
        actions=actions,
    )


class RemoteVerifyActionTests(unittest.TestCase):
    def test_editor_sequence_maps_play_pause_and_save_actions(self):
        recorded: list[dict] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append({"name": step_name, **kwargs})
            report.setdefault("steps", []).append({"name": step_name, "result": {"ok": True}})

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify._capture_status", return_value={"ok": True, "data": {}}):
                    with patch("tools.remote_verify._write_report_files", return_value=None):
                        exit_code = remote_verify._run_editor_sequence(
                            _args(tmp, ["play", "pause", "save-project"])
                        )

        self.assertEqual(exit_code, 0)
        commands = [item for item in recorded if item.get("command")]
        self.assertEqual([item["command"] for item in commands], ["editor-playback", "editor-playback", "save-project"])
        self.assertEqual(commands[0]["options"], {"action": "play"})
        self.assertEqual(commands[1]["options"], {"action": "pause"})
        self.assertEqual(commands[2].get("options", {}), {})

    def test_editor_sequence_maps_active_worker_control_actions(self):
        recorded: list[dict] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append({"name": step_name, **kwargs})
            report.setdefault("steps", []).append({"name": step_name, "result": {"ok": True}})

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify._capture_status", return_value={"ok": True, "data": {}}):
                    with patch("tools.remote_verify._write_report_files", return_value=None):
                        exit_code = remote_verify._run_editor_sequence(
                            _args(tmp, ["cancel-current-pipeline", "app-close-request", "app-quit-request"])
                        )

        self.assertEqual(exit_code, 0)
        commands = [item for item in recorded if item.get("command")]
        self.assertEqual(
            [item["command"] for item in commands],
            ["cancel-current-pipeline", "app-close-request", "app-quit-request"],
        )

    def test_editor_sequence_maps_generation_status_and_wait_actions(self):
        recorded: list[dict] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append({"name": step_name, **kwargs})
            report.setdefault("steps", []).append({"name": step_name, "result": {"ok": True}})

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify.time.sleep", return_value=None) as sleep_mock:
                    with patch("tools.remote_verify._capture_status", return_value={"ok": True, "data": {}}):
                        with patch("tools.remote_verify._write_report_files", return_value=None):
                            exit_code = remote_verify._run_editor_sequence(
                                _args(tmp, ["start-current-pipeline", "wait-1.5", "status-probe", "guided-status-probe"])
                            )

        self.assertEqual(exit_code, 0)
        sleep_mock.assert_called_once_with(1.5)
        commands = [item for item in recorded if item.get("command")]
        self.assertEqual(
            [item["command"] for item in commands],
            ["start-current-pipeline", "status", "guided-subtitle-status"],
        )

    def test_editor_sequence_maps_menu_dialog_stt_and_lora_actions(self):
        recorded: list[dict] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append({"name": step_name, **kwargs})
            report.setdefault("steps", []).append({"name": step_name, "result": {"ok": True}})

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify._capture_status", return_value={"ok": True, "data": {}}):
                    with patch("tools.remote_verify._write_report_files", return_value=None):
                        exit_code = remote_verify._run_editor_sequence(
                            _args(
                                tmp,
                                [
                                    "open-settings",
                                    "capture-active-dialog",
                                    "close-active-dialog",
                                    "stt-enable",
                                    "lora-run-now",
                                    "capture-dictionary",
                                ],
                            )
                        )

        self.assertEqual(exit_code, 0)
        commands = [item for item in recorded if item.get("command")]
        self.assertEqual(
            [item["command"] for item in commands],
            [
                "open-settings",
                "capture-active-dialog",
                "close-active-dialog",
                "editor-stt-mode",
                "personalization-idle",
                "capture-dictionary-snapshot",
            ],
        )
        self.assertEqual(commands[3]["options"], {"action": "enable"})
        self.assertEqual(commands[4]["options"], {"action": "run-now"})
        self.assertTrue(str(commands[1]["path"]).endswith("capture-active-dialog.png"))
        self.assertTrue(str(commands[5]["path"]).endswith("capture-dictionary.png"))

    def test_editor_sequence_maps_save_export_actions_with_artifact_paths_and_long_timeout(self):
        recorded: list[dict] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append({"name": step_name, **kwargs})
            report.setdefault("steps", []).append({"name": step_name, "result": {"ok": True}})

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify._capture_status", return_value={"ok": True, "data": {}}):
                    with patch("tools.remote_verify._write_report_files", return_value=None):
                        exit_code = remote_verify._run_editor_sequence(
                            _args(tmp, ["save-subtitles", "export-subtitles", "export-subtitle-video"])
                        )

        self.assertEqual(exit_code, 0)
        commands = [item for item in recorded if item.get("command")]
        self.assertEqual([item["command"] for item in commands], ["save-subtitles", "export-subtitles", "export-subtitle-video"])
        self.assertTrue(str(commands[1]["path"]).endswith("manual_export.srt"))
        self.assertGreaterEqual(commands[0]["timeout"], 60.0)
        self.assertGreaterEqual(commands[1]["timeout"], 60.0)
        self.assertGreaterEqual(commands[2]["timeout"], 240.0)

    def test_capture_snapshot_requires_saved_file_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing.png"

            with patch(
                "tools.remote_verify._send",
                return_value={"ok": True, "message": "snapshot_queued", "data": {"path": str(target)}},
            ):
                result = remote_verify._capture_snapshot(Path(tmp), "missing", timeout=0.1)

        self.assertFalse(result["ok"])
        self.assertFalse(result["path_exists"])
        self.assertEqual(result["path_size"], 0)

    def test_editor_sequence_step_caps_post_status_and_snapshot_probe_timeouts(self):
        report: dict = {"steps": []}
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch("tools.remote_verify._capture_status", return_value={"ok": True}) as status_mock:
                with patch("tools.remote_verify._send", return_value={"ok": True, "data": {}}) as send_mock:
                    with patch(
                        "tools.remote_verify._capture_snapshot",
                        return_value={"ok": False, "path_exists": False, "path_size": 0},
                    ) as snapshot_mock:
                        with patch("tools.remote_verify._write_report_files") as write_mock:
                            remote_verify._record_step(
                                report,
                                output_dir,
                                "export-video",
                                timeout=240.0,
                                snapshot=True,
                                command="export-subtitle-video",
                            )

        self.assertEqual(send_mock.call_args.kwargs["timeout"], 240.0)
        self.assertEqual([call.args[0] for call in status_mock.call_args_list], [4.0, 4.0])
        self.assertEqual(snapshot_mock.call_args.kwargs["timeout"], 8.0)
        write_mock.assert_called_once()

    def test_editor_sequence_aborts_after_open_media_app_unreachable(self):
        recorded: list[str] = []

        def _fake_record_step(report, output_dir, step_name, **kwargs):
            recorded.append(step_name)
            entry = {
                "name": step_name,
                "command": kwargs.get("command", ""),
                "result": {"ok": False, "error": "app_unreachable"},
            }
            report.setdefault("steps", []).append(entry)
            return entry

        with tempfile.TemporaryDirectory() as tmp:
            args = _args(tmp, ["save-subtitles", "export-subtitles"])
            args.open_media = "/tmp/media.mp4"
            with patch("tools.remote_verify._record_step", side_effect=_fake_record_step):
                with patch("tools.remote_verify._capture_status", return_value={"ok": False}):
                    with patch("tools.remote_verify._write_report_files") as write_mock:
                        exit_code = remote_verify._run_editor_sequence(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual(recorded, ["open"])
        write_mock.assert_called_once()

    def test_export_subtitle_video_step_validates_returned_mov_artifact(self):
        report: dict = {"steps": []}
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            mov_path = output_dir / "manual_export.mov"
            mov_path.write_bytes(b"mov")

            def _fake_send(command, **kwargs):
                if command == "export-subtitle-video":
                    return {
                        "ok": True,
                        "data": {"outputs": [{"mov_output": {"path": str(mov_path)}}]},
                    }
                return {"ok": True, "data": {}}

            with patch("tools.remote_verify._capture_status", return_value={"ok": True}):
                with patch("tools.remote_verify._send", side_effect=_fake_send):
                    with patch("tools.remote_verify._write_report_files"):
                        remote_verify._record_step(
                            report,
                            output_dir,
                            "export-subtitle-video",
                            timeout=1.0,
                            snapshot=False,
                            command="export-subtitle-video",
                        )

        entry = report["steps"][0]
        self.assertTrue(entry["result"]["ok"])
        self.assertEqual(entry["artifacts"][0]["path"], str(mov_path))
        self.assertEqual(entry["artifacts"][0]["path_size"], 3)

    def test_live_nle_proof_accepts_pre_final_compact_runtime_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            data = {
                "editor_state": "ST_PROC",
                "backend_active": True,
                "nle_runtime_track_counts": {
                    "VAD": 2,
                    "STT1": 1,
                    "STT2": 1,
                    "subtitle_preview": 1,
                    "final": 0,
                },
                "nle_runtime_tracks": {
                    "compact_payload": True,
                    "counts": {"VAD": 2, "STT1": 1, "STT2": 1, "subtitle_preview": 1, "final": 0},
                    "tracks": {
                        "VAD": {"count": 2, "authoritative_for_save_export": False},
                        "STT1": {"count": 1, "authoritative_for_save_export": False},
                        "STT2": {"count": 1, "authoritative_for_save_export": False},
                        "subtitle_preview": {"count": 1, "authoritative_for_save_export": False},
                        "final": {"count": 0, "authoritative_for_save_export": True},
                    },
                },
                "runtime_resource": {
                    "live_nle_projection_budget": {
                        "dedicated_worker_count": 0,
                        "max_projection_workers": 0,
                        "shares_subtitle_worker_pool": False,
                        "uses_existing_row_snapshots": True,
                        "coalesces_updates": True,
                        "drops_stale_preview_frames": True,
                        "quality_policy": "final_authority_unchanged",
                    }
                },
            }
            samples = [
                remote_verify._live_nle_sample_from_status(
                    {"ok": True, "data": data},
                    elapsed_sec=1.25,
                    latency_sec=0.03,
                    poll_index=0,
                ),
                remote_verify._live_nle_sample_from_status(
                    {"ok": True, "data": data},
                    elapsed_sec=2.25,
                    latency_sec=0.02,
                    poll_index=1,
                ),
                remote_verify._live_nle_sample_from_status(
                    {
                        "ok": True,
                        "data": {
                            **data,
                            "editor_state": "READY",
                            "backend_active": False,
                            "auto_processing_active": False,
                            "guided_snapshot_run": {"active": False, "last_stage_key": "completed"},
                        },
                    },
                    elapsed_sec=3.25,
                    latency_sec=0.02,
                    poll_index=2,
                ),
            ]

            report = remote_verify._build_live_nle_runtime_proof_report(
                media_path="/tmp/demo.mp4",
                output_dir=output_dir,
                start_result={"ok": True},
                samples=samples,
                snapshot_dir=output_dir / "snapshots",
                started_at="start",
                ended_at="end",
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(sorted(report["observed_pre_final_tracks"]), ["STT1", "STT2", "VAD"])
        self.assertEqual(report["pre_final_observation_counts"], {"VAD": 2, "STT1": 2, "STT2": 2})
        self.assertTrue(report["generation_completed"])
        self.assertEqual(report["issues"], [])

    def test_live_nle_sample_does_not_infer_completion_from_cached_timeout_status(self):
        sample = remote_verify._live_nle_sample_from_status(
            {
                "ok": True,
                "data": {
                    "status_handler_timeout": True,
                    "status_response_cached": True,
                    "editor_state": "",
                    "backend_active": False,
                    "auto_processing_active": False,
                    "guided_snapshot_run": {"active": False},
                    "nle_runtime_track_counts": {"VAD": 1, "STT1": 1, "STT2": 0},
                    "runtime_resource": {
                        "live_nle_projection_budget": {
                            "dedicated_worker_count": 0,
                            "max_projection_workers": 0,
                            "shares_subtitle_worker_pool": False,
                            "uses_existing_row_snapshots": True,
                            "coalesces_updates": True,
                            "drops_stale_preview_frames": True,
                            "quality_policy": "final_authority_unchanged",
                        }
                    },
                },
            },
            elapsed_sec=4.0,
            latency_sec=0.01,
            poll_index=3,
        )

        self.assertFalse(sample["generation_completed"])
        self.assertFalse(sample["pre_final_active"])
        self.assertTrue(sample["status_handler_timeout"])
        self.assertTrue(sample["status_response_cached"])

    def test_live_nle_proof_blocks_single_pre_final_observation_per_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            sample = remote_verify._live_nle_sample_from_status(
                {
                    "ok": True,
                    "data": {
                        "editor_state": "ST_PROC",
                        "backend_active": True,
                        "nle_runtime_track_counts": {
                            "VAD": 5,
                            "STT1": 4,
                            "STT2": 3,
                            "subtitle_preview": 1,
                            "final": 0,
                        },
                        "nle_runtime_tracks": {
                            "compact_payload": True,
                            "counts": {"VAD": 5, "STT1": 4, "STT2": 3, "subtitle_preview": 1, "final": 0},
                            "tracks": {
                                "VAD": {"count": 5, "authoritative_for_save_export": False},
                                "STT1": {"count": 4, "authoritative_for_save_export": False},
                                "STT2": {"count": 3, "authoritative_for_save_export": False},
                                "subtitle_preview": {"count": 1, "authoritative_for_save_export": False},
                                "final": {"count": 0, "authoritative_for_save_export": True},
                            },
                        },
                        "runtime_resource": {
                            "live_nle_projection_budget": {
                                "dedicated_worker_count": 0,
                                "max_projection_workers": 0,
                                "shares_subtitle_worker_pool": False,
                                "uses_existing_row_snapshots": True,
                                "coalesces_updates": True,
                                "drops_stale_preview_frames": True,
                                "quality_policy": "final_authority_unchanged",
                            }
                        },
                    },
                },
                elapsed_sec=1.0,
                latency_sec=0.01,
                poll_index=0,
            )

            report = remote_verify._build_live_nle_runtime_proof_report(
                media_path="/tmp/demo.mp4",
                output_dir=output_dir,
                start_result={"ok": True},
                samples=[sample],
                snapshot_dir=output_dir / "snapshots",
                started_at="start",
                ended_at="end",
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["pre_final_observation_counts"], {"VAD": 1, "STT1": 1, "STT2": 1})
        self.assertIn("insufficient_pre_final_observations:VAD,STT1,STT2", report["issues"])

    def test_live_nle_proof_does_not_count_completed_samples_as_pre_final_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            base_data = {
                "nle_runtime_track_counts": {
                    "VAD": 2,
                    "STT1": 2,
                    "STT2": 2,
                    "subtitle_preview": 1,
                    "final": 1,
                },
                "nle_runtime_tracks": {
                    "compact_payload": True,
                    "counts": {"VAD": 2, "STT1": 2, "STT2": 2, "subtitle_preview": 1, "final": 1},
                    "tracks": {
                        "VAD": {"count": 2, "authoritative_for_save_export": False},
                        "STT1": {"count": 2, "authoritative_for_save_export": False},
                        "STT2": {"count": 2, "authoritative_for_save_export": False},
                        "subtitle_preview": {"count": 1, "authoritative_for_save_export": False},
                        "final": {"count": 1, "authoritative_for_save_export": True},
                    },
                },
                "runtime_resource": {
                    "live_nle_projection_budget": {
                        "dedicated_worker_count": 0,
                        "max_projection_workers": 0,
                        "shares_subtitle_worker_pool": False,
                        "uses_existing_row_snapshots": True,
                        "coalesces_updates": True,
                        "drops_stale_preview_frames": True,
                        "quality_policy": "final_authority_unchanged",
                    }
                },
            }
            pre_final = remote_verify._live_nle_sample_from_status(
                {"ok": True, "data": {**base_data, "editor_state": "ST_PROC", "backend_active": True}},
                elapsed_sec=1.0,
                latency_sec=0.01,
                poll_index=0,
            )
            completed = remote_verify._live_nle_sample_from_status(
                {
                    "ok": True,
                    "data": {
                        **base_data,
                        "editor_state": "READY",
                        "backend_active": False,
                        "guided_snapshot_run": {"active": False, "last_stage_key": "completed"},
                    },
                },
                elapsed_sec=2.0,
                latency_sec=0.01,
                poll_index=1,
            )

            report = remote_verify._build_live_nle_runtime_proof_report(
                media_path="/tmp/demo.mp4",
                output_dir=output_dir,
                start_result={"ok": True},
                samples=[pre_final, completed],
                snapshot_dir=output_dir / "snapshots",
                started_at="start",
                ended_at="end",
            )

        self.assertTrue(report["generation_completed"])
        self.assertEqual(report["pre_final_observation_counts"], {"VAD": 1, "STT1": 1, "STT2": 1})
        self.assertIn("insufficient_pre_final_observations:VAD,STT1,STT2", report["issues"])

    def test_live_nle_proof_blocks_raw_payload_and_final_authority_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            sample = remote_verify._live_nle_sample_from_status(
                {
                    "ok": True,
                    "data": {
                        "editor_state": "ST_PROC",
                        "backend_active": True,
                        "nle_runtime_track_counts": {
                            "VAD": 1,
                            "STT1": 1,
                            "STT2": 0,
                            "subtitle_preview": 0,
                            "final": 0,
                        },
                        "nle_runtime_tracks": {
                            "compact_payload": False,
                            "tracks": {
                                "STT1": {
                                    "count": 1,
                                    "authoritative_for_save_export": True,
                                    "segments": [{"text": "raw stt leaked"}],
                                },
                                "final": {"count": 0, "authoritative_for_save_export": True},
                            },
                        },
                        "runtime_resource": {
                            "live_nle_projection_budget": {
                                "dedicated_worker_count": 1,
                                "max_projection_workers": 1,
                                "shares_subtitle_worker_pool": True,
                                "uses_existing_row_snapshots": False,
                                "coalesces_updates": False,
                                "drops_stale_preview_frames": False,
                                "quality_policy": "changed",
                            }
                        },
                    },
                },
                elapsed_sec=2.0,
                latency_sec=0.04,
            )

            report = remote_verify._build_live_nle_runtime_proof_report(
                media_path="/tmp/demo.mp4",
                output_dir=output_dir,
                start_result={"ok": True},
                samples=[sample],
                snapshot_dir=output_dir / "snapshots",
                started_at="start",
                ended_at="end",
            )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("missing_pre_final_tracks:STT2", report["issues"])
        self.assertIn("raw_runtime_payload_leak", report["issues"])
        self.assertIn("compact_runtime_payload_contract_failed", report["issues"])
        self.assertIn("final_authority_contract_failed", report["issues"])
        self.assertIn("live_projection_budget_contract_failed", report["issues"])

    def test_live_nle_proof_writes_redacted_summary_and_samples_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            report = {
                "status": "passed",
                "media_path": "/tmp/demo.mp4",
                "output_dir": str(output_dir),
                "snapshot_dir": str(output_dir / "snapshots"),
                "started_at": "start",
                "ended_at": "end",
                "sample_count": 1,
                "generation_completed": True,
                "required_tracks": ["VAD", "STT1", "STT2"],
                "min_pre_final_observations": 2,
                "pre_final_observation_counts": {"VAD": 2, "STT1": 2, "STT2": 2},
                "observed_pre_final_tracks": {
                    "VAD": {"first_elapsed_sec": 1.0, "last_elapsed_sec": 2.0, "observation_count": 2, "max_count": 1, "stage": "vad"},
                    "STT1": {"first_elapsed_sec": 1.0, "last_elapsed_sec": 2.0, "observation_count": 2, "max_count": 1, "stage": "stt"},
                    "STT2": {"first_elapsed_sec": 1.0, "last_elapsed_sec": 2.0, "observation_count": 2, "max_count": 1, "stage": "stt2"},
                },
                "issues": [],
                "raw_payload_leak_elapsed_sec": [],
                "compact_payload_failure_elapsed_sec": [],
                "final_authority_failure_elapsed_sec": [],
                "budget_failure_elapsed_sec": [],
                "snapshot_files": [],
                "samples": [{"large": "sample"}],
                "notes": ["runtime proof only"],
            }

            remote_verify._write_live_nle_runtime_proof(output_dir, report)

            summary = (output_dir / "live_nle_runtime_proof.json").read_text(encoding="utf-8")
            samples = (output_dir / "status_samples.json").read_text(encoding="utf-8")
            jsonl_samples = (output_dir / "observability_samples.jsonl").read_text(encoding="utf-8")
            md = (output_dir / "live_nle_runtime_proof.md").read_text(encoding="utf-8")

        self.assertNotIn('"samples"', summary)
        self.assertIn('"large": "sample"', samples)
        self.assertIn('"large": "sample"', jsonl_samples)
        self.assertEqual(len([line for line in jsonl_samples.splitlines() if line.strip()]), 1)
        self.assertIn("| VAD | yes | 2 | 1.0 | 2.0 | 1 | vad |", md)


if __name__ == "__main__":
    unittest.main()
