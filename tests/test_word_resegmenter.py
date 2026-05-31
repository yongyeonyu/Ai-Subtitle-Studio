# Version: 03.01.23
# Phase: PHASE2
import unittest
from unittest import mock

from core.engine import subtitle_engine
from core.engine.subtitle_native_word_split import native_builtin_word_groups
from core.native_cut_boundary import word_split_groups
from core.engine.word_resegmenter import resegment_by_word_timestamps
from core.engine.subtitle_timing import apply_final_gap_settings
from core.subtitle_quality.timestamp_regrouper import (
    regroup_by_word_timestamps,
    refine_segment_edges_with_context,
    snap_segments_to_word_vad_boundaries,
)


class WordResegmenterTests(unittest.TestCase):
    def test_native_cpp_word_split_groups_match_gap_rules(self):
        groups = word_split_groups(
            [0.0, 2.7],
            [0.8, 3.5],
            [5, 5],
            [0, 0],
            [-1, -1],
            max_chars=30,
            max_duration=8.0,
            max_cps=20.0,
            min_duration=0.1,
            gap_break_sec=1.5,
            word_gap_break_sec=0.65,
        )
        if groups is None:
            self.skipTest("native C++ extension unavailable")

        self.assertEqual(groups, [(0, 1), (1, 2)])

    def test_subtitle_engine_native_word_split_bridge_matches_gap_rules(self):
        words = [
            {"word": "안녕하세요", "start": 0.0, "end": 0.8},
            {"word": "다음입니다", "start": 2.7, "end": 3.5},
        ]
        groups = native_builtin_word_groups(
            words,
            rules={},
            threshold=30,
            gap_break_sec=1.5,
            default_gap_break_sec=1.5,
            natural_break_func=lambda _word, _next, _rules: False,
            visible_len_func=lambda text: len(text.replace(" ", "").replace("\n", "")),
        )
        if groups is None:
            self.skipTest("native C++ extension unavailable")

        self.assertEqual(groups, [(0, 1), (1, 2)])

    def test_splits_on_silence_gap(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 4.0,
                    "text": "안녕하세요 다음입니다",
                    "words": [
                        {"word": "안녕하세요", "start": 0.0, "end": 0.8},
                        {"word": "다음입니다", "start": 2.7, "end": 3.5},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["안녕하세요", "다음입니다"])

    def test_splits_on_punctuation_and_max_chars(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 4.0,
                    "text": "처음입니다, 다음 문장입니다",
                    "words": [
                        {"word": "처음입니다,", "start": 0.0, "end": 1.0},
                        {"word": "다음", "start": 1.1, "end": 1.7},
                        {"word": "문장입니다", "start": 1.8, "end": 2.6},
                    ],
                }
            ],
            max_chars=5,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["처음입니다,", "다음 문장입니다"])

    def test_lora_threshold_prevents_stt1_over_resegmentation(self):
        words = [
            {"word": token, "start": round(index * 0.35, 3), "end": round(index * 0.35 + 0.25, 3)}
            for index, token in enumerate(["하나", "둘셋", "넷다", "다섯", "여섯", "일곱", "여덟", "아홉"])
        ]

        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "하나 둘셋 넷다 다섯 여섯 일곱 여덟 아홉",
                    "words": words,
                    "_lora_segment_settings": {"split_length_threshold": 24},
                    "_lora_gap_settings": {"split_length_threshold": 24, "sub_gap_break_sec": 1.5},
                    "_lora_generation_profile": {"top_score": 92.0},
                    "_lora_segment_score": 92.0,
                }
            ],
            max_chars=6,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "하나 둘셋 넷다 다섯 여섯 일곱 여덟 아홉")
        self.assertEqual(result[0]["_lora_segment_settings"], {"split_length_threshold": 24})
        self.assertEqual(result[0]["_lora_gap_settings"]["split_length_threshold"], 24)
        self.assertEqual(result[0]["_lora_generation_profile"], {"top_score": 92.0})

    def test_timestamp_regrouper_preserves_lora_metadata(self):
        words = [
            {"word": token, "start": round(index * 0.32, 3), "end": round(index * 0.32 + 0.22, 3)}
            for index, token in enumerate(["하나", "둘셋", "넷다", "다섯", "여섯", "일곱", "여덟"])
        ]

        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "text": "하나 둘셋 넷다 다섯 여섯 일곱 여덟",
                    "words": words,
                    "_lora_segment_settings": {"split_length_threshold": 24},
                    "_lora_gap_settings": {"split_length_threshold": 24, "sub_max_duration": 8.0},
                    "_lora_generation_profile": {"top_score": 91.0},
                    "_lora_segment_score": 91.0,
                }
            ],
            max_chars=6,
            max_duration=4.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["_lora_segment_settings"], {"split_length_threshold": 24})
        self.assertEqual(result[0]["_lora_gap_settings"]["split_length_threshold"], 24)
        self.assertEqual(result[0]["_lora_segment_score"], 91.0)

    def test_lora_continuity_prevents_vad_from_creating_micro_splits(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "오 아 이건 스티커구나",
                    "words": [
                        {"word": "오", "start": 0.0, "end": 0.25},
                        {"word": "아", "start": 0.95, "end": 1.18},
                        {"word": "이건", "start": 1.55, "end": 1.9},
                        {"word": "스티커구나", "start": 2.0, "end": 2.6},
                    ],
                    "_lora_segment_settings": {
                        "split_length_threshold": 18,
                        "sub_min_duration": 0.8,
                        "sub_gap_break_sec": 1.8,
                        "word_timing_gap_break_sec": 1.2,
                    },
                    "_lora_gap_settings": {
                        "continuous_threshold": 2.4,
                        "sub_gap_break_sec": 1.8,
                    },
                    "_lora_segment_score": 94.0,
                }
            ],
            max_chars=8,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
            word_gap_break_sec=0.65,
            vad_segments=[
                {"start": 0.0, "end": 0.3},
                {"start": 0.92, "end": 1.22},
                {"start": 1.5, "end": 2.7},
            ],
        )

        self.assertEqual([item["text"] for item in result], ["오 아 이건 스티커구나"])
        self.assertEqual(result[0]["_lora_segment_score"], 94.0)

    def test_timestamp_regrouper_merges_lora_micro_segments_across_short_vad_gaps(self):
        base_lora = {
            "_lora_segment_settings": {
                "split_length_threshold": 18,
                "sub_min_duration": 0.8,
                "sub_gap_break_sec": 1.8,
                "word_timing_gap_break_sec": 1.2,
            },
            "_lora_gap_settings": {
                "continuous_threshold": 2.4,
                "sub_gap_break_sec": 1.8,
            },
            "_lora_segment_score": 93.0,
        }
        result = regroup_by_word_timestamps(
            [
                {
                    **base_lora,
                    "start": 0.0,
                    "end": 0.25,
                    "text": "오",
                    "words": [{"word": "오", "start": 0.0, "end": 0.25}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    **base_lora,
                    "start": 0.95,
                    "end": 1.18,
                    "text": "아",
                    "words": [{"word": "아", "start": 0.95, "end": 1.18}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    **base_lora,
                    "start": 1.55,
                    "end": 2.6,
                    "text": "이건 스티커구나",
                    "words": [
                        {"word": "이건", "start": 1.55, "end": 1.9},
                        {"word": "스티커구나", "start": 2.0, "end": 2.6},
                    ],
                    "asr_metadata": {"_clip_idx": 0},
                },
            ],
            max_chars=8,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.8,
            gap_break_sec=1.5,
            word_gap_break_sec=0.65,
            vad_segments=[
                {"start": 0.0, "end": 0.3},
                {"start": 0.92, "end": 1.22},
                {"start": 1.5, "end": 2.7},
            ],
        )

        self.assertEqual([item["text"] for item in result], ["오 아 이건 스티커구나"])
        self.assertEqual(result[0]["asr_metadata"]["_clip_idx"], 0)

    def test_lora_style_micro_merge_repairs_source_gap_only_micro_subtitles(self):
        result = subtitle_engine._apply_lora_style_micro_merge(
            [
                {
                    "start": 54.55,
                    "end": 54.85,
                    "text": "일단",
                    "words": [{"word": "일단", "start": 54.55, "end": 54.85}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    "start": 56.61,
                    "end": 57.25,
                    "text": "넥스 수소차",
                    "words": [{"word": "넥스", "start": 56.61, "end": 56.85}, {"word": "수소차", "start": 56.9, "end": 57.25}],
                    "asr_metadata": {"_clip_idx": 0},
                },
            ],
            [],
            {
                "subtitle_lora_micro_merge_enabled": True,
                "split_length_threshold": 16,
                "sub_min_duration": 0.3,
                "sub_gap_break_sec": 1.5,
                "continuous_threshold": 2.0,
                "subtitle_lora_micro_merge_continuous_sec": 3.0,
                "word_timing_gap_break_sec": 0.65,
                "sub_max_duration": 6.0,
                "sub_max_cps": 20,
            },
            stage="unit",
        )

        self.assertEqual([item["text"] for item in result], ["일단 넥스 수소차"])
        self.assertEqual(result[0]["_lora_style_merge_policy"]["task"], "lora_style_micro_merge")
        self.assertEqual(result[0]["_lora_segment_settings"]["split_length_threshold"], 20)

    def test_lora_style_micro_merge_uses_twenty_char_floor_for_legacy_short_settings(self):
        result = subtitle_engine._apply_lora_style_micro_merge(
            [
                {
                    "start": 0.0,
                    "end": 0.9,
                    "text": "이번에 마크마가",
                    "words": [
                        {"word": "이번에", "start": 0.0, "end": 0.35},
                        {"word": "마크마가", "start": 0.38, "end": 0.9},
                    ],
                },
                {
                    "start": 1.15,
                    "end": 2.1,
                    "text": "WEC 데뷔전에서",
                    "words": [
                        {"word": "WEC", "start": 1.15, "end": 1.45},
                        {"word": "데뷔전에서", "start": 1.48, "end": 2.1},
                    ],
                },
            ],
            [],
            {
                "subtitle_lora_micro_merge_enabled": True,
                "subtitle_lora_split_floor_chars": 20,
                "split_length_threshold": 10,
                "sub_min_duration": 0.3,
                "sub_gap_break_sec": 1.5,
                "continuous_threshold": 2.0,
                "subtitle_lora_micro_merge_continuous_sec": 3.0,
                "word_timing_gap_break_sec": 0.65,
                "sub_max_duration": 6.0,
                "sub_max_cps": 20,
            },
            stage="unit",
        )

        self.assertEqual([item["text"] for item in result], ["이번에 마크마가 WEC 데뷔전에서"])
        self.assertEqual(result[0]["_lora_segment_settings"]["split_length_threshold"], 20)

    def test_lora_style_micro_merge_selective_merges_low_readability_micro_fragment_without_resnapping(self):
        result = subtitle_engine._apply_lora_style_micro_merge(
            [
                {
                    "start": 0.0,
                    "end": 0.35,
                    "text": "어",
                    "words": [{"word": "어", "start": 0.02, "end": 0.18}],
                    "subtitle_confidence_label": "yellow",
                },
                {
                    "start": 0.46,
                    "end": 1.48,
                    "text": "이건 수소차예요",
                    "words": [
                        {"word": "이건", "start": 0.5, "end": 0.72},
                        {"word": "수소차예요", "start": 0.78, "end": 1.34},
                    ],
                },
            ],
            [],
            {
                "subtitle_lora_micro_merge_enabled": True,
                "subtitle_lora_micro_merge_mode": "readability_selective",
                "split_length_threshold": 16,
                "sub_min_duration": 0.8,
                "sub_gap_break_sec": 1.5,
                "continuous_threshold": 2.0,
                "subtitle_lora_micro_merge_continuous_sec": 3.0,
                "word_timing_gap_break_sec": 0.65,
                "sub_max_duration": 6.0,
                "sub_max_cps": 20,
            },
            stage="unit",
        )

        self.assertEqual([item["text"] for item in result], ["어 이건 수소차예요"])
        self.assertEqual(result[0]["start"], 0.0)
        self.assertEqual(result[0]["end"], 1.48)
        self.assertEqual(result[0]["_lora_style_merge_policy"]["mode"], "readability_selective")

    def test_lora_style_micro_merge_selective_skips_clean_rows(self):
        result = subtitle_engine._apply_lora_style_micro_merge(
            [
                {
                    "start": 0.0,
                    "end": 1.25,
                    "text": "여기는 티니핑 자동차 전시",
                    "words": [
                        {"word": "여기는", "start": 0.0, "end": 0.3},
                        {"word": "티니핑", "start": 0.34, "end": 0.64},
                        {"word": "자동차", "start": 0.68, "end": 0.94},
                        {"word": "전시", "start": 0.98, "end": 1.18},
                    ],
                    "subtitle_confidence_label": "green",
                    "_uncertainty_policy": {"bucket": "easy", "reasons": []},
                },
                {
                    "start": 1.18,
                    "end": 2.42,
                    "text": "수소 에너지로 자동차가 달려요",
                    "words": [
                        {"word": "수소", "start": 1.18, "end": 1.42},
                        {"word": "에너지로", "start": 1.46, "end": 1.82},
                        {"word": "자동차가", "start": 1.86, "end": 2.12},
                        {"word": "달려요", "start": 2.16, "end": 2.36},
                    ],
                    "subtitle_confidence_label": "green",
                    "_uncertainty_policy": {"bucket": "easy", "reasons": []},
                },
            ],
            [],
            {
                "subtitle_lora_micro_merge_enabled": True,
                "subtitle_lora_micro_merge_mode": "readability_selective",
                "split_length_threshold": 16,
                "sub_min_duration": 0.8,
                "sub_gap_break_sec": 1.5,
                "continuous_threshold": 2.0,
                "subtitle_lora_micro_merge_continuous_sec": 3.0,
                "word_timing_gap_break_sec": 0.65,
                "sub_max_duration": 6.0,
                "sub_max_cps": 20,
            },
            stage="unit",
        )

        self.assertEqual([item["text"] for item in result], ["여기는 티니핑 자동차 전시", "수소 에너지로 자동차가 달려요"])

    def test_lora_card_packaging_keeps_single_speaker_row_on_one_line(self):
        result = subtitle_engine._apply_lora_card_packaging(
            [
                {
                    "start": 10.0,
                    "end": 12.4,
                    "text": "수소를 만들고 보관해서 자동차를 달리게 하자",
                    "_lora_segment_settings": {
                        "split_length_threshold": 12,
                        "subtitle_target_line_count": 2,
                    },
                }
            ],
            {
                "subtitle_lora_packaging_enabled": True,
                "subtitle_lora_packaging_mode": "full",
                "split_length_threshold": 12,
            },
            {},
            stage="unit",
        )

        self.assertEqual(result[0]["start"], 10.0)
        self.assertEqual(result[0]["end"], 12.4)
        self.assertEqual(result[0]["text"], "수소를 만들고 보관해서 자동차를 달리게 하자")
        self.assertNotIn("_lora_packaging_policy", result[0])

    def test_lora_card_packaging_selective_skips_short_clean_rows(self):
        result = subtitle_engine._apply_lora_card_packaging(
            [
                {
                    "start": 0.0,
                    "end": 1.2,
                    "text": "티니핑 전시예요",
                    "subtitle_confidence_label": "green",
                    "_lora_segment_settings": {
                        "split_length_threshold": 14,
                        "subtitle_target_line_count": 1,
                    },
                }
            ],
            {
                "subtitle_lora_packaging_enabled": True,
                "subtitle_lora_packaging_mode": "readability_selective",
                "split_length_threshold": 14,
            },
            {},
            stage="unit",
        )

        self.assertEqual(result[0]["text"], "티니핑 전시예요")
        self.assertNotIn("_lora_packaging_policy", result[0])

    def test_non_speaker_multiline_rows_flatten_back_to_single_line(self):
        result = subtitle_engine._expand_non_speaker_multiline_segments(
            [
                {
                    "start": 10.0,
                    "end": 12.4,
                    "text": "수소를 만들고\n보관해서 자동차를 달리게 하자",
                    "_lora_packaging_policy": {"task": "lora_card_packaging"},
                }
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "수소를 만들고 보관해서 자동차를 달리게 하자")
        self.assertAlmostEqual(result[0]["start"], 10.0)
        self.assertAlmostEqual(result[0]["end"], 12.4)
        self.assertEqual(result[0]["_lora_packaging_policy"]["output_mode"], "single_line_flatten")

    def test_speaker_split_multiline_rows_keep_line_breaks(self):
        result = subtitle_engine._expand_non_speaker_multiline_segments(
            [
                {
                    "start": 1.0,
                    "end": 3.0,
                    "text": "- 안녕하세요\n- 반갑습니다",
                    "speaker_list": ["00", "01"],
                }
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "- 안녕하세요\n- 반갑습니다")

    def test_hyphen_multiline_without_two_speakers_is_flattened(self):
        result = subtitle_engine._expand_non_speaker_multiline_segments(
            [
                {
                    "start": 1.0,
                    "end": 3.0,
                    "text": "- 안녕하세요\n- 반갑습니다",
                    "speaker_list": ["00"],
                }
            ]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "- 안녕하세요 - 반갑습니다")

    def test_processing_preview_flattens_non_speaker_multiline_text(self):
        payloads: list[dict] = []

        subtitle_engine._emit_processing_preview(
            payloads.append,
            stage="packaging",
            stage_label="줄바꿈/카드 포장",
            segments=[
                {
                    "start": 4.0,
                    "end": 6.0,
                    "text": "올해도 유스 어드벤처\n2026을 해서",
                    "speaker_list": ["00"],
                },
                {
                    "start": 6.0,
                    "end": 8.0,
                    "text": "- 안녕하세요\n- 반갑습니다",
                    "speaker_list": ["00", "01"],
                },
            ],
        )

        self.assertEqual(len(payloads), 1)
        preview_rows = payloads[0]["segments"]
        self.assertEqual(preview_rows[0]["text"], "올해도 유스 어드벤처 2026을 해서")
        self.assertEqual(preview_rows[1]["text"], "- 안녕하세요\n- 반갑습니다")

    def test_common_split_guard_does_not_recut_lora_twenty_char_style(self):
        text = "이번에 마크마가 WEC 데뷔전에서 완주를 두 대 다 했잖아요"
        words = [
            {"word": token, "start": idx * 0.3, "end": idx * 0.3 + 0.25}
            for idx, token in enumerate(text.split())
        ]
        result = apply_final_gap_settings(
            [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": text,
                    "words": words,
                    "_lora_segment_score": 95.0,
                    "_lora_segment_settings": {"split_length_threshold": 10},
                }
            ],
            {
                "split_length_threshold": 10,
                "subtitle_lora_split_floor_chars": 20,
                "subtitle_common_split_guard_enabled": True,
                "subtitle_common_split_target_chars": 16,
                "subtitle_common_split_hard_max_chars": 24,
                "subtitle_common_split_hard_max_duration_sec": 5.5,
                "sub_min_duration": 0.2,
                "sub_max_duration": 6.0,
                "sub_gap_break_sec": 1.5,
            },
            force=True,
        )

        self.assertEqual([item["text"] for item in result], [text])

    def test_splits_when_duration_is_too_long(self):
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 10.0,
                    "text": "하나 둘 셋 넷 다섯 여섯",
                    "words": [
                        {"word": "하나", "start": 0.0, "end": 1.0},
                        {"word": "둘", "start": 1.1, "end": 2.0},
                        {"word": "셋", "start": 2.1, "end": 3.0},
                        {"word": "넷", "start": 5.5, "end": 6.2},
                        {"word": "다섯", "start": 6.3, "end": 7.0},
                        {"word": "여섯", "start": 7.1, "end": 8.0},
                    ],
                }
            ],
            max_chars=20,
            max_duration=3.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=3.0,
        )

        self.assertGreaterEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "하나 둘 셋")

    def test_generates_words_when_missing(self):
        result = resegment_by_word_timestamps(
            [{"start": 0.0, "end": 2.0, "text": "없는 단어 타임스탬프"}],
            max_chars=3,
            max_duration=1.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertTrue(result)
        self.assertTrue(all(item.get("words") for item in result))

    def test_timestamp_regrouper_merges_tiny_same_boundary_segments(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "아",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "아", "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    "start": 0.35,
                    "end": 1.0,
                    "text": "맞아요",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "맞아요", "start": 0.35, "end": 0.9, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
            ],
            max_chars=10,
            max_duration=4.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=1.5,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "아 맞아요")

    def test_timestamp_regrouper_does_not_merge_across_clip_boundary(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 0.2,
                    "text": "아",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "아", "start": 0.0, "end": 0.2, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 0},
                },
                {
                    "start": 0.35,
                    "end": 0.9,
                    "text": "맞아요",
                    "speaker": "SPEAKER_00",
                    "words": [{"word": "맞아요", "start": 0.35, "end": 0.9, "speaker": "SPEAKER_00"}],
                    "asr_metadata": {"_clip_idx": 1},
                },
            ],
            max_chars=10,
            max_duration=4.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=1.5,
        )

        self.assertEqual([item["text"] for item in result], ["아", "맞아요"])

    def test_timestamp_regrouper_prefers_word_gap_over_large_gap_setting(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "첫말 다음말",
                    "words": [
                        {"word": "첫말", "start": 0.2, "end": 0.6},
                        {"word": "다음말", "start": 1.35, "end": 1.9},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.1,
            gap_break_sec=5.0,
            word_gap_break_sec=0.65,
        )

        self.assertEqual([item["text"] for item in result], ["첫말", "다음말"])
        self.assertAlmostEqual(result[0]["start"], 0.2)
        self.assertAlmostEqual(result[0]["end"], 0.6)
        self.assertAlmostEqual(result[1]["start"], 1.35)
        self.assertAlmostEqual(result[1]["end"], 1.9)

    def test_timestamp_regrouper_prefers_vad_boundary_over_gap_setting(self):
        result = regroup_by_word_timestamps(
            [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "text": "하나 둘",
                    "words": [
                        {"word": "하나", "start": 0.2, "end": 0.55},
                        {"word": "둘", "start": 0.72, "end": 1.05},
                    ],
                }
            ],
            max_chars=30,
            max_duration=8.0,
            max_cps=20,
            min_duration=0.5,
            gap_break_sec=5.0,
            word_gap_break_sec=0.65,
            vad_segments=[
                {"start": 0.18, "end": 0.58},
                {"start": 0.70, "end": 1.08},
            ],
        )

        self.assertEqual([item["text"] for item in result], ["하나", "둘"])
        self.assertLess(result[0]["end"], result[1]["start"])

    def test_snap_segments_to_word_vad_boundaries_uses_word_edges_then_nearby_vad(self):
        result = snap_segments_to_word_vad_boundaries(
            [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "정확한 시간",
                    "words": [
                        {"word": "정확한", "start": 1.0, "end": 1.4},
                        {"word": "시간", "start": 1.5, "end": 2.0},
                    ],
                }
            ],
            vad_segments=[{"start": 0.96, "end": 2.04}],
            edge_pad_sec=0.04,
            max_edge_shift_sec=0.12,
        )

        self.assertAlmostEqual(result[0]["start"], 0.92)
        self.assertAlmostEqual(result[0]["end"], 2.08)
        self.assertEqual(result[0]["asr_metadata"]["word_vad_timing"]["source"], "whisper_words+vad")

    def test_refine_segment_edges_with_context_snaps_to_words_vad_and_frame(self):
        result = refine_segment_edges_with_context(
            [
                {
                    "start": 0.93,
                    "end": 2.11,
                    "text": "정확한 시간",
                    "words": [
                        {"word": "정확한", "start": 1.0, "end": 1.4},
                        {"word": "시간", "start": 1.5, "end": 2.0},
                    ],
                }
            ],
            vad_segments=[{"start": 0.98, "end": 2.03}],
            frame_rate=10.0,
        )

        self.assertAlmostEqual(result[0]["start"], 1.0)
        self.assertAlmostEqual(result[0]["end"], 2.1)
        self.assertEqual(result[0]["asr_metadata"]["precision_timing"]["source"], "words+vad+frame")

    def test_refine_segment_edges_with_context_keeps_neighbors_non_overlapping(self):
        result = refine_segment_edges_with_context(
            [
                {
                    "start": 0.0,
                    "end": 1.05,
                    "text": "첫말",
                    "words": [{"word": "첫말", "start": 0.1, "end": 1.0}],
                },
                {
                    "start": 1.02,
                    "end": 2.0,
                    "text": "둘째",
                    "words": [{"word": "둘째", "start": 1.02, "end": 1.95}],
                },
            ],
            frame_rate=30.0,
        )

        self.assertLessEqual(result[0]["end"], result[1]["start"])

    def test_refine_segment_edges_with_context_can_prefer_precision_vad_start(self):
        result = refine_segment_edges_with_context(
            [
                {
                    "start": 1.30,
                    "end": 2.11,
                    "text": "정확한 시작",
                    "words": [
                        {"word": "정확한", "start": 1.15, "end": 1.45},
                        {"word": "시작", "start": 1.50, "end": 2.00},
                    ],
                }
            ],
            vad_segments=[
                {
                    "start": 0.98,
                    "end": 2.03,
                    "precision_lattice": True,
                    "source_count": 4,
                    "vad_sources": ["measured_audio:silero", "measured_audio:ten_vad"],
                }
            ],
            max_vad_shift_sec=0.25,
            max_start_shift_sec=0.40,
            prefer_precision_vad_start=True,
        )

        self.assertAlmostEqual(result[0]["start"], 0.96)
        self.assertAlmostEqual(result[0]["end"], 2.08)

    def test_llm_split_preserves_matched_word_timestamps(self):
        segment = {
            "start": 0.0,
            "end": 3.0,
            "text": "첫말 둘 셋",
            "words": [
                {"word": "첫말", "start": 0.1, "end": 0.6},
                {"word": "둘", "start": 1.0, "end": 1.3},
                {"word": "셋", "start": 1.4, "end": 1.8},
            ],
        }

        with mock.patch.object(subtitle_engine, "ask_exaone_to_split", return_value=["첫말", "둘 셋"]):
            result = subtitle_engine._process_one((segment, {}, 3, {}, "exaone3.5:7.8b", "", "", False))

        self.assertEqual([item["text"] for item in result], ["첫말", "둘 셋"])
        self.assertEqual([word["word"] for word in result[0]["words"]], ["첫말"])
        self.assertEqual([word["word"] for word in result[1]["words"]], ["둘", "셋"])
        self.assertAlmostEqual(result[1]["start"], 1.0)
        self.assertAlmostEqual(result[1]["end"], 1.8)

    def test_llm_split_matches_chunk_text_to_later_stt_words(self):
        segment = {
            "start": 136.0,
            "end": 143.0,
            "text": "구와봐 와 말린 과일이네 히프소스",
            "words": [
                {"word": "구와봐", "start": 136.0, "end": 136.4},
                {"word": "와", "start": 136.5, "end": 136.7},
                {"word": "말린", "start": 140.9, "end": 141.2},
                {"word": "과일이네", "start": 141.24, "end": 141.8},
                {"word": "히프소스", "start": 142.1, "end": 142.7},
            ],
        }

        with (
            mock.patch.object(subtitle_engine, "_apply_llm_confidence_gate", return_value=(True, {})),
            mock.patch.object(subtitle_engine, "_verify_llm_chunks", return_value=(["말린 과일이네", "히프소스"], {})),
            mock.patch.object(subtitle_engine, "_deep_rerank_chunks", side_effect=lambda _text, chunks, _settings, lora: (chunks, lora)),
            mock.patch.object(subtitle_engine, "ask_exaone_to_split", return_value=["말린 과일이네", "히프소스"]),
        ):
            result = subtitle_engine._process_one(
                (
                    segment,
                    {},
                    6,
                    {},
                    "exaone3.5:7.8b",
                    "",
                    "",
                    False,
                    {"deep_timing_adjustment_enabled": False},
                )
            )

        self.assertEqual([item["text"] for item in result], ["말린 과일이네", "히프소스"])
        self.assertEqual([word["word"] for word in result[0]["words"]], ["말린", "과일이네"])
        self.assertAlmostEqual(result[0]["start"], 140.9)
        self.assertAlmostEqual(result[0]["end"], 141.8)
        self.assertEqual(result[0]["_stt_word_match_timing_policy"]["source_start_index"], 2)

    def test_llm_split_uses_stt_words_when_chunk_text_diverges(self):
        segment = {
            "start": 79.0,
            "end": 83.0,
            "text": "그냥 가져가 뭐야 뭐야",
            "words": [
                {"word": "그냥", "start": 79.0, "end": 79.3},
                {"word": "가져가", "start": 79.34, "end": 79.9},
                {"word": "뭐야", "start": 80.2, "end": 80.5},
                {"word": "뭐야", "start": 80.7, "end": 81.0},
            ],
        }

        with (
            mock.patch.object(subtitle_engine, "_apply_llm_confidence_gate", return_value=(True, {})),
            mock.patch.object(subtitle_engine, "_verify_llm_chunks", return_value=(["뭐야, 그냥 해, 그냥 해, 그냥 해"], {})),
            mock.patch.object(subtitle_engine, "_deep_rerank_chunks", side_effect=lambda _text, chunks, _settings, lora: (chunks, lora)),
            mock.patch.object(subtitle_engine, "ask_exaone_to_split", return_value=["뭐야, 그냥 해, 그냥 해, 그냥 해"]),
        ):
            result = subtitle_engine._process_one(
                (
                    segment,
                    {},
                    6,
                    {},
                    "exaone3.5:7.8b",
                    "",
                    "",
                    False,
                    {"deep_timing_adjustment_enabled": False},
                )
            )

        self.assertEqual(result[0]["text"], "그냥 가져가 뭐야 뭐야")
        self.assertAlmostEqual(result[0]["start"], 79.0)
        self.assertAlmostEqual(result[0]["end"], 81.0)
        self.assertEqual(result[0]["_llm_stt_text_guard_policy"]["reason"], "llm_chunk_diverged_from_matched_stt_words")

    def test_resegment_preserves_stt_timing_anchor_metadata(self):
        policy = {"task": "stt_chunk_word_timing_match", "source_start_index": 2}
        text_guard = {"task": "llm_stt_text_guard"}
        result = resegment_by_word_timestamps(
            [
                {
                    "start": 140.9,
                    "end": 141.8,
                    "text": "말린 과일이네",
                    "speaker": "00",
                    "speaker_list": ["00", "01"],
                    "speaker2": "01",
                    "_stt_original_candidate_start": 136.0,
                    "_stt_original_candidate_end": 143.0,
                    "_stt_candidate_word_timing_anchor_policy": {"task": "stt_candidate_word_timing_anchor"},
                    "_stt_word_match_timing_policy": policy,
                    "_llm_stt_text_guard_policy": text_guard,
                    "words": [
                        {"word": "말린", "start": 140.9, "end": 141.2, "speaker": "00"},
                        {"word": "과일이네", "start": 141.24, "end": 141.8, "speaker": "00"},
                    ],
                }
            ],
            max_chars=20,
            max_duration=6.0,
            max_cps=20.0,
            min_duration=0.1,
            gap_break_sec=1.5,
        )

        self.assertEqual(result[0]["_stt_original_candidate_start"], 136.0)
        self.assertEqual(result[0]["_stt_word_match_timing_policy"], policy)
        self.assertEqual(result[0]["_llm_stt_text_guard_policy"], text_guard)
        self.assertEqual(result[0]["speaker_list"], ["00", "01"])


if __name__ == "__main__":
    unittest.main()
