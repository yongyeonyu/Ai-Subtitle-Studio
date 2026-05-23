import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tools.benchmark_tiniping_mode_search import (
    _adaptive_audio_profiles,
    _load_manual_seeds,
    _selected_modes,
)
from tools.subtitle_regression_pack import _extract_json_tail, _parse_regression_fixtures, _segment_artifact_summary
from tools.verify_full_media_pipeline import run_full_verification


class TinipingModeSearchTests(unittest.TestCase):
    def test_load_manual_seeds_accepts_mode_keyed_payload(self):
        payload = {
            "seeds": {
                "fast": [
                    {
                        "mode": "fast",
                        "primary_model": "stt1-fast",
                        "secondary_model": "stt2-fast",
                        "method": "stt1_only",
                        "run_llm": False,
                    }
                ],
                "auto": [
                    {
                        "mode": "auto",
                        "primary_model": "stt1-auto",
                        "secondary_model": "stt2-auto",
                        "method": "selective_ensemble",
                        "run_llm": False,
                    }
                ],
                "high": [
                    {
                        "mode": "high",
                        "primary_model": "stt1-high",
                        "secondary_model": "stt2-high",
                        "method": "selective_ensemble",
                        "run_llm": True,
                    }
                ],
            }
        }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "seeds.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            loaded = _load_manual_seeds(path)

        self.assertEqual(loaded["fast"][0].primary_model, "stt1-fast")
        self.assertEqual(loaded["auto"][0].method, "selective_ensemble")
        self.assertTrue(loaded["high"][0].run_llm)

    def test_parse_regression_fixtures_dedupes_in_order(self):
        fixtures = _parse_regression_fixtures("x5, macau, x5, tinyping_short")
        self.assertEqual(fixtures, ["x5", "macau", "tinyping_short"])

    def test_selected_modes_normalizes_and_dedupes(self):
        self.assertEqual(_selected_modes("high, precise, auto, high"), ["high", "auto"])

    def test_high_mode_audio_profiles_include_high_detail_route(self):
        names = [profile.name for profile in _adaptive_audio_profiles({"mode": "high"})]
        self.assertIn("adaptive_voice_change_high_detail", names)
        non_high_names = [profile.name for profile in _adaptive_audio_profiles({"mode": "fast"})]
        self.assertNotIn("adaptive_voice_change_high_detail", non_high_names)

    def test_extract_json_tail_ignores_leading_logs(self):
        payload = _extract_json_tail('[bench] running\n{\n  "json": "/tmp/out.json",\n  "ok": true\n}\n')
        self.assertEqual(payload["json"], "/tmp/out.json")
        self.assertTrue(payload["ok"])

    def test_run_full_verification_exposes_cli_single_run_path(self):
        with TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "fixture.mp4"
            media_path.write_bytes(b"")
            output_dir = Path(tmpdir) / "verify"
            with mock.patch(
                "tools.verify_full_media_pipeline._run_single_verification",
                return_value={"ok": True, "summary_metrics": {"final_segment_count": 1}},
            ) as run_single:
                payload = run_full_verification(
                    media_path,
                    mode="high",
                    output_dir=output_dir,
                    settings_overrides={"runtime_performance_profile": "max"},
                    start_sec=1.5,
                    duration_sec=12.0,
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result_path"], str((output_dir / "tinyping_full_verify.json").resolve()))
        call = run_single.call_args.kwargs
        self.assertEqual(call["mode"], "high")
        self.assertEqual(call["output_root"], output_dir)
        self.assertEqual(call["settings_overrides"], {"runtime_performance_profile": "max"})
        self.assertEqual(call["start_sec"], 1.5)
        self.assertEqual(call["duration_sec"], 12.0)

    def test_segment_artifact_summary_persists_selected_source_and_anchor_in_saved_project(self):
        raw_rows = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "원본 자막",
                "stt_selected_source": "STT2",
                "stt_score_label": "red",
            }
        ]
        output_rows = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "최종 자막",
                "speaker": "00",
                "stt_selected_source": "STT2",
                "_stt_original_candidate_start": 0.8,
                "_stt_original_candidate_end": 2.2,
                "stt_score_label": "red",
            }
        ]
        with TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "fixture.mp4"
            media_path.write_bytes(b"")
            output_dir = Path(tmpdir) / "artifacts"
            with mock.patch("tools.subtitle_regression_pack.probe_media", return_value={"fps": 30.0}):
                summary = _segment_artifact_summary(
                    media=media_path,
                    raw_rows=raw_rows,
                    output_rows=output_rows,
                    output_dir=output_dir,
                    project_name="roundtrip_check",
                )

        self.assertEqual(summary["final_selected_source_counts"], {"STT2": 1})
        self.assertEqual(summary["saved_project_state"]["reloaded_segment_count"], 1)
        self.assertEqual(summary["saved_project_state"]["preserved_anchor_segments"], 1)


if __name__ == "__main__":
    unittest.main()
