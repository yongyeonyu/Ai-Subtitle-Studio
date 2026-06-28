import errno
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.runtime.trace_logger as trace_logger_module
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state
from core.project.project_io import clear_project_file_cache, read_project_file, write_project_file
from core.runtime.temp_workspace import (
    REQUIRED_SUBDIRECTORIES,
    TEMP_WORKSPACE_DIRNAME,
    cleanup_temp_workspace,
    ensure_temp_workspace,
    prune_temp_workspace,
    prune_trace_package_directories,
    prune_trace_run_directories,
    temp_workspace_root,
    workspace_usage,
)
from core.runtime.trace_logger import TraceLogger, initialize_app_trace, media_fingerprint, reset_app_trace_after_fork
from tools.audit_project_io_trace_contract import build_project_io_trace_report
from tools.collect_trace_package import collect_trace_package


def _jsonl_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class _FakeProjectTraceLogger:
    def __init__(self):
        self.events = []

    def log_event(self, event, **fields):
        self.events.append({"event": event, **fields})
        return True


def _trace_project_payload():
    return {
        "project_name": "trace project",
        "mode": "single",
        "video": {"duration_sec": 2.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {
                    "id": "subtitle_vector_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                    "speaker": "00",
                }
            ],
            primary_fps=30.0,
        ),
        NLE_PROJECT_STATE_RUNTIME_KEY: {"runtime_only": True},
    }


