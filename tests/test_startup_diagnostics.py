import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.pipeline.startup_diagnostics import (
    STARTUP_DIAGNOSTIC_SCHEMA,
    build_startup_diagnostic,
    format_startup_diagnostic_log,
    persist_startup_diagnostic,
)


class StartupDiagnosticsTests(unittest.TestCase):
    @patch("core.pipeline.startup_diagnostics.probe_audio_stream_info")
    @patch("core.pipeline.startup_diagnostics.probe_media")
    def test_builds_precise_profile_from_media_audio_and_cut_density(self, mock_media, mock_audio):
        mock_media.return_value = {
            "duration": 1450.249,
            "width": 3840,
            "height": 2160,
            "fps": 59.94,
            "info_txt": "3840x2160 (59.94fps)",
            "len_txt": "24:10",
        }
        mock_audio.return_value = {
            "has_audio": True,
            "codec": "aac",
            "sample_rate": 48000,
            "channels": 2,
            "bit_rate": 160000,
            "duration_sec": 1450.249,
        }

        diagnostic = build_startup_diagnostic(
            "/tmp/source/틴니핑.MP4",
            settings={"max_speakers": 2},
            cut_boundaries=[{"timeline_sec": 120.0}, {"timeline_sec": 300.0}],
            provisional_cut_boundaries=[{"timeline_sec": 180.0}],
            expected_time_sec=321.0,
        )

        self.assertEqual(diagnostic["schema"], STARTUP_DIAGNOSTIC_SCHEMA)
        self.assertEqual(diagnostic["media"]["duration_label"], "24:10")
        self.assertEqual(diagnostic["audio"]["quality"]["label"], "green")
        self.assertEqual(diagnostic["speakers"]["count"], 2)
        self.assertEqual(diagnostic["cut_density"]["verified_count"], 2)
        self.assertEqual(diagnostic["cut_density"]["provisional_count"], 1)
        self.assertEqual(diagnostic["recommended_pipeline"]["mode"], "precise")
        self.assertEqual(diagnostic["estimated_processing_label"], "5분 21초")

        lines = format_startup_diagnostic_log(diagnostic)
        self.assertTrue(any("정밀 모드" in line for line in lines))
        self.assertTrue(any("24:10" in line for line in lines))

    @patch("core.pipeline.startup_diagnostics.probe_audio_stream_info")
    @patch("core.pipeline.startup_diagnostics.probe_media")
    def test_recovery_profile_when_duration_or_audio_is_missing(self, mock_media, mock_audio):
        mock_media.return_value = {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "info_txt": "오디오 파일",
            "len_txt": "-",
        }
        mock_audio.return_value = {
            "has_audio": False,
            "codec": "",
            "sample_rate": 0,
            "channels": 0,
            "bit_rate": 0,
            "duration_sec": 0.0,
        }

        diagnostic = build_startup_diagnostic("/tmp/broken.mp4")

        self.assertEqual(diagnostic["recommended_pipeline"]["mode"], "recovery")
        self.assertEqual(diagnostic["audio"]["quality"]["summary"], "오디오 없음")
        self.assertEqual(diagnostic["estimated_processing_label"], "예상불가")

    def test_persist_startup_diagnostic_updates_project_analysis_locations(self):
        diagnostic = {
            "schema": STARTUP_DIAGNOSTIC_SCHEMA,
            "media_name": "clip.mp4",
            "recommended_pipeline": {"mode": "balanced", "label": "균형 모드"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "project.json")
            with open(project_path, "w", encoding="utf-8") as handle:
                json.dump({"analysis": {"old": True}, "editor_state": {"analysis": {}}}, handle)

            self.assertTrue(persist_startup_diagnostic(project_path, diagnostic))

            with open(project_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertTrue(saved["analysis"]["old"])
            self.assertEqual(saved["analysis"]["startup_diagnostic"], diagnostic)
            self.assertEqual(saved["editor_state"]["analysis"]["startup_diagnostic"], diagnostic)


if __name__ == "__main__":
    unittest.main()
