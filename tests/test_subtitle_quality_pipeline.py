# Version: 03.01.24
# Phase: PHASE2
import unittest

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


if __name__ == "__main__":
    unittest.main()
