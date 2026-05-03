# Version: 03.12.02
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
    choose_representative_window,
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

    def test_apply_auto_classified_presets_updates_both_audio_and_quality(self):
        updated = apply_auto_classified_presets(
            {"selected_model": "old"},
            {"audio_preset": "차안-마이크무", "stt_quality_preset": "precise", "confidence": 0.91, "reason": "test"},
        )

        self.assertEqual(updated["audio_preset"], "차안-마이크무")
        self.assertEqual(updated["stt_quality_preset"], "precise")
        self.assertEqual(updated["selected_vad"], "ten_vad")
        self.assertEqual(updated["audio_preset_auto_decision"]["audio_preset"], "차안-마이크무")

    def test_auto_classify_media_presets_falls_back_to_heuristic_without_llm(self):
        with mock.patch("core.audio.preset_auto_classifier.prepare_audio_sample") as prep, \
             mock.patch("core.audio.preset_auto_classifier.analyze_sample_features") as analyze:
            prep.return_value = {
                "wav_path": "/tmp/fake.wav",
                "media_duration_sec": 600.0,
                "window_start_sec": 110.0,
                "window_duration_sec": 180.0,
                "representative_start_sec": 60.0,
                "representative_duration_sec": 60.0,
            }
            analyze.return_value = {
                "rms_mean": 0.02,
                "rms_p90": 0.08,
                "silence_ratio": 0.3,
                "zero_crossing_rate": 0.22,
                "low_band_ratio": 0.12,
                "mid_band_ratio": 0.62,
                "high_band_ratio": 0.18,
                "spectral_centroid_hz": 3200.0,
            }
            with tempfile.TemporaryDirectory() as tmp:
                media = os.path.join(tmp, "sample.mp4")
                open(media, "wb").close()

                decision = auto_classify_media_presets(media, settings={"selected_model": "사용 안함 (Whisper 단독 진행)"})

        self.assertEqual(decision["audio_preset"], "실외-마이크무")
        self.assertEqual(decision["stt_quality_preset"], "precise")
        self.assertFalse(decision["llm_used"])


if __name__ == "__main__":
    unittest.main()
