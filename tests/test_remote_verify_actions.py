import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
