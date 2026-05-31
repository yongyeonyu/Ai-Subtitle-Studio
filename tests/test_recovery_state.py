import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.project.project_context import build_editor_state
from core.project.project_io import read_project_storage_payload
from core.project.project_manager import load_project, save_project
from core.project.recovery_state import (
    RECOVERY_CONTROLS_SCHEMA,
    RECOVERY_STATE_SCHEMA,
    build_recovery_checkpoint,
    build_recovery_controls,
    cache_artifact_is_stale,
    next_recovery_stage,
    recovery_state_is_stale,
    refresh_project_recovery_state,
)


class RecoveryStateTests(unittest.TestCase):
    def test_checkpoint_records_media_fingerprint_and_resume_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"first media bytes")

            state = build_recovery_checkpoint(
                media_path=str(media),
                project_path=str(Path(tmp) / "project.json"),
                stage="stt",
                status="saved",
                detail="stt blocks complete",
                segments=[{"start": 0.0, "end": 1.0, "text": "안녕"}],
                settings={"stt_quality_preset": "balanced"},
            )

            self.assertEqual(state["schema"], RECOVERY_STATE_SCHEMA)
            self.assertEqual(state["last_safe_stage"], "stt")
            self.assertEqual(next_recovery_stage(state), "subtitle_llm")
            self.assertEqual(state["segment_count"], 1)
            self.assertEqual(state["recovery_controls"]["schema"], RECOVERY_CONTROLS_SCHEMA)
            self.assertFalse(recovery_state_is_stale(state, str(media)))

            media.write_bytes(b"replacement media bytes")
            self.assertTrue(recovery_state_is_stale(state, str(media)))
            self.assertTrue(cache_artifact_is_stale({"fingerprint_digest": state["media"]["fingerprint_digest"]}, str(media)))

    def test_save_project_persists_recovery_state_and_load_marks_stale_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "sample.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"stable media")
            project_path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "test",
                        "phase": "test",
                        "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "editor_state": build_editor_state(mode="single", media_files=[], segments=[], primary_fps=30.0),
                        "workspace": {},
                        "user_settings": {"accuracy_graph_persist_enabled": False, "stt_lattice_persist_enabled": False},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 30.0}):
                save_project(
                    str(project_path),
                    media_paths=[str(media)],
                    segments=[{"start": 0.0, "end": 1.0, "text": "복구"}],
                    user_settings={"accuracy_graph_persist_enabled": False, "stt_lattice_persist_enabled": False},
                )
            saved = read_project_storage_payload(str(project_path))
            recovery = saved["analysis"]["recovery_state"]

            self.assertEqual(recovery["schema"], RECOVERY_STATE_SCHEMA)
            self.assertEqual(recovery["stage"], "save")
            self.assertEqual(recovery["resume_stage"], "export")
            self.assertEqual(recovery["media"]["path"], os.path.abspath(str(media)))
            self.assertEqual(saved["editor_state"]["analysis"]["recovery_state"]["media"]["fingerprint_digest"], recovery["media"]["fingerprint_digest"])

            loaded = load_project(str(project_path))
            self.assertFalse(loaded["analysis"]["recovery_state"]["stale"])
            self.assertTrue(loaded["analysis"]["recovery_state"]["can_resume"])

            media.write_bytes(b"different media replacement")
            stale_loaded = load_project(str(project_path))
            stale_state = stale_loaded["analysis"]["recovery_state"]

            self.assertTrue(stale_state["stale"])
            self.assertFalse(stale_state["cache_valid"])
            self.assertFalse(stale_state["can_resume"])
            self.assertEqual(stale_state["resume_stage"], "queued")
            self.assertEqual(stale_loaded["editor_state"]["analysis"]["recovery_state"]["resume_stage"], "queued")

    def test_tablet_recovery_controls_expose_large_pause_resume_cancel_actions(self):
        running = build_recovery_checkpoint(
            stage="stt",
            status="running",
            artifacts={"ui_profile": "tablet_landscape", "low_power": True},
        )
        controls = running["recovery_controls"]
        actions = {item["id"]: item for item in controls["actions"]}

        self.assertEqual(controls["profile"], "tablet")
        self.assertEqual(controls["touch_target"], 48)
        self.assertTrue(actions["pause"]["enabled"])
        self.assertFalse(actions["resume"]["enabled"])
        self.assertTrue(actions["cancel"]["enabled"])
        self.assertEqual(actions["foreground_safe"]["reason"], "low_power")

        paused_controls = build_recovery_controls(
            {"stage": "stt", "status": "paused", "last_safe_stage": "stt", "can_resume": True},
            tablet_profile=True,
            foreground_activity=True,
        )
        paused_actions = {item["id"]: item for item in paused_controls["actions"]}
        self.assertFalse(paused_actions["pause"]["enabled"])
        self.assertTrue(paused_actions["resume"]["enabled"])
        self.assertEqual(paused_actions["resume"]["resume_stage"], "subtitle_llm")

    def test_stale_recovery_refresh_disables_nested_resume_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"old media")
            state = build_recovery_checkpoint(
                media_path=str(media),
                stage="stt",
                status="paused",
                artifacts={"ui_profile": "tablet_landscape"},
            )
            before_actions = {item["id"]: item for item in state["recovery_controls"]["actions"]}
            self.assertTrue(before_actions["resume"]["enabled"])

            media.write_bytes(b"new media")
            project = {
                "analysis": {"recovery_state": state},
                "editor_state": {"analysis": {}},
                "media": [{"path": str(media)}],
            }

            refresh_project_recovery_state(project)
            refreshed = project["analysis"]["recovery_state"]
            actions = {item["id"]: item for item in refreshed["recovery_controls"]["actions"]}

            self.assertTrue(refreshed["stale"])
            self.assertFalse(refreshed["can_resume"])
            self.assertFalse(actions["resume"]["enabled"])
            self.assertEqual(refreshed["recovery_controls"]["profile"], "tablet")


if __name__ == "__main__":
    unittest.main()
