# Version: 03.09.23
# Phase: PHASE2
import unittest
from unittest.mock import patch

from core.audio.stt_ensemble import merge_stt_outputs, text_similarity
from core.engine import subtitle_engine
from core.engine.subtitle_engine import _process_one, optimize_segments
from core.pipeline.multiclip_pipeline import MulticlipPipelineMixin
from core.pipeline.single_pipeline import (
    SinglePipelineMixin,
    _should_flush_final_subtitle_buffer,
    _should_flush_live_subtitle_buffer,
)
from core.settings import get_model_key
from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries


class STTEnsembleTests(unittest.TestCase):
    def test_multiclip_offsets_stt_candidate_timestamps(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "최종",
                "stt_candidates": [
                    {
                        "source": "STT2",
                        "start": 1.0,
                        "end": 2.0,
                        "text": "후보",
                        "words": [{"word": "후보", "start": 1.1, "end": 1.8}],
                    }
                ],
            }
        ]

        MulticlipPipelineMixin()._offset_multiclip_segments(segments, 10.0, 1, "/tmp/b.mp4")

        self.assertEqual(segments[0]["_clip_idx"], 1)
        self.assertAlmostEqual(segments[0]["stt_candidates"][0]["start"], 11.0)
        self.assertAlmostEqual(segments[0]["stt_candidates"][0]["end"], 12.0)
        self.assertAlmostEqual(segments[0]["stt_candidates"][0]["words"][0]["start"], 11.1)

    def test_merge_keeps_two_candidates_for_overlapping_segments(self):
        primary = [
            {"start": 0.0, "end": 1.2, "text": "안녕하세요", "avg_logprob": -0.2, "no_speech_prob": 0.02},
        ]
        secondary = [
            {"start": 0.05, "end": 1.25, "text": "안녕 하세요", "avg_logprob": -0.4, "no_speech_prob": 0.03},
        ]

        merged = merge_stt_outputs(primary, secondary)

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["stt_candidates"]), 2)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "안녕하세요")
        self.assertAlmostEqual(merged[0]["start"], 0.0)
        self.assertAlmostEqual(merged[0]["end"], 1.2)
        self.assertGreater(merged[0]["stt_ensemble_similarity"], 0.8)

    def test_merge_preserves_secondary_only_segments(self):
        merged = merge_stt_outputs(
            [{"start": 0.0, "end": 1.0, "text": "첫 문장"}],
            [{"start": 2.0, "end": 3.0, "text": "두 번째 문장"}],
        )

        self.assertEqual([seg["text"] for seg in merged], ["첫 문장", "두 번째 문장"])
        self.assertEqual(merged[1]["stt_ensemble_source"], "STT2")

    def test_merge_drops_secondary_duplicate_even_when_text_differs(self):
        merged = merge_stt_outputs(
            [{"start": 10.0, "end": 12.0, "text": "망고 보여 봐"}],
            [{"start": 10.1, "end": 12.1, "text": "방금 보아 봐 말린 과일이네"}],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "망고 보여 봐")

    def test_low_confidence_primary_can_be_replaced_by_secondary(self):
        merged = merge_stt_outputs(
            [{
                "start": 0.0,
                "end": 1.6,
                "text": "망고 보여 봐",
                "avg_logprob": -1.2,
                "no_speech_prob": 0.08,
                "compression_ratio": 1.1,
            }],
            [{
                "start": 0.02,
                "end": 1.55,
                "text": "방금 보여 봐",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.01,
                "compression_ratio": 1.0,
            }],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT2")
        self.assertEqual(merged[0]["text"], "방금 보여 봐")
        self.assertTrue(merged[0]["stt_ensemble_needs_llm_review"])

    def test_word_level_rover_replaces_only_weak_primary_word(self):
        merged = merge_stt_outputs(
            [{
                "start": 0.0,
                "end": 1.8,
                "text": "망고 보여 봐",
                "avg_logprob": -0.95,
                "no_speech_prob": 0.02,
                "words": [
                    {"word": "망고", "start": 0.0, "end": 0.5, "confidence": 0.21},
                    {"word": "보여", "start": 0.55, "end": 1.0, "confidence": 0.82},
                    {"word": "봐", "start": 1.05, "end": 1.35, "confidence": 0.87},
                ],
            }],
            [{
                "start": 0.02,
                "end": 1.75,
                "text": "방금 보여 봐",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.01,
                "words": [
                    {"word": "방금", "start": 0.02, "end": 0.52, "confidence": 0.91},
                    {"word": "보여", "start": 0.56, "end": 1.02, "confidence": 0.8},
                    {"word": "봐", "start": 1.06, "end": 1.34, "confidence": 0.79},
                ],
            }],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "ROVER")
        self.assertEqual(merged[0]["text"], "방금 보여 봐")
        self.assertEqual(merged[0]["stt_ensemble_word_rover"]["replaced"], 1)
        self.assertEqual([w["stt_word_source"] for w in merged[0]["words"]], ["STT2", "STT1", "STT1"])

    def test_word_level_rover_keeps_protected_number_from_primary(self):
        merged = merge_stt_outputs(
            [{
                "start": 0.0,
                "end": 1.2,
                "text": "3번 카메라",
                "avg_logprob": -0.95,
                "words": [
                    {"word": "3번", "start": 0.0, "end": 0.45, "confidence": 0.25},
                    {"word": "카메라", "start": 0.5, "end": 1.1, "confidence": 0.8},
                ],
            }],
            [{
                "start": 0.0,
                "end": 1.2,
                "text": "이번 카메라",
                "avg_logprob": -0.1,
                "words": [
                    {"word": "이번", "start": 0.0, "end": 0.45, "confidence": 0.95},
                    {"word": "카메라", "start": 0.5, "end": 1.1, "confidence": 0.86},
                ],
            }],
        )

        self.assertEqual(merged[0]["text"], "3번 카메라")
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")

    def test_secondary_overlap_never_trims_primary_segment(self):
        merged = merge_stt_outputs(
            [{"start": 0.0, "end": 4.0, "text": "STT1 기준 문장"}],
            [{"start": 3.6, "end": 5.0, "text": "STT2 겹친 문장"}],
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(merged[0]["text"], "STT1 기준 문장")
        self.assertAlmostEqual(merged[0]["start"], 0.0)
        self.assertAlmostEqual(merged[0]["end"], 4.0)

    def test_secondary_insert_only_when_primary_has_real_gap(self):
        merged = merge_stt_outputs(
            [
                {"start": 0.0, "end": 1.0, "text": "첫 문장"},
                {"start": 3.0, "end": 4.0, "text": "셋째 문장"},
            ],
            [{"start": 1.4, "end": 2.3, "text": "빠진 둘째 문장", "avg_logprob": -0.3}],
        )

        self.assertEqual([seg["text"] for seg in merged], ["첫 문장", "빠진 둘째 문장", "셋째 문장"])
        self.assertEqual(merged[1]["stt_ensemble_source"], "STT2")
        self.assertEqual(merged[1]["stt_ensemble_inserted_from_stt2"], True)
        self.assertEqual(merged[1]["stt_ensemble_needs_llm_review"], True)

    def test_model_key_includes_secondary_stt_when_ensemble_enabled(self):
        key = get_model_key(
            {
                "selected_whisper_model": "large-v3",
                "selected_whisper_model_secondary": "ghost613/faster-whisper-large-v3-turbo-korean",
                "stt_ensemble_enabled": True,
                "selected_model": "exaone3.5",
                "max_speakers": 1,
            }
        )

        self.assertIn("large-v3+ghost613/faster-whisper-large-v3-turbo-korean", key)

    def test_subtitle_buffer_flushes_live_regardless_of_ensemble(self):
        self.assertTrue(
            _should_flush_final_subtitle_buffer(
                0.8,
                60,
                stt_ensemble_enabled=True,
            )
        )
        self.assertTrue(
            _should_flush_final_subtitle_buffer(
                300.0,
                60,
                stt_ensemble_enabled=False,
            )
        )

    def test_all_modes_flush_chunks_for_live_progress(self):
        self.assertTrue(
            _should_flush_live_subtitle_buffer(
                1.0,
                60,
                stt_ensemble_enabled=False,
                individual_queue_mode=True,
            )
        )
        self.assertTrue(
            _should_flush_live_subtitle_buffer(
                1.0,
                60,
                stt_ensemble_enabled=True,
                individual_queue_mode=True,
            )
        )
        self.assertTrue(
            _should_flush_live_subtitle_buffer(
                1.0,
                60,
                stt_ensemble_enabled=False,
                individual_queue_mode=False,
            )
        )

    def test_individual_queue_appends_segments_one_by_one(self):
        class Pipeline(SinglePipelineMixin):
            def __init__(self):
                self._individual_queue_mode = True
                self._active = True
                self.calls = []

            def _ui_attr(self, name, default=None):
                if name == "append_segments_to_editor_and_wait":
                    return lambda segments, timeout_sec=2.0: self.calls.append(list(segments))
                return default

            def _ui_call(self, method_name, *args, **kwargs):
                method = self._ui_attr(method_name)
                if callable(method):
                    method(*args, **kwargs)
                    return True
                return False

            def _ui_is_alive(self):
                return True

            def _ui_emit(self, signal_name, *args):
                self.calls.append(("emit", signal_name, args))
                return True

        pipeline = Pipeline()
        with patch("core.pipeline.single_pipeline.time.sleep", return_value=None):
            pipeline._append_live_segments_to_editor([
                {"start": 0.0, "end": 1.0, "text": "첫 자막"},
                {"start": 1.0, "end": 2.0, "text": "둘째 자막"},
            ])

        self.assertEqual(
            pipeline.calls,
            [
                [{"start": 0.0, "end": 1.0, "text": "첫 자막"}],
                [{"start": 1.0, "end": 2.0, "text": "둘째 자막"}],
            ],
        )

    def test_text_similarity_compacts_whitespace_and_punctuation(self):
        self.assertGreater(text_similarity("안녕 하세요!", "안녕하세요"), 0.9)

    def test_vad_post_alignment_snaps_ensemble_boundaries(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.5,
                "text": "안녕하세요",
                "stt_candidates": [{"source": "STT1", "text": "안녕하세요"}],
            }
        ]
        vad = [{"start": 0.18, "end": 1.18, "post_stt_align": True, "vad_word_filter": False}]

        adjusted, count = adjust_segments_to_vad_boundaries(segments, vad, max_shift_sec=0.7, edge_pad_sec=0.04)

        self.assertEqual(count, 1)
        self.assertAlmostEqual(adjusted[0]["start"], 0.14)
        self.assertAlmostEqual(adjusted[0]["end"], 1.22)
        self.assertEqual(adjusted[0]["asr_metadata"]["vad_alignment"]["vad_aligned"], True)

    def test_llm_candidate_judge_keeps_selected_source_metadata(self):
        seg = {
            "start": 0.0,
            "end": 1.5,
            "text": "STT1 문장",
            "speaker": "00",
            "stt_candidates": [
                {"source": "STT1", "text": "STT1 문장", "score": 0.4},
                {"source": "STT2", "text": "STT2 문장", "score": 0.8},
            ],
        }

        with (
            patch("core.engine.subtitle_engine._get_user_settings", return_value={"stt_ensemble_llm_judge_enabled": True}),
            patch("core.engine.subtitle_engine._local_ollama_ready", return_value=True),
            patch("core.engine.subtitle_engine._resolve_runtime_llm_model", side_effect=lambda model, **_: model),
            patch("core.engine.subtitle_engine.ollama_split_text", return_value=["B"]),
        ):
            result = _process_one((seg, {}, 10, {}, "gemma4:e4b", "", "", True))

        self.assertEqual(result[0]["text"], "STT2 문장")
        self.assertEqual(result[0]["stt_ensemble_llm_selected_source"], "STT2")
        self.assertEqual(result[0]["stt_ensemble_llm_selected_label"], "B")

    def test_llm_candidate_judge_runs_even_when_primary_is_locked(self):
        seg = {
            "start": 0.0,
            "end": 1.5,
            "text": "STT1 문장",
            "speaker": "00",
            "stt_ensemble_primary_locked": True,
            "stt_candidates": [
                {"source": "STT1", "text": "STT1 문장", "score": 0.7},
                {"source": "STT2", "text": "문맥상 맞는 STT2", "score": 0.5},
            ],
            "stt_ensemble_context_prev": "앞 문맥",
            "stt_ensemble_context_next": "다음 문맥",
        }

        prompts = []

        def _fake_ollama(_model, prompt):
            prompts.append(prompt)
            return ["B"]

        with (
            patch("core.engine.subtitle_engine._get_user_settings", return_value={"stt_ensemble_llm_judge_enabled": True}),
            patch("core.engine.subtitle_engine._local_ollama_ready", return_value=True),
            patch("core.engine.subtitle_engine._resolve_runtime_llm_model", side_effect=lambda model, **_: model),
            patch("core.engine.subtitle_engine.ollama_split_text", side_effect=_fake_ollama),
        ):
            result = _process_one((seg, {}, 10, {}, "gemma4:e4b", "", "", True))

        self.assertEqual(result[0]["text"], "문맥상 맞는 STT2")
        self.assertEqual(result[0]["stt_ensemble_llm_selected_source"], "STT2")
        self.assertIn("앞 문맥", prompts[0])
        self.assertIn("다음 문맥", prompts[0])

    def test_optimize_recovers_ensemble_segments_if_filters_drop_all_candidates(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.4,
                "text": "STT1 후보",
                "speaker": "00",
                "stt_candidates": [
                    {"source": "STT1", "text": "STT1 후보", "score": 0.7},
                    {"source": "STT2", "text": "STT2 후보", "score": 0.6},
                ],
            }
        ]

        with (
            patch("core.engine.subtitle_engine.get_selected_llm", return_value="사용 안함 (Whisper 단독 진행)"),
            patch("core.engine.subtitle_engine._sanitize", return_value=[]),
        ):
            result = optimize_segments(segments)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "STT1 후보")

    def test_local_llm_connection_refused_is_logged_once_and_falls_back(self):
        class Logger:
            def __init__(self):
                self.lines = []

            def log(self, line):
                self.lines.append(str(line))

        logger = Logger()
        seg = {
            "start": 0.0,
            "end": 1.5,
            "text": "STT1 문장",
            "speaker": "00",
            "stt_candidates": [
                {"source": "STT1", "text": "STT1 문장", "score": 0.4},
                {"source": "STT2", "text": "STT2 문장", "score": 0.8},
            ],
        }

        subtitle_engine._LOCAL_LLM_UNAVAILABLE_UNTIL = 0.0
        try:
            with (
                patch("core.engine.subtitle_engine.get_logger", return_value=logger),
                patch("core.engine.subtitle_engine.ensure_ollama_server", return_value=False) as ensure_mock,
                patch("core.engine.subtitle_engine.restart_ollama_server", return_value=False) as restart_mock,
                patch("core.engine.subtitle_engine.ollama_split_text") as split_mock,
            ):
                first = _process_one((dict(seg), {}, 10, {}, "gemma4:e4b", "", "", True))
                second = _process_one((dict(seg), {}, 10, {}, "gemma4:e4b", "", "", True))
        finally:
            subtitle_engine._LOCAL_LLM_UNAVAILABLE_UNTIL = 0.0

        self.assertEqual(first[0]["text"], "STT1 문장")
        self.assertEqual(second[0]["text"], "STT1 문장")
        self.assertEqual(ensure_mock.call_count, 1)
        restart_mock.assert_called_once()
        split_mock.assert_not_called()
        self.assertEqual(sum("Ollama 연결 실패" in line for line in logger.lines), 1)


if __name__ == "__main__":
    unittest.main()
