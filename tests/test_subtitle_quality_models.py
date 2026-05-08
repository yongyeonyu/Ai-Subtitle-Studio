# Version: 03.01.22
# Phase: PHASE2
import unittest

from core.subtitle_quality.models import (
    attach_asr_metadata,
    metrics_from_dict,
    metrics_to_dict,
    normalize_asr_metadata,
)
from core.subtitle_quality.hallucination_detector import estimate_hallucination_risk
from core.subtitle_quality.vad_alignment_checker import (
    annotate_segment_vad_alignment,
    annotate_segments_vad_alignment,
    apply_review_vad_settings,
    adjust_segments_to_vad_boundaries,
    vad_overlap_ratio,
)


class SubtitleQualityModelsTest(unittest.TestCase):
    def test_normalize_asr_metadata_keeps_backend_fields(self):
        segment = {
            "avg_logprob": -0.32,
            "compression_ratio": 1.4,
            "no_speech_prob": 0.08,
            "temperature": 0.0,
            "tokens": [1, 2],
            "words": [
                {"word": "안녕", "start": 0.0, "end": 0.5, "confidence": 0.91},
                {"word": "하세요", "start": 0.5, "end": 1.0, "confidence": 0.81},
            ],
        }

        metadata = normalize_asr_metadata(segment, backend="test-backend", language_probability=0.97)

        self.assertEqual(metadata["backend"], "test-backend")
        self.assertEqual(metadata["avg_logprob"], -0.32)
        self.assertEqual(metadata["compression_ratio"], 1.4)
        self.assertEqual(metadata["no_speech_prob"], 0.08)
        self.assertEqual(metadata["temperature"], 0.0)
        self.assertEqual(metadata["tokens"], [1, 2])
        self.assertEqual(metadata["language_probability"], 0.97)
        self.assertAlmostEqual(metadata["word_confidence"], 0.86)
        self.assertEqual(metadata["words"][0]["word"], "안녕")

    def test_attach_asr_metadata_does_not_change_text_or_timing(self):
        source = {"start": 1.0, "end": 2.0, "text": "원문", "words": []}

        segment = attach_asr_metadata(source, backend="backend")

        self.assertEqual(segment["start"], source["start"])
        self.assertEqual(segment["end"], source["end"])
        self.assertEqual(segment["text"], source["text"])
        self.assertIn("asr_metadata", segment)

    def test_metrics_dict_roundtrip(self):
        data = {"confidence_score": 87.0, "confidence_label": "green", "flags": ["ok"]}

        metrics = metrics_from_dict(data)
        payload = metrics_to_dict(metrics)

        self.assertEqual(metrics.flags, ("ok",))
        self.assertEqual(payload["confidence_score"], 87.0)
        self.assertEqual(payload["confidence_label"], "green")

    def test_vad_alignment_annotates_quality_flag(self):
        segment = {"start": 2.0, "end": 4.0, "text": "음성"}
        vad = [{"start": 2.5, "end": 3.5}]

        annotated = annotate_segment_vad_alignment(segment, vad)

        self.assertEqual(vad_overlap_ratio(segment, vad), 0.5)
        self.assertEqual(annotated["quality"]["vad_alignment_score"], 50.0)
        self.assertEqual(annotated["asr_metadata"]["vad_alignment"]["vad_aligned"], True)

    def test_vad_alignment_adjustment_uses_prepared_overlap_path(self):
        segments = [{"start": 1.9, "end": 3.2, "text": "음성"}]
        vad = [{"start": 2.0, "end": 3.0}]

        adjusted, changed = adjust_segments_to_vad_boundaries(segments, vad, max_shift_sec=0.3, edge_pad_sec=0.05)

        self.assertEqual(changed, 1)
        self.assertEqual(adjusted[0]["start"], 1.95)
        self.assertEqual(adjusted[0]["end"], 3.05)
        self.assertEqual(adjusted[0]["quality"]["vad_alignment_score"], 90.909)

    def test_batch_vad_alignment_matches_single_segment_annotations(self):
        segments = [
            {"start": 0.0, "end": 2.0, "text": "앞"},
            {"start": 3.0, "end": 5.0, "text": "뒤"},
        ]
        vad = [{"start": 1.0, "end": 1.5}, {"start": 3.5, "end": 4.5}]

        batch = annotate_segments_vad_alignment(segments, vad)
        single = [annotate_segment_vad_alignment(segment, vad) for segment in segments]

        self.assertEqual(
            [item["asr_metadata"]["vad_alignment"] for item in batch],
            [item["asr_metadata"]["vad_alignment"] for item in single],
        )

    def test_hallucination_risk_combines_asr_and_vad(self):
        segment = {
            "start": 5.0,
            "end": 6.0,
            "text": "Thank you for watching",
            "asr_metadata": {"no_speech_prob": 0.9, "avg_logprob": -1.4},
        }

        risk = estimate_hallucination_risk(segment, vad_segments=[{"start": 0.0, "end": 1.0}])

        self.assertEqual(risk["risk"], 1.0)
        self.assertIn("non_speech_hallucination_risk", risk["flags"])
        self.assertIn("known_hallucination_phrase", risk["flags"])

    def test_review_vad_settings_override_only_review_fields(self):
        settings = {
            "vad_threshold": 0.6,
            "vad_min_speech": 0.3,
            "vad_min_silence": 2.0,
            "vad_speech_pad": 0.1,
            "review_vad_before_stt_enabled": True,
            "review_vad_strict_mode": True,
            "review_vad_speech_pad_sec": 0.35,
            "review_vad_min_silence_sec": 0.8,
        }

        applied = apply_review_vad_settings(settings)

        self.assertEqual(applied["vad_threshold"], 0.6)
        self.assertEqual(applied["vad_min_speech"], 0.3)
        self.assertEqual(applied["vad_speech_pad"], 0.35)
        self.assertEqual(applied["vad_min_silence"], 0.8)


if __name__ == "__main__":
    unittest.main()
