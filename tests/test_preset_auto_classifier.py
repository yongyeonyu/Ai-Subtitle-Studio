# Version: 03.14.12
# Phase: PHASE2
import os
import tempfile
import unittest
import wave
from unittest import mock

import numpy as np

from core.audio.audio_presets import curated_audio_preset_names, load_audio_presets
from core.audio.preset_auto_classifier import (
    analyze_sample_features,
    apply_auto_classified_presets,
    auto_classify_media_presets,
    build_audio_profile,
    choose_representative_window,
    tune_audio_settings_for_profile,
)


class PresetAutoClassifierTests(unittest.TestCase):
    def _write_wave(self, path: str, data: np.ndarray, rate: int = 16000) -> None:
        pcm = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm.tobytes())

    def test_curated_audio_presets_expose_six_cases(self):
        names = curated_audio_preset_names()
        presets = load_audio_presets()

        self.assertEqual(names, [
            "실내-마이크유",
            "실내-마이크무",
            "실외-마이크유",
            "실외-마이크무",
            "차안-마이크유",
            "차안-마이크무",
        ])
        for name in names:
            self.assertIn(name, presets)

    def test_choose_representative_window_prefers_louder_middle_minute(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "sample.wav")
            quiet = np.zeros(16000 * 60, dtype=np.float32)
            loud = np.sin(np.linspace(0, 4000 * np.pi, 16000 * 60)).astype(np.float32) * 0.12
            tail = np.zeros(16000 * 60, dtype=np.float32)
            self._write_wave(wav_path, np.concatenate([quiet, loud, tail]))

            start_sec, duration_sec = choose_representative_window(wav_path)

        self.assertAlmostEqual(start_sec, 66.667, places=1)
        self.assertAlmostEqual(duration_sec, 60.0, places=1)

    def test_choose_representative_window_scans_ten_candidates_in_three_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "sample.wav")
            total = np.zeros(16000 * 180, dtype=np.float32)
            start_sec = int(round((120.0 / 9.0) * 5))
            start_idx = start_sec * 16000
            total[start_idx:start_idx + (60 * 16000)] = (
                np.sin(np.linspace(0, 4000 * np.pi, 16000 * 60)).astype(np.float32) * 0.14
            )
            self._write_wave(wav_path, total)

            start_sec, duration_sec = choose_representative_window(wav_path)

        self.assertAlmostEqual(start_sec, 66.667, places=1)
        self.assertAlmostEqual(duration_sec, 60.0, places=1)

    def test_analyze_sample_features_reports_low_band_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "low.wav")
            t = np.linspace(0, 60, 16000 * 60, endpoint=False)
            low = (np.sin(2 * np.pi * 90 * t) * 0.1).astype(np.float32)
            self._write_wave(wav_path, low)

            features = analyze_sample_features(wav_path)

        self.assertGreater(features["low_band_ratio"], 0.5)
        self.assertLess(features["high_band_ratio"], 0.2)

    def test_apply_auto_classified_presets_preserves_stage_settings(self):
        updated = apply_auto_classified_presets(
            {
                "selected_model": "old",
                "selected_audio_ai": "none",
                "selected_vad": "none",
                "stt_quality_preset": "balanced",
            },
            {
                "audio_preset": "차안-마이크무",
                "stt_quality_preset": "precise",
                "confidence": 0.91,
                "reason": "test",
                "audio_tune_settings": {"ff_hp": 190, "selected_audio_ai": "clearvoice"},
                "audio_profile": {"environment": "car"},
                "audio_tune_reason": "저역/차내 소음 대응",
            },
        )

        self.assertEqual(updated["audio_preset"], "auto")
        self.assertEqual(updated["stt_quality_preset"], "balanced")
        self.assertEqual(updated["selected_model"], "old")
        self.assertEqual(updated["selected_audio_ai"], "clearvoice")
        self.assertEqual(updated["selected_vad"], "none")
        self.assertEqual(updated["ff_hp"], 190)
        self.assertEqual(updated["audio_preset_auto_tune"]["selected_audio_ai"], "clearvoice")
        self.assertNotIn("selected_vad", updated["audio_preset_auto_tune"])
        self.assertEqual(updated["audio_preset_auto_decision"]["audio_preset"], "auto")
        self.assertEqual(updated["audio_preset_auto_decision"]["suggested_stt_quality_preset"], "precise")
        self.assertEqual(updated["audio_preset_auto_decision"]["audio_profile"]["environment"], "car")

    def test_audio_profile_tunes_car_low_rumble_to_strong_filter_stack(self):
        features = {
            "rms_mean": 0.021,
            "rms_p90": 0.08,
            "silence_ratio": 0.42,
            "zero_crossing_rate": 0.08,
            "low_band_ratio": 0.62,
            "high_band_ratio": 0.04,
            "spectral_centroid_hz": 900.0,
        }
        profile = build_audio_profile(features, audio_preset="차안-마이크무")
        tune, reason = tune_audio_settings_for_profile(profile, features)

        self.assertEqual(profile["environment"], "car")
        self.assertTrue(profile["low_rumble"])
        self.assertEqual(tune["selected_audio_ai"], "clearvoice")
        self.assertNotIn("selected_vad", tune)
        self.assertNotIn("vad_threshold", tune)
        self.assertGreaterEqual(tune["ff_hp"], 170)
        self.assertLessEqual(tune["ff_nf"], -30)
        self.assertIn("저역", reason)

    def test_auto_classify_media_presets_scans_samples_without_llm(self):
        with mock.patch("core.audio.preset_auto_classifier.prepare_audio_samples") as prep:
            prep.return_value = {
                "media_duration_sec": 600.0,
                "samples": [
                    {
                        "index": 1,
                        "start_sec": 0.0,
                        "duration_sec": 30.0,
                        "speech_score": 0.62,
                        "features": {
                            "rms_mean": 0.02,
                            "rms_p90": 0.08,
                            "silence_ratio": 0.3,
                            "zero_crossing_rate": 0.22,
                            "low_band_ratio": 0.12,
                            "mid_band_ratio": 0.62,
                            "high_band_ratio": 0.18,
                            "spectral_centroid_hz": 3200.0,
                        },
                    }
                ],
            }
            with tempfile.TemporaryDirectory() as tmp:
                media = os.path.join(tmp, "sample.mp4")
                open(media, "wb").close()

                decision = auto_classify_media_presets(media, settings={"selected_model": "사용 안함 (Whisper 단독 진행)"})

        self.assertEqual(decision["audio_preset"], "auto")
        self.assertEqual(decision["audio_strategy"], "noisy_voice")
        self.assertEqual(decision["audio_profile"]["environment"], "outdoor")
        self.assertIn("audio_tune_settings", decision)
        self.assertEqual(decision["audio_tune_settings"]["selected_audio_ai"], "clearvoice")
        self.assertNotIn("selected_vad", decision["audio_tune_settings"])
        self.assertGreaterEqual(decision["audio_tune_settings"]["ff_hp"], 150)
        self.assertFalse(decision["llm_used"])


if __name__ == "__main__":
    unittest.main()
