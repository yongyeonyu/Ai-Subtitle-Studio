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
    apply_vad_stt_timing_consensus,
    apply_review_vad_settings,
    adjust_segments_to_vad_boundaries,
    prioritize_vad_voice_starts,
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

    def test_vad_voice_start_priority_pulls_late_final_start_to_speech_onset(self):
        segments = [{"start": 10.9, "end": 12.0, "text": "늦은 자막"}]
        vad = [{"start": 10.2, "end": 11.8}]

        adjusted, changed = prioritize_vad_voice_starts(
            segments,
            vad,
            max_pull_sec=1.0,
            edge_pad_sec=0.04,
        )

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 10.16, places=3)
        self.assertEqual(adjusted[0]["timeline_start"], adjusted[0]["start"])
        self.assertEqual(adjusted[0]["end"], 12.0)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_voice_start_priority"]["vad_start"],
            10.2,
        )

    def test_vad_voice_start_priority_respects_stt_anchor_lead_limit(self):
        segments = [
            {
                "start": 10.9,
                "end": 12.0,
                "text": "앵커 있는 자막",
                "_stt_original_candidate_start": 10.7,
                "_stt_original_candidate_end": 12.0,
            }
        ]
        vad = [{"start": 10.2, "end": 11.8}]

        adjusted, changed = prioritize_vad_voice_starts(
            segments,
            vad,
            max_pull_sec=1.0,
            edge_pad_sec=0.04,
            max_stt_lead_sec=0.12,
        )

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 10.58, places=3)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_voice_start_priority"]["stt_anchor_start"],
            10.7,
        )

    def test_vad_voice_start_priority_keeps_previous_subtitle_boundary_safe(self):
        segments = [
            {"start": 9.0, "end": 10.3, "text": "앞 자막"},
            {"start": 10.9, "end": 12.0, "text": "뒤 자막"},
        ]
        vad = [{"start": 10.2, "end": 11.8}]

        adjusted, changed = prioritize_vad_voice_starts(
            segments,
            vad,
            max_pull_sec=1.0,
            edge_pad_sec=0.04,
            min_gap_sec=0.02,
        )

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[1]["start"], 10.32, places=3)
        self.assertEqual(adjusted[0]["end"], 10.3)

    def test_vad_voice_start_priority_ignores_unrelated_earlier_vad_span(self):
        segments = [{"start": 10.9, "end": 12.0, "text": "자막"}]
        vad = [{"start": 9.0, "end": 10.91}]

        adjusted, changed = prioritize_vad_voice_starts(
            segments,
            vad,
            max_pull_sec=2.0,
            min_overlap_sec=0.04,
        )

        self.assertEqual(changed, 0)
        self.assertAlmostEqual(adjusted[0]["start"], 10.9, places=3)

    def test_vad_stt_timing_consensus_uses_vad_when_two_of_three_match(self):
        segments = [
            {
                "start": 23.0,
                "end": 26.4,
                "text": "안녕하세요 소설가 유모씨입니다",
                "stt_candidates": [
                    {"source": "STT1", "start": 21.54, "end": 22.94, "text": "안녕하세요 소설가 유모씨입니다"},
                    {"source": "STT2", "start": 23.0, "end": 26.4, "text": "안녕하세요 소설가 유모씨입니다"},
                ],
            }
        ]
        vad = [{"start": 21.5, "end": 22.9}]

        adjusted, changed = apply_vad_stt_timing_consensus(
            segments,
            vad,
            start_tolerance_sec=0.35,
            end_tolerance_sec=0.45,
            duration_tolerance_sec=0.45,
            edge_pad_sec=0.04,
        )

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 21.46, places=3)
        self.assertAlmostEqual(adjusted[0]["end"], 22.94, places=3)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_stt_timing_consensus"]["matched_sources"],
            ["VAD", "STT1"],
        )

    def test_vad_stt_timing_consensus_uses_union_when_only_stt1_and_vad_exist(self):
        segments = [
            {
                "start": 23.0,
                "end": 26.4,
                "text": "안녕하세요 소설가 유모씨입니다",
                "stt_candidates": [
                    {"source": "STT1", "start": 21.54, "end": 22.94, "text": "안녕하세요 소설가 유모씨입니다"},
                ],
            }
        ]
        vad = [{"start": 21.5, "end": 22.9}]

        adjusted, changed = apply_vad_stt_timing_consensus(segments, vad)

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 21.5, places=3)
        self.assertAlmostEqual(adjusted[0]["end"], 22.94, places=3)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_stt_timing_consensus"]["action"],
            "stt1_vad_union_span",
        )

    def test_vad_stt_timing_consensus_uses_stt_pair_when_vad_disagrees(self):
        segments = [
            {
                "start": 20.0,
                "end": 25.0,
                "text": "오늘은 센터에 방문을 했는데",
                "stt_candidates": [
                    {"source": "STT1", "start": 20.02, "end": 22.22, "text": "오늘은 센터에 방문을 했는데"},
                    {"source": "STT2", "start": 20.08, "end": 22.3, "text": "오늘은 센터에 방문을 했는데"},
                ],
            }
        ]
        vad = [{"start": 18.0, "end": 18.4}]

        adjusted, changed = apply_vad_stt_timing_consensus(segments, vad)

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 20.05, places=3)
        self.assertAlmostEqual(adjusted[0]["end"], 22.26, places=3)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_stt_timing_consensus"]["matched_sources"],
            ["STT1", "STT2"],
        )

    def test_vad_stt_timing_consensus_uses_stt_pair_when_vad_is_missing(self):
        segments = [
            {
                "start": 20.0,
                "end": 25.0,
                "text": "오늘은 센터에 방문을 했는데",
                "stt_candidates": [
                    {"source": "STT1", "start": 20.02, "end": 22.22, "text": "오늘은 센터에 방문을 했는데"},
                    {"source": "STT2", "start": 20.08, "end": 22.3, "text": "오늘은 센터에 방문을 했는데"},
                ],
            }
        ]

        adjusted, changed = apply_vad_stt_timing_consensus(segments, [])

        self.assertEqual(changed, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 20.05, places=3)
        self.assertAlmostEqual(adjusted[0]["end"], 22.26, places=3)
        self.assertEqual(
            adjusted[0]["asr_metadata"]["vad_stt_timing_consensus"]["matched_sources"],
            ["STT1", "STT2"],
        )

    def test_vad_stt_timing_consensus_requires_two_similar_sources(self):
        segments = [
            {
                "start": 23.0,
                "end": 26.0,
                "text": "불일치",
                "stt_candidates": [
                    {"source": "STT1", "start": 20.0, "end": 21.0, "text": "불일치"},
                    {"source": "STT2", "start": 23.0, "end": 26.0, "text": "불일치"},
                ],
            }
        ]
        vad = [{"start": 21.8, "end": 22.2}]

        adjusted, changed = apply_vad_stt_timing_consensus(segments, vad)

        self.assertEqual(changed, 0)
        self.assertAlmostEqual(adjusted[0]["start"], 23.0, places=3)
        self.assertAlmostEqual(adjusted[0]["end"], 26.0, places=3)

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
