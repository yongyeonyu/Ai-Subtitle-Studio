# Version: 03.01.24
# Phase: PHASE2
import os
import unittest
from unittest import mock

from core.subtitle_quality.confidence_checker import evaluate_subtitle_confidence
from core.subtitle_quality.quality_pipeline import run_subtitle_quality_pipeline


class SubtitleQualityPipelineTests(unittest.TestCase):
    def _good_segment(self):
        return {
            "start": 0.0,
            "end": 1.2,
            "text": "안녕하세요",
            "words": [{"word": "안녕하세요", "start": 0.1, "end": 1.0, "confidence": 0.91}],
            "asr_metadata": {
                "backend": "unit-test",
                "avg_logprob": -0.2,
                "compression_ratio": 1.1,
                "no_speech_prob": 0.02,
                "word_confidence": 0.91,
                "words": [{"word": "안녕하세요", "start": 0.1, "end": 1.0, "confidence": 0.91}],
            },
        }

    def test_evaluate_subtitle_confidence_labels_good_segment_green(self):
        metrics = evaluate_subtitle_confidence(
            self._good_segment(),
            vad_segments=[{"start": 0.0, "end": 1.3}],
            settings={"sub_max_cps": 12},
        )

        self.assertEqual(metrics.confidence_label, "green")
        self.assertGreaterEqual(metrics.confidence_score, 85)
        self.assertEqual(metrics.hallucination_penalty, 0.0)

    def test_evaluate_subtitle_confidence_flags_missing_metadata_gray(self):
        metrics = evaluate_subtitle_confidence(
            {"start": 0.0, "end": 0.2, "text": "긴문장입니다"},
            settings={"sub_min_duration": 0.3, "sub_max_cps": 12},
        )

        self.assertEqual(metrics.confidence_label, "gray")
        self.assertIn("metadata_missing", metrics.flags)
        self.assertIn("word_timestamps_missing", metrics.flags)

    def test_evaluate_subtitle_confidence_numeric_token_is_not_over_penalized(self):
        metrics = evaluate_subtitle_confidence(
            {
                "start": 0.0,
                "end": 1.0,
                "text": "2026",
                "asr_metadata": {
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.05,
                    "word_confidence": 0.90,
                },
            },
            settings={"sub_min_duration": 0.2, "sub_max_cps": 12},
        )

        self.assertEqual(metrics.confidence_label, "green")
        self.assertGreaterEqual(metrics.confidence_score, 85.0)
        self.assertNotIn("text_has_no_language_chars", metrics.flags)

    def test_evaluate_subtitle_confidence_short_interjection_can_score_green(self):
        metrics = evaluate_subtitle_confidence(
            {
                "start": 0.0,
                "end": 0.6,
                "text": "어",
                "asr_metadata": {
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.05,
                    "word_confidence": 0.90,
                },
            },
            settings={"sub_min_duration": 0.2, "sub_max_cps": 12},
        )

        self.assertEqual(metrics.confidence_label, "green")
        self.assertGreaterEqual(metrics.confidence_score, 85.0)
        self.assertIn("very_short_text", metrics.flags)

    def test_evaluate_subtitle_confidence_plausible_text_without_metadata_is_not_forced_gray(self):
        metrics = evaluate_subtitle_confidence(
            {
                "start": 0.0,
                "end": 1.3,
                "text": "유스 어드벤처 2026",
            },
            settings={"sub_min_duration": 0.2, "sub_max_cps": 12},
        )

        self.assertNotEqual(metrics.confidence_label, "gray")
        self.assertGreaterEqual(metrics.confidence_score, 72.0)
        self.assertIn("metadata_missing", metrics.flags)

    def test_quality_pipeline_adds_segment_quality_and_summary(self):
        result = run_subtitle_quality_pipeline(
            [
                self._good_segment(),
                {
                    "start": 2.0,
                    "end": 2.8,
                    "text": "Thank you for watching",
                    "asr_metadata": {"no_speech_prob": 0.95, "avg_logprob": -1.5},
                },
            ],
            vad_segments=[{"start": 0.0, "end": 1.3}],
            settings={"subtitle_quality_enabled": True},
        )

        self.assertEqual(len(result.segments), 2)
        self.assertIn("quality", result.segments[0])
        self.assertGreater(result.summary.green_count, 0)
        self.assertGreater(result.summary.needs_review_count, 0)
        self.assertIsNotNone(result.summary.overall_score)

    def test_quality_pipeline_preserves_before_after_scores_from_context(self):
        result = run_subtitle_quality_pipeline(
            [self._good_segment()],
            settings={"subtitle_quality_enabled": True},
            context={"before_score": 70, "after_score": 88},
        )

        self.assertEqual(result.summary.before_score, 70.0)
        self.assertEqual(result.summary.after_score, 88.0)

    def test_quality_pipeline_auto_correct_generates_candidates_without_changing_when_unsafe(self):
        result = run_subtitle_quality_pipeline(
            [
                {
                    "line": 0,
                    "start": 0.0,
                    "end": 0.5,
                    "text": "가격은 123원",
                    "quality": {"confidence_label": "red", "confidence_score": 40, "flags": ["high_cps"]},
                }
            ],
            settings={
                "subtitle_quality_enabled": True,
                "subtitle_quality_auto_correct_enabled": True,
                "review_auto_correct_apply_threshold": 92,
            },
            auto_correct=True,
        )

        self.assertEqual(result.segments[0]["text"], "가격은 123원")
        self.assertIn("quality_candidates", result.segments[0])

    def test_quality_pipeline_marks_uncertain_llm_rewrite_for_review(self):
        result = run_subtitle_quality_pipeline(
            [
                {
                    "start": 0.0,
                    "end": 1.3,
                    "text": "안경쓰신 분들은 그냥 시뮬레이터를 하시는 게 낫습니다",
                    "words": [{"word": "안경쓰신", "start": 0.0, "end": 0.4}],
                    "asr_metadata": {
                        "avg_logprob": -0.2,
                        "compression_ratio": 1.0,
                        "no_speech_prob": 0.05,
                        "word_confidence": 0.91,
                    },
                    "_llm_rewrite_policy": {
                        "changed": True,
                        "confidence": "medium",
                        "needs_review": True,
                        "reason": "uncertain_lexical_rewrite",
                        "similarity": 0.88,
                        "score_penalty": 18.0,
                    },
                }
            ],
            settings={"subtitle_quality_enabled": True, "sub_max_cps": 12},
        )

        quality = dict(result.segments[0].get("quality") or {})
        self.assertEqual(quality.get("confidence_label"), "yellow")
        self.assertIn("llm_uncertain_rewrite", tuple(quality.get("flags") or ()))
        self.assertGreaterEqual(result.summary.needs_review_count, 1)

    def test_swift_quality_bridge_matches_pipeline_when_available(self):
        from core.native_swift_subtitle import find_native_cli_path

        if find_native_cli_path() is None:
            self.skipTest("native Swift CLI is not built")

        segments = [
            self._good_segment(),
            {
                "start": 2.0,
                "end": 2.8,
                "text": "Thank you for watching",
                "asr_metadata": {"no_speech_prob": 0.95, "avg_logprob": -1.5},
            },
        ]
        settings = {"subtitle_quality_enabled": True, "sub_max_cps": 12}
        env_off = {"AI_SUBTITLE_STUDIO_SWIFT_QUALITY": "0"}
        env_on = {"AI_SUBTITLE_STUDIO_SWIFT_QUALITY": "1"}
        with mock.patch.dict(os.environ, env_off, clear=False):
            python_result = run_subtitle_quality_pipeline(segments, vad_segments=[{"start": 0.0, "end": 1.3}], settings=settings)
        with mock.patch.dict(os.environ, env_on, clear=False):
            swift_result = run_subtitle_quality_pipeline(segments, vad_segments=[{"start": 0.0, "end": 1.3}], settings=settings)

        self.assertEqual(len(swift_result.segments), len(python_result.segments))
        self.assertEqual(
            [dict(item.get("quality") or {}).get("confidence_label") for item in swift_result.segments],
            [dict(item.get("quality") or {}).get("confidence_label") for item in python_result.segments],
        )
        self.assertEqual(swift_result.summary.green_count, python_result.summary.green_count)
        self.assertEqual(swift_result.summary.needs_review_count, python_result.summary.needs_review_count)


if __name__ == "__main__":
    unittest.main()
