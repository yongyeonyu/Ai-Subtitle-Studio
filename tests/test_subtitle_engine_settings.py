# Version: 03.10.03
# Phase: PHASE2
import unittest
import unittest.mock
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

from core.runtime import config
from core.engine import subtitle_engine
from core.engine.llm_candidate_policy import build_llm_candidate_options


class SubtitleEngineSettingsTests(unittest.TestCase):
    def test_final_gap_settings_apply_as_last_timing_pass(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 2.0, "end": 3.0, "text": "B"},
            {"start": 6.0, "end": 7.0, "text": "C"},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "continuous_threshold": 1.5,
                "gap_push_rate": 0.8,
                "gap_pull_rate": 0.2,
                "single_subtitle_end": 0.2,
                "sub_min_duration": 0.2,
            },
        )

        self.assertEqual([seg["text"] for seg in adjusted], ["A", "B", "C"])
        self.assertAlmostEqual(adjusted[0]["end"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["end"], 3.2, places=3)
        self.assertAlmostEqual(adjusted[2]["start"], 5.8, places=3)
        self.assertTrue(all(seg.get("_final_gap_settings_applied") for seg in adjusted))

    def test_final_gap_settings_do_not_pull_across_multiclip_boundaries(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "A", "_clip_idx": 0},
            {"start": 2.0, "end": 3.0, "text": "B", "_clip_idx": 1},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.8,
                "gap_pull_rate": 0.2,
                "single_subtitle_end": 0.2,
            },
        )

        self.assertAlmostEqual(adjusted[0]["end"], 1.2, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 2.0, places=3)

    def test_final_gap_settings_do_not_pull_across_confirmed_cut_scene(self):
        segments = [
            {
                "start": 0.0,
                "end": 2.8,
                "text": "A",
                "cut_scene_index": 0,
                "cut_scene_start": 0.0,
                "cut_scene_end": 3.0,
            },
            {
                "start": 3.2,
                "end": 4.0,
                "text": "B",
                "cut_scene_index": 1,
                "cut_scene_start": 3.0,
            },
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "continuous_threshold": 1.0,
                "gap_push_rate": 0.8,
                "gap_pull_rate": 0.2,
                "single_subtitle_end": 0.4,
                "sub_min_duration": 0.2,
            },
            force=True,
        )

        self.assertLessEqual(adjusted[0]["end"], 3.0)
        self.assertAlmostEqual(adjusted[1]["start"], 3.2, places=3)
        self.assertEqual(adjusted[0]["_cut_boundary_guard_policy"]["action"], "clamped_to_cut_scene")

    def test_final_gap_settings_allows_high_confidence_cut_crossing_exception(self):
        segments = [
            {
                "start": 2.0,
                "end": 3.2,
                "text": "강한 근거 자막",
                "cut_scene_index": 0,
                "cut_scene_start": 0.0,
                "cut_scene_end": 3.0,
                "_lora_generation_profile": {"top_score": 98.0},
            },
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "single_subtitle_end": 0.0,
                "sub_min_duration": 0.2,
                "subtitle_cut_boundary_high_confidence_score": 96.0,
            },
            force=True,
        )

        self.assertAlmostEqual(adjusted[0]["end"], 3.2, places=3)
        self.assertEqual(
            adjusted[0]["_cut_boundary_guard_policy"]["action"],
            "allowed_high_confidence_crossing",
        )
        policy = adjusted[0]["_cut_boundary_guard_policy"]
        self.assertTrue(policy["hard_cut_crossing_exception"])
        self.assertGreaterEqual(policy["evidence"]["combined_confidence"], policy["evidence"]["threshold"])

    def test_final_gap_settings_are_idempotent_when_already_applied(self):
        segments = [
            {"start": 0.0, "end": 1.8, "text": "A", "_final_gap_settings_applied": True},
            {"start": 1.8, "end": 3.0, "text": "B", "_final_gap_settings_applied": True},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {"continuous_threshold": 2.0, "gap_push_rate": 0.8, "gap_pull_rate": 0.2},
        )

        self.assertAlmostEqual(adjusted[0]["end"], 1.8, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 1.8, places=3)

    def test_common_split_guard_applies_to_fast_auto_high_modes(self):
        text = "여기 안에 들어가 있는 것도 똑같고 저기 방향제도 똑같고 이번에는 동일한 차를 그냥 2대를 만드셨네"
        tokens = text.split()
        words = [
            {
                "word": token,
                "start": round(index * (9.9 / len(tokens)), 3),
                "end": round((index + 1) * (9.9 / len(tokens)), 3),
            }
            for index, token in enumerate(tokens)
        ]

        for mode in ("fast", "auto", "high"):
            with self.subTest(mode=mode):
                adjusted = subtitle_engine.apply_final_gap_settings(
                    [
                        {
                            "start": 0.0,
                            "end": 9.9,
                            "text": text,
                            "words": words,
                            "_final_gap_settings_applied": True,
                        }
                    ],
                    {
                        "subtitle_mode": mode,
                        "single_subtitle_end": 0.0,
                        "split_length_threshold": 10,
                        "sub_min_duration": 0.2,
                        "sub_max_duration": 6.0,
                        "subtitle_common_split_guard_enabled": True,
                        "subtitle_common_split_target_chars": 16,
                        "subtitle_common_split_hard_max_chars": 24,
                        "subtitle_common_split_hard_max_duration_sec": 5.5,
                    },
                )

                self.assertGreater(len(adjusted), 1)
                self.assertEqual(
                    "".join("".join(seg["text"].split()) for seg in adjusted),
                    "".join(text.split()),
                )
                self.assertTrue(
                    all(len(seg["text"].replace(" ", "").replace("\n", "")) <= 24 for seg in adjusted)
                )
                self.assertTrue(all(seg["end"] - seg["start"] <= 5.5 for seg in adjusted))
                self.assertTrue(
                    all(
                        seg.get("_common_split_guard_policy", {}).get("action") == "split"
                        for seg in adjusted
                    )
                )
                self.assertTrue(all(seg.get("_final_gap_settings_applied") for seg in adjusted))

    def test_swift_common_split_bridge_matches_python_when_available(self):
        from core.native_swift_subtitle import find_native_cli_path

        if find_native_cli_path() is None:
            self.skipTest("native Swift CLI is not built")

        text = "여기 안에 들어가 있는 것도 똑같고 저기 방향제도 똑같고 이번에는 동일한 차를 그냥 2대를 만드셨네"
        tokens = text.split()
        words = [
            {
                "word": token,
                "start": round(index * (9.9 / len(tokens)), 3),
                "end": round((index + 1) * (9.9 / len(tokens)), 3),
            }
            for index, token in enumerate(tokens)
        ]
        segments = [
            {
                "start": 0.0,
                "end": 9.9,
                "text": text,
                "words": words,
                "_final_gap_settings_applied": True,
            }
        ]
        settings = {
            "subtitle_mode": "high",
            "single_subtitle_end": 0.0,
            "split_length_threshold": 10,
            "sub_min_duration": 0.2,
            "sub_max_duration": 6.0,
            "subtitle_common_split_guard_enabled": True,
            "subtitle_common_split_target_chars": 16,
            "subtitle_common_split_hard_max_chars": 24,
            "subtitle_common_split_hard_max_duration_sec": 5.5,
        }
        with unittest.mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_SWIFT_COMMON_SPLIT": "0"}, clear=False):
            python_result = subtitle_engine.apply_final_gap_settings(segments, settings)
        with unittest.mock.patch.dict(os.environ, {"AI_SUBTITLE_STUDIO_SWIFT_COMMON_SPLIT": "1"}, clear=False):
            swift_result = subtitle_engine.apply_final_gap_settings(segments, settings)

        self.assertEqual(
            [(seg["text"], round(seg["start"], 3), round(seg["end"], 3)) for seg in swift_result],
            [(seg["text"], round(seg["start"], 3), round(seg["end"], 3)) for seg in python_result],
        )
        self.assertTrue(all(seg.get("_common_split_guard_policy", {}).get("action") == "split" for seg in swift_result))

    def test_final_gap_settings_use_segment_lora_overrides(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "A",
                "_lora_gap_settings": {
                    "continuous_threshold": 3.0,
                    "gap_push_rate": 1.0,
                    "single_subtitle_end": 0.0,
                },
            },
            {"start": 3.0, "end": 4.0, "text": "B"},
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {"continuous_threshold": 0.5, "gap_push_rate": 0.0, "single_subtitle_end": 0.0},
            force=True,
        )

        self.assertAlmostEqual(adjusted[0]["end"], 3.0, places=3)
        self.assertAlmostEqual(adjusted[1]["start"], 3.0, places=3)

    def test_final_gap_settings_apply_timing_fusion_evidence(self):
        segments = [
            {
                "start": 0.0,
                "end": 2.8,
                "text": "주행 소음 확인",
                "words": [
                    {"word": "주행", "start": 0.22, "end": 0.55},
                    {"word": "소음", "start": 0.62, "end": 0.95},
                    {"word": "확인", "start": 1.02, "end": 1.42},
                ],
                "voice_activity_segments": [{"start": 0.2, "end": 1.5}],
                "audio_energy_boundaries": [{"timeline_sec": 0.18}, {"timeline_sec": 1.52}],
                "_lora_generation_profile": {
                    "examples": [{"text": "주행 소음 확인", "duration_sec": 1.5, "score": 92.0}],
                },
            }
        ]

        adjusted = subtitle_engine.apply_final_gap_settings(
            segments,
            {
                "subtitle_timing_fusion_enabled": True,
                "subtitle_timing_fusion_max_shift_sec": 0.4,
                "subtitle_timing_fusion_boundary_snap_window_sec": 0.15,
                "sub_min_duration": 0.2,
                "single_subtitle_end": 0.0,
            },
            force=True,
        )

        policy = adjusted[0].get("_timing_fusion_policy", {})
        sources = {item.get("source") for item in policy.get("evidence", [])}
        self.assertGreater(adjusted[0]["start"], 0.0)
        self.assertLess(adjusted[0]["end"], 2.8)
        self.assertIn("word_timestamp", sources)
        self.assertIn("vad", sources)
        self.assertIn("lora_duration", sources)

    def test_enforce_len_preserves_segment_lora_metadata(self):
        segments = [
            {
                "start": 0.0,
                "end": 4.0,
                "text": "가나 다라 마바 사아",
                "speaker": "SPEAKER_00",
                "words": [
                    {"word": "가나", "start": 0.0, "end": 0.8},
                    {"word": "다라", "start": 0.9, "end": 1.7},
                    {"word": "마바", "start": 1.8, "end": 2.6},
                    {"word": "사아", "start": 2.7, "end": 3.5},
                ],
                "_lora_segment_settings": {"split_length_threshold": 4},
                "_lora_gap_settings": {"sub_gap_break_sec": 1.1},
                "_lora_generation_profile": {"top_score": 91.0},
                "_lora_segment_score": 91.0,
                "_llm_gate_policy": {"task": "llm_gate", "call_llm": False},
                "_llm_verifier_policy": {"task": "llm_verifier", "accepted": True},
                "_accuracy_decision_graph": {"schema": "ai_subtitle_studio.subtitle_accuracy_pipeline.v1", "decisions": []},
            }
        ]

        result = subtitle_engine._enforce_len(segments, threshold=4, rules={})

        self.assertGreater(len(result), 1)
        self.assertTrue(all(seg.get("_lora_segment_settings") == {"split_length_threshold": 4} for seg in result))
        self.assertTrue(all(seg.get("_lora_gap_settings") == {"sub_gap_break_sec": 1.1} for seg in result))
        self.assertTrue(all(seg.get("_lora_generation_profile") == {"top_score": 91.0} for seg in result))
        self.assertTrue(all(seg.get("_llm_gate_policy", {}).get("call_llm") is False for seg in result))
        self.assertTrue(all(seg.get("_llm_verifier_policy", {}).get("accepted") is True for seg in result))

    def test_verify_llm_chunks_blocks_candidate_policy_violations(self):
        source = "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다"
        settings = {
            "accuracy_decision_graph_enabled": True,
            "llm_candidate_policy_enabled": True,
            "llm_candidate_policy_max_edit_ratio": 0.08,
        }
        candidates = build_llm_candidate_options(source, threshold=8, settings=settings)

        accepted, accepted_meta = subtitle_engine._verify_llm_chunks(
            source,
            candidates[0]["chunks"],
            settings,
            {},
            fallback="safe_split",
            candidate_options=candidates,
        )
        rejected, rejected_meta = subtitle_engine._verify_llm_chunks(
            source,
            ["완전히 다른 설명을 새로 추가했습니다"],
            settings,
            {},
            fallback="safe_split",
            candidate_options=candidates,
        )

        self.assertEqual(accepted, candidates[0]["chunks"])
        self.assertTrue(accepted_meta["_llm_candidate_policy"]["accepted"])
        self.assertIsNone(rejected)
        self.assertFalse(rejected_meta["_llm_candidate_policy"]["accepted"])
        self.assertEqual(rejected_meta["_llm_rollback_policy"]["fallback"], "safe_split")

    def test_setting_int_uses_fallback_and_default_for_invalid_values(self):
        self.assertEqual(
            subtitle_engine._setting_int(
                {"llm_threads": "", "llm_workers": 7},
                "llm_threads",
                6,
                fallback_key="llm_workers",
            ),
            7,
        )
        self.assertEqual(
            subtitle_engine._setting_int(
                {"llm_threads": "bad", "llm_workers": 7},
                "llm_threads",
                6,
                fallback_key="llm_workers",
            ),
            6,
        )

    def test_setting_float_uses_default_for_blank_or_invalid_values(self):
        self.assertEqual(
            subtitle_engine._setting_float(
                {"sub_gap_break_sec": ""},
                "sub_gap_break_sec",
                1.5,
            ),
            1.5,
        )

    def test_clean_strips_whisper_control_tokens(self):
        cleaned = subtitle_engine._clean("<|startoftranscript|><|6.78|> 이게 펠리칸입니다")

        self.assertEqual(cleaned, "이게 펠리칸입니다")

    def test_clean_strips_periods_reintroduced_by_corrections(self):
        cleaned = subtitle_engine._clean("안녕", {"안녕": "안녕."})

        self.assertEqual(cleaned, "안녕")

    def test_final_text_policy_strips_source_variant_periods(self):
        result = subtitle_engine._enforce_final_subtitle_text_policy(
            [{"start": 0.0, "end": 1.0, "text": "안녕하세요. 반갑습니다."}],
            None,
        )

        self.assertEqual(result[0]["text"], "안녕하세요 반갑습니다")

    def test_save_srt_strips_periods_as_final_guard(self):
        from core.engine.srt_writer import save_srt

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "period_guard.srt")
            save_srt([{"start": 0.0, "end": 1.0, "text": "안녕하세요."}], path, apply_offset=False)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        self.assertIn("안녕하세요", content)
        self.assertNotIn("안녕하세요.", content)

    def test_save_srt_aligns_frame_grid_before_timestamp_output(self):
        from core.engine.srt_writer import save_srt

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "frame_grid.srt")
            save_srt(
                [
                    {"start": 0.999, "end": 2.001, "text": "프레임 정렬"},
                    {"start": 2.001, "end": 3.467, "text": "다음 줄"},
                ],
                path,
                apply_offset=False,
                fps=30.0,
            )
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        self.assertIn("00:00:01,000 --> 00:00:02,000", content)
        self.assertIn("00:00:02,000 --> 00:00:03,467", content)

    def test_project_text_asset_srt_strips_periods(self):
        from core.project.project_assets import write_srt_track

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assets", "final.srt")
            info = write_srt_track([{"start": 0.0, "end": 1.0, "text": "프로젝트 저장."}], path)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        self.assertEqual(info["rows"][0]["text"], "프로젝트 저장")
        self.assertNotIn("프로젝트 저장.", content)

    def test_project_text_asset_srt_uses_frame_aligned_bounds(self):
        from core.project.project_assets import write_srt_track

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assets", "aligned.srt")
            info = write_srt_track(
                [
                    {
                        "start": 0.999,
                        "end": 2.001,
                        "text": "프로젝트 프레임",
                        "timeline_frame_rate": 30.0,
                    }
                ],
                path,
            )
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        self.assertIn("00:00:01,000 --> 00:00:02,000", content)
        self.assertAlmostEqual(info["rows"][0]["start"], 1.0, places=6)
        self.assertAlmostEqual(info["rows"][0]["end"], 2.0, places=6)

    def test_process_one_strips_whisper_tokens_before_builtin_split(self):
        segment = {
            "start": 0.0,
            "end": 3.0,
            "text": "<|startoftranscript|><|6.78|> 이게 펠리칸입니다 다음 설명입니다",
            "words": [
                {"word": "<|startoftranscript|>", "start": 0.0, "end": 0.01},
                {"word": "<|6.78|>", "start": 0.01, "end": 0.02},
                {"word": "이게", "start": 0.02, "end": 0.4},
                {"word": "펠리칸입니다", "start": 0.45, "end": 1.2},
                {"word": "다음", "start": 1.25, "end": 1.7},
                {"word": "설명입니다", "start": 1.75, "end": 2.6},
            ],
        }

        result = subtitle_engine._process_one((segment, {}, 8, {}, "사용 안함", "", "", False, {}))

        self.assertTrue(result)
        self.assertNotIn("<|", " ".join(item["text"] for item in result))

    def test_local_ollama_workers_are_capped(self):
        workers, mode = subtitle_engine._effective_llm_workers(
            "gemma4:e4b",
            configured_workers=6,
            settings={"llm_threads_auto_enabled": False, "local_ollama_llm_max_workers": 2},
            segment_count=226,
        )

        self.assertEqual(mode, "local")
        self.assertEqual(workers, 2)

    def test_local_ollama_workers_can_use_resource_auto_mode(self):
        workers, mode = subtitle_engine._effective_llm_workers(
            "gemma4:e4b",
            configured_workers=6,
            settings={"llm_threads_auto_enabled": True},
            segment_count=12,
        )

        self.assertEqual(mode, "local_auto")
        self.assertGreaterEqual(workers, 1)
        self.assertLessEqual(workers, 12)

    def test_stt_candidate_optimizer_does_not_call_llm(self):
        segments = [
            {
                "start": 0.0,
                "end": 4.0,
                "text": "오늘은 비엠더블유 행사장에 왔습니다",
                "words": [
                    {"word": "오늘은", "start": 0.0, "end": 0.5},
                    {"word": "비엠더블유", "start": 0.55, "end": 1.2},
                    {"word": "행사장에", "start": 1.25, "end": 2.0},
                    {"word": "왔습니다", "start": 2.05, "end": 2.8},
                ],
            }
        ]

        with unittest.mock.patch("core.engine.subtitle_engine.ask_exaone_to_split") as ask_llm:
            result = subtitle_engine.optimize_stt_candidate_segments(segments)

        ask_llm.assert_not_called()
        self.assertTrue(result)
        self.assertTrue(all(seg.get("_final_gap_settings_applied") for seg in result))

    def test_llm_confidence_gate_skips_provider_when_profile_is_strong(self):
        segment = {
            "start": 0.0,
            "end": 2.0,
            "text": "오늘은 행사장에 왔습니다 바로 시작합니다",
            "words": [
                {"word": "오늘은", "start": 0.0, "end": 0.3},
                {"word": "행사장에", "start": 0.35, "end": 0.8},
                {"word": "왔습니다", "start": 0.85, "end": 1.2},
                {"word": "바로", "start": 1.25, "end": 1.5},
                {"word": "시작합니다", "start": 1.55, "end": 1.9},
            ],
        }
        runtime_settings = {
            "subtitle_quality_auto_correct_enabled": False,
            "editor_lora_runtime_enabled": False,
            "deep_subtitle_policy_enabled": False,
            "llm_confidence_gate_enabled": True,
            "llm_confidence_gate_min_lora_score": 82.0,
            "llm_confidence_gate_max_compact_ratio": 1.45,
            "split_length_threshold": 16,
            "sub_max_duration": 6.0,
            "_lora_generation_profile": {"top_score": 95.0},
        }

        with unittest.mock.patch("core.engine.subtitle_engine.ask_exaone_to_split") as ask_llm:
            result = subtitle_engine._process_one_llm_only(
                (segment, {}, 16, {}, "exaone3.5:7.8b", "", "", False, runtime_settings)
            )

        ask_llm.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].get("_llm_gate_policy", {}).get("call_llm", True))

    def test_llm_confidence_gate_skips_gemini_and_openai_providers(self):
        segment = {
            "start": 0.0,
            "end": 2.0,
            "text": "오늘은 행사장에 왔습니다 바로 시작합니다",
            "words": [
                {"word": "오늘은", "start": 0.0, "end": 0.3},
                {"word": "행사장에", "start": 0.35, "end": 0.8},
                {"word": "왔습니다", "start": 0.85, "end": 1.2},
                {"word": "바로", "start": 1.25, "end": 1.5},
                {"word": "시작합니다", "start": 1.55, "end": 1.9},
            ],
        }
        runtime_settings = {
            "subtitle_quality_auto_correct_enabled": False,
            "editor_lora_runtime_enabled": False,
            "deep_subtitle_policy_enabled": False,
            "llm_confidence_gate_enabled": True,
            "llm_confidence_gate_min_lora_score": 82.0,
            "llm_confidence_gate_max_compact_ratio": 1.45,
            "split_length_threshold": 16,
            "sub_max_duration": 6.0,
            "_lora_generation_profile": {"top_score": 95.0},
        }

        with unittest.mock.patch("core.engine.subtitle_engine.ask_gemini_to_split") as ask_gemini:
            gemini_result = subtitle_engine._process_one_llm_only(
                (segment, {}, 16, {}, "Gemini 1.5", "", "", False, runtime_settings)
            )
        with unittest.mock.patch("core.engine.subtitle_engine.ask_openai_to_split") as ask_openai, \
                unittest.mock.patch("core.engine.subtitle_engine.is_openai_model", return_value=True):
            openai_result = subtitle_engine._process_one_llm_only(
                (segment, {}, 16, {}, "gpt-test", "", "", False, runtime_settings)
            )

        ask_gemini.assert_not_called()
        ask_openai.assert_not_called()
        self.assertFalse(gemini_result[0].get("_llm_gate_policy", {}).get("call_llm", True))
        self.assertFalse(openai_result[0].get("_llm_gate_policy", {}).get("call_llm", True))

    def test_optimize_segments_batches_llm_into_macro_chunks(self):
        segments = [
            {
                "start": float(index * 2),
                "end": float(index * 2 + 1.4),
                "text": f"테스트 문장 {index} 입니다",
                "words": [
                    {"word": "테스트", "start": float(index * 2), "end": float(index * 2 + 0.3)},
                    {"word": "문장", "start": float(index * 2 + 0.35), "end": float(index * 2 + 0.7)},
                    {"word": str(index), "start": float(index * 2 + 0.75), "end": float(index * 2 + 0.95)},
                    {"word": "입니다", "start": float(index * 2 + 1.0), "end": float(index * 2 + 1.3)},
                ],
            }
            for index in range(12)
        ]
        settings = {
            "subtitle_llm_macro_chunk_enabled": True,
            "subtitle_llm_macro_chunk_min_rows": 10,
            "subtitle_llm_macro_chunk_max_rows": 15,
            "subtitle_llm_macro_chunk_use_cut_boundaries": True,
            "split_length_threshold": 10,
            "sub_max_duration": 6.0,
            "llm_confidence_gate_enabled": True,
            "llm_confidence_gate_min_lora_score": 82.0,
            "llm_candidate_policy_enabled": False,
            "editor_lora_runtime_enabled": False,
            "subtitle_quality_auto_correct_enabled": False,
            "deep_subtitle_policy_enabled": False,
            "deep_policy_event_logging_enabled": False,
            "runtime_quality_self_review_enabled": False,
            "subtitle_output_selector_enabled": False,
            "subtitle_context_consistency_enabled": False,
            "subtitle_auto_review_enabled": False,
            "accuracy_decision_graph_enabled": False,
        }

        with (
            unittest.mock.patch("core.engine.subtitle_engine.get_selected_llm", return_value="exaone3.5:7.8b"),
            unittest.mock.patch("core.engine.subtitle_engine._get_user_settings", return_value=settings),
            unittest.mock.patch("core.engine.subtitle_engine._resolve_runtime_llm_model", side_effect=lambda model, **_: model),
            unittest.mock.patch("core.engine.subtitle_engine._local_ollama_ready", return_value=True),
            unittest.mock.patch("core.engine.subtitle_engine.warmup_ollama_model"),
            unittest.mock.patch(
                "core.engine.subtitle_engine.ollama_split_text",
                return_value=[str(row["text"]) for row in segments],
            ) as split_text,
        ):
            result = subtitle_engine.optimize_segments(segments)

        self.assertEqual(split_text.call_count, 1)
        self.assertEqual(len(result), 12)
        self.assertTrue(any(row.get("_llm_macro_chunk_policy", {}).get("llm_called") for row in result))

    def test_lora_deep_prepass_uses_runtime_worker_plan_and_preserves_order(self):
        segments = [
            {"start": float(index), "end": float(index) + 0.8, "text": f"문장 {index}"}
            for index in range(6)
        ]

        def fake_process(arg):
            seg = arg[0]
            return [{**seg, "text": f"{seg['text']}!"}]

        with (
            unittest.mock.patch(
                "core.engine.subtitle_engine.runtime_parallel_worker_plan",
                return_value=(3, {"reason": "apple_m"}),
            ) as worker_plan,
            unittest.mock.patch("core.engine.subtitle_engine._process_one", side_effect=fake_process),
        ):
            result = subtitle_engine._preprocess_lora_deep_without_llm(
                segments,
                rules={},
                threshold=10,
                corrections={},
                user_prompt="",
                settings={"io_workers": 3},
            )

        worker_plan.assert_called_once()
        self.assertEqual(worker_plan.call_args.kwargs["task"], "subtitle_prepass")
        self.assertEqual([row["text"] for row in result], [f"문장 {index}!" for index in range(6)])

    def test_codex_native_fast_path_skips_bulk_cli_for_normal_segments(self):
        from core.llm.codex_provider import DEFAULT_CODEX_LABEL

        segments = [
            {
                "start": float(index * 2),
                "end": float(index * 2 + 1.2),
                "text": "테스트 문장",
                "words": [
                    {"word": "테스트", "start": float(index * 2), "end": float(index * 2 + 0.5)},
                    {"word": "문장", "start": float(index * 2 + 0.55), "end": float(index * 2 + 1.0)},
                ],
            }
            for index in range(6)
        ]
        settings = {
            "subtitle_llm_macro_chunk_enabled": False,
            "codex_subtitle_native_fast_path_enabled": True,
            "codex_subtitle_native_fast_path_min_segments": 3,
            "split_length_threshold": 10,
            "sub_max_duration": 6.0,
            "llm_candidate_policy_enabled": False,
            "editor_lora_runtime_enabled": False,
            "subtitle_quality_auto_correct_enabled": False,
            "deep_subtitle_policy_enabled": False,
            "deep_policy_event_logging_enabled": False,
            "runtime_quality_self_review_enabled": False,
            "subtitle_output_selector_enabled": False,
            "subtitle_context_consistency_enabled": False,
            "subtitle_auto_review_enabled": False,
            "accuracy_decision_graph_enabled": False,
        }

        with (
            unittest.mock.patch("core.engine.subtitle_engine.get_selected_llm", return_value=DEFAULT_CODEX_LABEL),
            unittest.mock.patch("core.engine.subtitle_engine._get_user_settings", return_value=settings),
            unittest.mock.patch("core.engine.subtitle_engine._resolve_runtime_llm_model", side_effect=lambda model, **_: model),
            unittest.mock.patch("core.engine.subtitle_engine.ask_openai_to_split") as ask_openai,
        ):
            result = subtitle_engine.optimize_segments(segments)

        ask_openai.assert_not_called()
        self.assertEqual(len(result), 6)
        self.assertTrue(
            all(
                row.get("_codex_native_fast_path_policy", {}).get("reason") == "bulk_native_rules"
                for row in result
            )
        )

    def test_macro_chunk_respects_confirmed_cut_boundaries_after_min_rows(self):
        rows = [
            {"start": float(index), "end": float(index) + 0.8, "text": f"문장 {index}"}
            for index in range(12)
        ]
        rows[10]["nearest_confirmed_cut_sec"] = rows[10]["start"]
        groups = subtitle_engine._build_llm_macro_groups(
            rows,
            [True] * len(rows),
            {
                "subtitle_llm_macro_chunk_min_rows": 10,
                "subtitle_llm_macro_chunk_max_rows": 15,
                "subtitle_llm_macro_chunk_use_cut_boundaries": True,
                "subtitle_bundle_boundary_snap_window_sec": 0.3,
            },
        )

        self.assertEqual([len(group["rows"]) for group in groups], [10, 2])

    def test_native_cpp_macro_group_ranges_match_python_chunking(self):
        from core.native_cut_boundary import llm_macro_group_ranges

        native_ranges = llm_macro_group_ranges(
            [0, 0, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 0, 1, 0],
            min_rows=3,
            max_rows=5,
        )
        if native_ranges is None:
            self.skipTest("native C++ extension unavailable")

        rows = [
            {"start": float(index), "end": float(index) + 0.7, "text": f"문장 {index}"}
            for index in range(7)
        ]
        rows[4]["nearest_confirmed_cut_sec"] = rows[4]["start"]
        groups = subtitle_engine._build_llm_macro_groups(
            rows,
            [False, True, False, False, False, True, False],
            {
                "subtitle_llm_macro_chunk_min_rows": 3,
                "subtitle_llm_macro_chunk_max_rows": 5,
                "subtitle_llm_macro_chunk_use_cut_boundaries": True,
                "subtitle_bundle_boundary_snap_window_sec": 0.3,
                "native_cpp_llm_macro_groups_enabled": True,
            },
        )

        self.assertEqual(native_ranges, [(0, 4, True, 1), (4, 7, True, 1)])
        self.assertEqual([group["start_index"] for group in groups], [0, 4])
        self.assertEqual([len(group["rows"]) for group in groups], [4, 3])
        self.assertTrue(all(group.get("_native_group_policy", {}).get("backend") == "cpp" for group in groups))

    def test_self_review_quality_attaches_runtime_quality_metadata(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.4,
                "text": "좋은 자막",
                "words": [{"word": "좋은", "start": 0.0, "end": 0.5, "confidence": 0.9}],
                "asr_metadata": {"avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.0},
            }
        ]

        result = subtitle_engine._self_review_subtitle_quality(
            segments,
            [],
            {"runtime_quality_self_review_enabled": True, "sub_max_cps": 12, "sub_min_duration": 0.2, "sub_max_duration": 6.0},
        )

        self.assertEqual(len(result), 1)
        self.assertIn("quality", result[0])
        self.assertIn(result[0]["quality"]["confidence_label"], {"green", "yellow", "red", "gray"})

    def test_output_variant_selector_can_restore_safer_source_variant(self):
        optimized = [
            {
                "start": 0.0,
                "end": 0.5,
                "text": "너무긴자막입니다",
                "quality": {"confidence_score": 45.0, "confidence_label": "red"},
            }
        ]
        source = [
            {
                "start": 0.0,
                "end": 1.8,
                "text": "안전한 원본 자막",
                "quality": {"confidence_score": 94.0, "confidence_label": "green"},
            }
        ]

        with unittest.mock.patch("core.engine.subtitle_engine._self_review_subtitle_quality", side_effect=lambda rows, *_args, **_kwargs: rows):
            result = subtitle_engine._apply_output_variant_selector(
                optimized,
                source,
                [],
                {
                    "subtitle_output_selector_enabled": True,
                    "sub_max_cps": 12,
                    "sub_max_duration": 6.0,
                    "sub_min_duration": 0.2,
                    "continuous_threshold": 2.0,
                    "gap_push_rate": 0.7,
                    "gap_pull_rate": 0.2,
                    "single_subtitle_end": 0.2,
                },
                stage="unit",
            )

        self.assertEqual(result[0]["text"], "안전한 원본 자막")
        self.assertEqual(result[0]["_output_selector_policy"]["selected_index"], 1)
        self.assertEqual(
            result[0]["_accuracy_decision_graph"]["decisions"][-1]["task"],
            "output_variant_selector",
        )

    def test_api_models_use_single_worker(self):
        workers, mode = subtitle_engine._effective_llm_workers(
            "OpenAI GPT-5.2",
            configured_workers=6,
            settings={"local_ollama_llm_max_workers": 2},
            segment_count=226,
        )

        self.assertEqual(mode, "api")
        self.assertEqual(workers, 1)

    def test_module_import_survives_invalid_numeric_settings(self):
        original_dataset_dir = config.DATASET_DIR
        original_module = sys.modules.get("core.engine.subtitle_engine")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "user_settings.json").write_text(
                json.dumps(
                    {
                        "llm_threads": "bad",
                        "sub_gap_break_sec": "bad",
                        "sub_max_cps": "",
                    }
                ),
                encoding="utf-8",
            )
            try:
                config.DATASET_DIR = tmp
                sys.modules.pop("core.engine.subtitle_engine", None)
                reloaded = importlib.import_module("core.engine.subtitle_engine")
                self.assertEqual(reloaded._EXAONE_WORKERS, 6)
                self.assertEqual(reloaded._GAP_BREAK_SEC, 1.5)
                self.assertEqual(reloaded._MAX_CPS, 12)
            finally:
                config.DATASET_DIR = original_dataset_dir
                sys.modules.pop("core.engine.subtitle_engine", None)
                if original_module is not None:
                    sys.modules["core.engine.subtitle_engine"] = original_module
        self.assertEqual(
            subtitle_engine._setting_float(
                {"sub_gap_break_sec": "bad"},
                "sub_gap_break_sec",
                1.5,
            ),
            1.5,
        )


if __name__ == "__main__":
    unittest.main()