class TraceLoggerTests(unittest.TestCase):
    def setUp(self):
        trace_logger_module._APP_TRACE_LOGGER = None

    def tearDown(self):
        trace_logger_module._APP_TRACE_LOGGER = None

    def test_temp_workspace_creates_required_dirs_reports_usage_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            for relative in REQUIRED_SUBDIRECTORIES:
                self.assertTrue(paths[relative].exists(), relative)
            sample = Path(tmp) / "Diagnostics" / "Trace" / "sample.log"
            sample.write_bytes(b"x" * 64)

            usage = workspace_usage(tmp)
            self.assertEqual(usage["total_bytes"], 64)
            self.assertEqual(usage["file_count"], 1)

            cleanup = cleanup_temp_workspace(tmp)

            self.assertTrue(cleanup["removed"])
        self.assertFalse(Path(cleanup["root"]).exists())

    def test_default_temp_workspace_is_scoped_per_user_while_override_stays_exact(self):
        with patch("core.runtime.temp_workspace.tempfile.gettempdir", return_value="/tmp/aiss-temp"):
            root = temp_workspace_root()
        self.assertTrue(root.name.startswith(f"{TEMP_WORKSPACE_DIRNAME}-"))

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"AI_SUBTITLE_STUDIO_TEMP_WORKSPACE": tmp},
        ):
            self.assertEqual(temp_workspace_root(), Path(tmp))

    def test_prune_temp_workspace_removes_old_or_oversized_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            ensure_temp_workspace(tmp)
            old_file = Path(tmp) / "Diagnostics" / "Trace" / "old.log"
            new_file = Path(tmp) / "Diagnostics" / "Trace" / "new.log"
            old_file.write_bytes(b"x" * 64)
            new_file.write_bytes(b"y" * 64)
            os.utime(old_file, (100, 100))

            result = prune_temp_workspace(tmp, target_total_bytes=256, max_age_sec=1)

            self.assertGreaterEqual(result["removed_files"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_trace_logger_prunes_old_run_directories_before_creating_new_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            runs_dir = paths["Diagnostics/Trace/runs"]
            for index in range(24):
                run_dir = runs_dir / f"old-run-{index:02d}"
                run_dir.mkdir(parents=True)
                (run_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
                os.utime(run_dir, (100 + index, 100 + index))

            logger = TraceLogger(root=tmp, run_id="new-run")
            self.assertTrue(logger.close())
            run_dirs = sorted(path.name for path in runs_dir.iterdir() if path.is_dir())

        self.assertLessEqual(len(run_dirs), 20)
        self.assertIn("new-run", run_dirs)
        self.assertNotIn("old-run-00", run_dirs)
        self.assertIn("old-run-23", run_dirs)
        self.assertGreater(logger.retention_report["removed_count"], 0)

    def test_prune_trace_run_directories_keeps_newest_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            runs_dir = paths["Diagnostics/Trace/runs"]
            for index in range(5):
                run_dir = runs_dir / f"run-{index}"
                run_dir.mkdir(parents=True)
                os.utime(run_dir, (100 + index, 100 + index))

            result = prune_trace_run_directories(tmp, max_runs=2)
            remaining = sorted(path.name for path in runs_dir.iterdir() if path.is_dir())

        self.assertEqual(result["removed_count"], 3)
        self.assertEqual(remaining, ["run-3", "run-4"])

    def test_collect_trace_package_prunes_old_packages_and_keeps_current_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            packages_dir = paths["Diagnostics/Packages"]
            for index in range(5):
                package_dir = packages_dir / f"AISSTrace-old-{index}"
                package_dir.mkdir(parents=True)
                (package_dir / "package_manifest.json").write_text("{}\n", encoding="utf-8")
                os.utime(package_dir, (100 + index, 100 + index))
            logger = TraceLogger(root=tmp, run_id="package-source")
            self.assertTrue(logger.close())

            manifest = collect_trace_package(
                root=tmp,
                run_id=logger.run_id,
                package_name="AISSTrace-new",
                max_packages=2,
            )
            remaining = sorted(path.name for path in packages_dir.iterdir() if path.is_dir())
            saved_manifest = json.loads(
                (packages_dir / "AISSTrace-new" / "package_manifest.json").read_text(encoding="utf-8")
            )

        self.assertLessEqual(len(remaining), 2)
        self.assertIn("AISSTrace-new", remaining)
        self.assertNotIn("AISSTrace-old-0", remaining)
        self.assertGreater(int(manifest["package_retention"]["removed_count"]), 0)
        self.assertEqual(saved_manifest["package_retention"]["after_package_count"], len(remaining))

    def test_prune_trace_package_directories_keeps_newest_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            packages_dir = paths["Diagnostics/Packages"]
            for index in range(5):
                package_dir = packages_dir / f"AISSTrace-{index}"
                package_dir.mkdir(parents=True)
                os.utime(package_dir, (100 + index, 100 + index))

            result = prune_trace_package_directories(tmp, max_packages=2)
            remaining = sorted(path.name for path in packages_dir.iterdir() if path.is_dir())

        self.assertEqual(result["removed_count"], 3)
        self.assertEqual(remaining, ["AISSTrace-3", "AISSTrace-4"])

    def test_media_fingerprint_uses_bounded_identity_without_file_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "source.mov"
            media.write_bytes(b"0123456789")

            fingerprint = media_fingerprint(media, duration_sec=12.5, frame_count=750, fps=60000 / 1001)

        self.assertEqual(fingerprint["basename"], "source.mov")
        self.assertEqual(fingerprint["size"], 10)
        self.assertEqual(fingerprint["duration_sec"], 12.5)
        self.assertEqual(fingerprint["frame_count"], 750)
        self.assertEqual((fingerprint["fps_num"], fingerprint["fps_den"]), (60000, 1001))
        self.assertNotIn("sha256", fingerprint)

    def test_trace_logger_creates_manifest_latest_and_frame_precise_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"media")
            logger = TraceLogger(
                root=tmp,
                run_id="trace-case",
                media_path=media,
                media_duration_sec=465.849,
                media_frame_count=27923,
                fps=60000 / 1001,
                fps_num=60000,
                fps_den=1001,
                mode_settings={"mode": "High"},
                project_id="project-a",
            )
            ok = logger.log_event(
                "cut_boundary_candidate",
                stage="cut-boundary",
                level="DEBUG",
                frame=2677,
                time_sec=2677 / (60000 / 1001),
                fps=60000 / 1001,
            )
            self.assertTrue(logger.flush())

            manifest = json.loads(logger.manifest_path.read_text(encoding="utf-8"))
            events = _jsonl_rows(logger.events_path)
            latest = _jsonl_rows(logger.latest_path)

        self.assertTrue(ok)
        self.assertEqual(manifest["app_name"], "AI Subtitle Studio")
        self.assertEqual(manifest["app_version"], "04.00.18")
        self.assertEqual(manifest["media_fingerprint"]["basename"], "clip.mp4")
        self.assertEqual((manifest["media_fingerprint"]["fps_num"], manifest["media_fingerprint"]["fps_den"]), (60000, 1001))
        self.assertTrue(manifest["mode_settings_snapshot_hash"])
        self.assertEqual([row["event"] for row in events], ["trace_run_started", "cut_boundary_candidate"])
        self.assertEqual(events[-1]["frame"], 2677)
        self.assertEqual((events[-1]["fps_num"], events[-1]["fps_den"]), (60000, 1001))
        self.assertEqual(events[-1]["project_id"], "project-a")
        self.assertEqual([row["event"] for row in latest], ["cut_boundary_candidate"])

    def test_repeated_runs_do_not_collide_on_same_requested_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = TraceLogger(root=tmp, run_id="same-run")
            second = TraceLogger(root=tmp, run_id="same-run")

            self.assertNotEqual(first.run_id, second.run_id)
            self.assertTrue(first.run_dir.exists())
            self.assertTrue(second.run_dir.exists())

    def test_logger_write_failures_are_isolated_without_app_logger_recursion(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = TraceLogger(root=tmp, run_id="failure-case")
            with patch(
                "core.runtime.trace_logger._append_jsonl",
                side_effect=OSError(errno.ENOSPC, "No space left on device"),
            ):
                ok = logger.log_event("disk_full_case")
                flushed = logger.flush()

            after_disabled = logger.log_event("after_disabled")
            status = logger.status()

        self.assertTrue(ok)
        self.assertFalse(flushed)
        self.assertFalse(after_disabled)
        self.assertTrue(status["disabled"])
        self.assertIn("disk_full", status["drop_counts"])
        self.assertIn("disabled", status["drop_counts"])

    def test_logger_json_permission_queue_and_shutdown_failures_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.runtime.trace_logger._atomic_write_json", side_effect=PermissionError("denied")):
                denied_logger = TraceLogger(root=tmp, run_id="permission-case")
            self.assertTrue(denied_logger.status()["disabled"])
            self.assertIn("manifest_write_failed", denied_logger.status()["drop_counts"])

            json_logger = TraceLogger(root=tmp, run_id="json-case")
            with patch("core.runtime.trace_logger.dumps_json_bytes", side_effect=TypeError("bad json")):
                self.assertTrue(json_logger.log_event("json_case"))
                self.assertFalse(json_logger.flush())
            self.assertIn("json_serialization_failed", json_logger.status()["drop_counts"])

            overflow_logger = TraceLogger(root=tmp, run_id="overflow-case", max_events=2)
            self.assertTrue(overflow_logger.log_event("allowed"))
            self.assertFalse(overflow_logger.log_event("overflow"))
            self.assertIn("queue_overflow", overflow_logger.status()["drop_counts"])

            shutdown_logger = TraceLogger(root=tmp, run_id="shutdown-case")
            with patch.object(shutdown_logger, "log_event", side_effect=RuntimeError("flush failed")):
                self.assertFalse(shutdown_logger.close())
            self.assertIn("shutdown_flush_failed", shutdown_logger.status()["drop_counts"])

    def test_initialize_app_trace_creates_latest_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_STUDIO_TEMP_WORKSPACE": tmp,
                "AI_SUBTITLE_STUDIO_TRACE_ENABLED": "1",
            },
        ):
            logger = initialize_app_trace()

            self.assertIsNotNone(logger)
            self.assertTrue(logger.latest_path.exists())

    def test_fork_reset_discards_parent_app_trace_singleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = TraceLogger(root=tmp, run_id="fork-case")
            trace_logger_module._APP_TRACE_LOGGER = logger

            reset_app_trace_after_fork()

            self.assertIsNone(trace_logger_module._APP_TRACE_LOGGER)

    def test_collect_trace_package_copies_latest_manifest_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = TraceLogger(root=tmp, run_id="package-case")
            logger.log_event("sample_event", stage="runtime")
            self.assertTrue(logger.flush())

            manifest = collect_trace_package(root=tmp, run_id=logger.run_id, package_name="AISSTrace-test")
            package_dir = Path(manifest["package_dir"])

            self.assertTrue((package_dir / "latest.jsonl").exists())
            self.assertTrue((package_dir / "runs" / "package-case" / "manifest.json").exists())
            self.assertTrue((package_dir / "runs" / "package-case" / "events.jsonl").exists())
            self.assertTrue((package_dir / "package_manifest.json").exists())

    def test_project_file_open_and_save_emit_best_effort_trace_without_raw_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "trace-project.aissproj"
            fake_logger = _FakeProjectTraceLogger()
            with patch("core.runtime.trace_logger.current_app_trace_logger", return_value=fake_logger):
                write_project_file(str(project_path), _trace_project_payload())
                clear_project_file_cache(str(project_path))
                disk_loaded = read_project_file(str(project_path))
                cache_loaded = read_project_file(str(project_path))

        save_events = [row for row in fake_logger.events if row["event"] == "project_file_save"]
        open_events = [row for row in fake_logger.events if row["event"] == "project_file_open"]
        self.assertEqual(len(save_events), 1)
        self.assertEqual(len(open_events), 2)
        self.assertTrue(any(row["cache_hit"] is False for row in open_events))
        self.assertTrue(any(row["cache_hit"] is True for row in open_events))
        self.assertTrue(save_events[0]["storage_clean_nle_runtime"])
        self.assertEqual(save_events[0]["event_type"], "project_io_write")
        self.assertIn(save_events[0]["payload_codec"], {"msgpack", "json"})
        self.assertEqual(save_events[0]["payload_compression"], "none")
        self.assertGreaterEqual(save_events[0]["stripped_runtime_key_count"], 1)
        self.assertTrue(all(row["event_type"] == "project_io_read" for row in open_events))
        self.assertTrue(disk_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY))
        self.assertTrue(cache_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY))
        event_text = json.dumps(fake_logger.events, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(tmp, event_text)
        self.assertTrue(all("project_path" not in row for row in fake_logger.events))
        self.assertTrue(all(row.get("project_path_hash") for row in fake_logger.events))
        self.assertTrue(all(row.get("project_basename") == "trace-project.aissproj" for row in fake_logger.events))

    def test_project_io_trace_contract_audit_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_project_io_trace_report(output_dir=Path(tmp))

        self.assertTrue(report["passed"])
        self.assertEqual(report["save_event_count"], 1)
        self.assertEqual(report["disk_open_event_count"], 1)
        self.assertEqual(report["cache_hit_event_count"], 1)
        self.assertFalse(report["raw_path_leak"])
        self.assertTrue(report["storage_clean"])

    def test_collect_trace_package_trims_active_jsonl_partial_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = ensure_temp_workspace(tmp)
            run_dir = paths["Diagnostics/Trace/runs"] / "active-run"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text('{"ok": true}\n', encoding="utf-8")
            (run_dir / "events.jsonl").write_bytes(b'{"event":"complete"}\n{"event":"partial"')
            paths["Diagnostics/Trace"].joinpath("latest.jsonl").write_bytes(b'{"event":"latest"}\n{"event":"partial"')

            manifest = collect_trace_package(root=tmp, run_id="active-run", package_name="AISSTrace-partial")
            package_dir = Path(manifest["package_dir"])
            rows = _jsonl_rows(package_dir / "runs" / "active-run" / "events.jsonl")
            latest_rows = _jsonl_rows(package_dir / "latest.jsonl")

        self.assertEqual([row["event"] for row in rows], ["complete"])
        self.assertEqual([row["event"] for row in latest_rows], ["latest"])


if __name__ == "__main__":
    unittest.main()
