import unittest
from core.audio.stt_rescue import replacement_is_better, SttRecheckRange


class STTRescueGuardTests(unittest.TestCase):
    def setUp(self):
        # Default settings with threshold and min_improvement
        self.settings = {
            "stt_low_score_recheck_threshold": 50.0,
            "stt_low_score_recheck_min_improvement": 3.0,
            "stt_rescue_similarity_threshold": 0.70,
        }

    def test_numeric_preservation_blocks_drift(self):
        # Original has 7000, challenger has 7008 (mismatch)
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="금일 매출은 7000원입니다.",
            secondary_text="",
            primary={},
            secondary={},
        )
        # Score is 92 (high improvement), but should be blocked due to number drift
        rescue_segments = [{"text": "금일 매출은 7008원입니다.", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, self.settings)
        self.assertFalse(better)

    def test_numeric_preservation_allows_matching_numbers(self):
        # Original has 7000, challenger also has 7000
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="금일 매출은 7000원입니다.",
            secondary_text="",
            primary={},
            secondary={},
        )
        rescue_segments = [{"text": "금일 매출은 7000원입니다!", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, self.settings)
        self.assertTrue(better)

    def test_unexpected_number_hallucination_blocked(self):
        # Original has no numbers, challenger has 7008
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="오늘 날씨가 매우 화창하고 맑네요.",
            secondary_text="",
            primary={},
            secondary={},
        )
        rescue_segments = [{"text": "오늘 날씨가 7008 매우 화창하고 맑네요.", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, self.settings)
        self.assertFalse(better)

    def test_wrong_ending_and_high_local_drift_blocked(self):
        # Completely different endings / meaning (low similarity)
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="자막 스튜디오의 가속 아키텍처가 정상 작동합니다.",
            secondary_text="",
            primary={},
            secondary={},
        )
        # Score is 92 (high improvement), but similarity is too low (< 0.55)
        rescue_segments = [{"text": "자막 스튜디오의 가속 아키텍처가 완전히 다른 결말로 종결.", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, self.settings)
        self.assertFalse(better)

    def test_close_apple_stt2_span_allowed(self):
        # High similarity (> 0.55) and matching numbers
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="자막 스튜디오의 가속 아키텍처가 정상 작동합니다.",
            secondary_text="",
            primary={},
            secondary={},
        )
        rescue_segments = [{"text": "자막 스튜디오의 가속 아키텍처가 정상 작동함.", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, self.settings)
        self.assertTrue(better)

    def test_case2_stricter_similarity_threshold_blocks_broad_drift(self):
        settings = dict(self.settings)
        settings["stt_rescue_similarity_threshold"] = 0.80
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="80으로 크루즈 컨트롤을 걸어놓고요",
            secondary_text="",
            primary={},
            secondary={},
        )
        rescue_segments = [{"text": "80으로 크루즈 컨트롤끄라구요", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, settings)
        self.assertFalse(better)

    def test_case2_stricter_similarity_threshold_keeps_close_span(self):
        settings = dict(self.settings)
        settings["stt_rescue_similarity_threshold"] = 0.80
        item = SttRecheckRange(
            start=0.0,
            end=5.0,
            primary_score=30.0,
            secondary_score=0.0,
            primary_text="아주 잘 유지가 되고 있구요",
            secondary_text="",
            primary={},
            secondary={},
        )
        rescue_segments = [{"text": "잘 유지가 되고 있구요", "stt_score": 92.0}]
        better = replacement_is_better(rescue_segments, item, settings)
        self.assertTrue(better)
