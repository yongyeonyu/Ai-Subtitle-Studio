import json
import tempfile
import unittest
from unittest.mock import patch

import core.personalization.lora_vector_retriever as lora_vector_retriever
from core.personalization.lora_models import TrialRecord, TruthTableRow
from core.personalization.lora_storage import (
    append_excluded_parentheticals,
    append_multimodal_lora_context_rows,
    append_prompt_trials,
    append_setting_trials,
    append_truth_table_rows,
    initialize_lora_personalization_store,
    save_best_settings,
    store_paths,
)
from core.personalization.lora_vector_retriever import (
    LORA_RETRIEVAL_SCORE_MODEL,
    build_lora_retrieval_index,
    lora_retrieval_index_summary,
    retrieve_lora_context,
    runtime_settings_from_retrieved_items,
)
from core.personalization.runtime_lora_context import build_runtime_lora_prompt
from core.personalization.runtime_personalization import personalization_settings_override_for_media
from core.personalization.subtitle_lora_runtime import lora_settings_for_subtitle_segment, merge_segment_lora_settings


class LoraVectorRetrieverTests(unittest.TestCase):
    def _seed_vehicle_store(self, tmpdir: str):
        initialize_lora_personalization_store(tmpdir)
        paths = store_paths(tmpdir)
        append_truth_table_rows(
            [
                TruthTableRow(
                    media_id="bmw-x5",
                    media_path="/training/BMW X5 vehicle review.mp4",
                    subtitle_path="/training/BMW X5 vehicle review.srt",
                    segment_id="seg-1",
                    start_sec=1.0,
                    end_sec=4.0,
                    raw_ground_truth_text="BMW X5 고속도로 주행 소음을 확인합니다.",
                    speech_training_text="BMW X5 고속도로 주행 소음을 확인합니다.",
                    detected_split_rule="합니다",
                ).to_record()
            ],
            tmpdir,
        )
        paths["text_lora_corpus"].write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "schema": "ai_subtitle_studio.text_lora_corpus.v1",
                            "task": "text_correction",
                            "source": "ground_truth",
                            "input": "bmw x5 고속도로 노면 소음",
                            "output": "BMW X5 고속도로 노면 소음",
                            "media_path": "/training/BMW X5 vehicle review.mp4",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "schema": "ai_subtitle_studio.text_lora_corpus.v1",
                            "task": "text_correction",
                            "source": "ground_truth",
                            "input": "제주도 여행 바다 풍경",
                            "output": "제주도 여행 바다 풍경",
                            "media_path": "/training/Jeju travel vlog.mp4",
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        append_multimodal_lora_context_rows(
            [
                {
                    "schema": "ai_subtitle_studio.multimodal_lora_context.v1",
                    "task": "subtitle_generation_context",
                    "source": "unit_test",
                    "media_id": "bmw-x5",
                    "media_path": "/training/BMW X5 vehicle review.mp4",
                    "context_classification": {
                        "scene_environment": {"label": "car"},
                        "topic": {"primary": "vehicle_review"},
                        "microphone_environment": {
                            "mic_type": "builtin_or_far",
                            "noise_level": "high",
                            "noise_sources": ["engine", "traffic"],
                        },
                        "training_focus": ["handle_low_rumble", "protect_brand_model_names"],
                    },
                    "subtitle_profile": {
                        "reading_speed": {"avg_cps": 12.5, "max_cps": 16.8},
                        "excluded_parenthetical_ratio": 0.2,
                    },
                    "generation_targets": {"do_not_learn_as_spoken_text": ["()", "[]", "{}"]},
                }
            ],
            tmpdir,
        )
        append_setting_trials(
            [
                TrialRecord(
                    trial_type="setting",
                    media_id="bmw-x5",
                    media_path="/training/BMW X5 vehicle review.mp4",
                    subtitle_path="/training/BMW X5 vehicle review.srt",
                    config={
                        "selected_audio_ai": "clearvoice",
                        "stt_quality_preset": "precise",
                        "subtitle_quality_enabled": True,
                        "continuous_threshold": 2.4,
                        "gap_push_rate": 0.82,
                        "single_subtitle_end": 0.3,
                        "sub_min_duration": 0.25,
                        "sub_max_duration": 5.5,
                        "sub_max_cps": 17,
                        "sub_dedup_window": 0.7,
                        "sub_gap_break_sec": 1.1,
                    },
                    status="complete",
                    score=96.0,
                    metrics={"final_score": 96.0, "scene_environment": "car", "topic": "vehicle_review"},
                    reason="car vehicle_review engine traffic high noise",
                ).to_record()
            ],
            tmpdir,
        )
        append_prompt_trials(
            [
                TrialRecord(
                    trial_type="prompt",
                    media_id="bmw-x5",
                    media_path="/training/BMW X5 vehicle review.mp4",
                    subtitle_path="/training/BMW X5 vehicle review.srt",
                    config={"provider": "inherit", "model": "inherit"},
                    prompt_template_id="vehicle_review_ground_truth_style",
                    prompt_text="BMW X5 차량 리뷰에서는 브랜드명과 모델명을 원문 그대로 보호하고 짧게 줄바꿈합니다.",
                    status="complete",
                    score=94.0,
                    reason="BMW X5 vehicle review prompt style",
                ).to_record()
            ],
            tmpdir,
        )
        append_excluded_parentheticals(
            [
                {
                    "media_id": "bmw-x5",
                    "media_path": "/training/BMW X5 vehicle review.mp4",
                    "subtitle_path": "/training/BMW X5 vehicle review.srt",
                    "excluded_text": "자막 설명",
                    "kept_text": "BMW X5 고속도로 주행 소음",
                    "reason_code": "editorial_parenthetical",
                    "score": 96.0,
                }
            ],
            tmpdir,
        )
        paths["audio_preset_lora"].write_text(
            json.dumps(
                {
                    "schema": "ai_subtitle_studio.audio_preset_lora.v1",
                    "media_id": "bmw-x5",
                    "media_path": "/training/BMW X5 vehicle review.mp4",
                    "audio_strategy_label": "BMW X5 engine road noise clearvoice",
                    "confidence": 0.98,
                    "reason": "BMW X5 vehicle review engine traffic audio preset",
                    "audio_tune_settings": {"selected_audio_ai": "clearvoice", "ff_hp": 180},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return paths

    def test_vector_index_ranks_relevant_vehicle_rows_over_unrelated_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)

            index = build_lora_retrieval_index(tmpdir)
            result = retrieve_lora_context("BMW X5 고속도로 주행 소음 리뷰", store_dir=tmpdir, limit=6)

            self.assertGreaterEqual(index["doc_count"], 4)
            self.assertEqual(index["score_model"], LORA_RETRIEVAL_SCORE_MODEL)
            self.assertGreater(index["bm25"]["term_count"], 0)
            self.assertTrue(result["items"])
            self.assertIn("bm25", result["items"][0]["score_breakdown"])
            joined = json.dumps(result["items"][:3], ensure_ascii=False)
            self.assertIn("BMW X5", joined)
            self.assertNotIn("제주도", joined)

    def test_runtime_prompt_uses_scored_lora_retrieval_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            prompt = build_runtime_lora_prompt(
                "bmw x5 고속도로 노면 소음 확인",
                {},
                {"editor_lora_runtime_enabled": True},
                store_dir=tmpdir,
            )

            self.assertIn("LoRA 검색 인덱스", prompt)
            self.assertIn("BMW X5", prompt)
            self.assertIn("scene=car", prompt)
            self.assertIn("괄호(), 대괄호[], 중괄호{}", prompt)

    def test_fast_quality_disables_runtime_lora_prompt_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            prompt = build_runtime_lora_prompt(
                "bmw x5 고속도로 노면 소음 확인",
                {},
                {"editor_lora_runtime_enabled": True, "stt_quality_preset": "fast"},
                store_dir=tmpdir,
            )

            self.assertEqual(prompt, "")

    def test_retrieved_settings_apply_to_similar_media_without_exact_path_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            with patch(
                "core.personalization.runtime_personalization.load_settings",
                return_value={"stt_quality_preset": "precise"},
            ):
                override = personalization_settings_override_for_media(
                    "/new_jobs/BMW X5 vehicle review final cut.mp4",
                    store_dir=tmpdir,
                )
            direct = retrieve_lora_context(
                "BMW X5 vehicle review final cut",
                media_path="/new_jobs/BMW X5 vehicle review final cut.mp4",
                store_dir=tmpdir,
                kinds=("setting_trials", "multimodal_lora_context"),
            )
            retrieval_override = runtime_settings_from_retrieved_items(direct["items"])

            self.assertEqual(override["selected_audio_ai"], "clearvoice")
            self.assertEqual(override["stt_quality_preset"], "precise")
            self.assertEqual(override["gap_push_rate"], 0.82)
            self.assertEqual(override["sub_max_duration"], 5.5)
            self.assertEqual(override["sub_gap_break_sec"], 1.1)
            self.assertEqual(retrieval_override["sub_max_cps"], 17)

    def test_context_facets_and_cache_make_retrieval_fast_and_specific(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            first = retrieve_lora_context(
                "고속도로 주행 중 노면 소음과 엔진음이 큰 차량 리뷰",
                media_path="/jobs/BMW X5 highway review.mp4",
                context={
                    "context_classification": {
                        "scene_environment": {"label": "car"},
                        "topic": {"primary": "vehicle_review"},
                        "microphone_environment": {
                            "mic_type": "builtin_or_far",
                            "noise_level": "high",
                            "noise_sources": ["engine", "traffic"],
                        },
                        "training_focus": ["protect_brand_model_names", "handle_low_rumble"],
                    }
                },
                store_dir=tmpdir,
                limit=4,
            )
            second = retrieve_lora_context(
                "고속도로 주행 중 노면 소음과 엔진음이 큰 차량 리뷰",
                media_path="/jobs/BMW X5 highway review.mp4",
                context={
                    "context_classification": {
                        "scene_environment": {"label": "car"},
                        "topic": {"primary": "vehicle_review"},
                        "microphone_environment": {
                            "mic_type": "builtin_or_far",
                            "noise_level": "high",
                            "noise_sources": ["engine", "traffic"],
                        },
                        "training_focus": ["protect_brand_model_names", "handle_low_rumble"],
                    }
                },
                store_dir=tmpdir,
                limit=4,
            )
            summary = lora_retrieval_index_summary(tmpdir)

            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["items"][0]["kind"], second["items"][0]["kind"])
            self.assertIn("facet", first["items"][0]["score_breakdown"])
            self.assertGreaterEqual(summary["query_cache_entries"], 1)

    def test_query_cache_lru_stays_bounded(self):
        original_max = lora_vector_retriever.LORA_QUERY_CACHE_MAX
        try:
            lora_vector_retriever.LORA_QUERY_CACHE_MAX = 2
            with tempfile.TemporaryDirectory() as tmpdir:
                self._seed_vehicle_store(tmpdir)
                build_lora_retrieval_index(tmpdir)
                retrieve_lora_context("BMW X5", store_dir=tmpdir, limit=4)
                retrieve_lora_context("Jeju", store_dir=tmpdir, limit=4)
                retrieve_lora_context("engine traffic", store_dir=tmpdir, limit=4)
                self.assertLessEqual(len(lora_vector_retriever._PROCESS_QUERY_CACHE), 2)
        finally:
            lora_vector_retriever.LORA_QUERY_CACHE_MAX = original_max

    def test_balanced_quality_retrieval_uses_only_high_lora_bucket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_setting_trials(
                [
                    TrialRecord(
                        trial_type="setting",
                        media_id=f"bucket-filter-{label}",
                        media_path=f"/training/bucket-filter-{label}.mp4",
                        subtitle_path=f"/training/bucket-filter-{label}.srt",
                        config={"candidate": label, "sub_max_cps": cps},
                        status="complete",
                        score=score,
                        reason="bucket filter conflict subtitle quality",
                    ).to_record()
                    for label, score, cps in (("high", 96.0, 17), ("medium", 70.0, 14), ("pending", 15.0, 10))
                ],
                tmpdir,
            )
            build_lora_retrieval_index(tmpdir)

            balanced = retrieve_lora_context(
                "bucket filter conflict subtitle quality",
                settings={"stt_quality_preset": "balanced"},
                store_dir=tmpdir,
                kinds=("setting_trials",),
                limit=8,
            )
            precise = retrieve_lora_context(
                "bucket filter conflict subtitle quality",
                settings={"stt_quality_preset": "precise"},
                store_dir=tmpdir,
                kinds=("setting_trials",),
                limit=8,
            )

            self.assertEqual(balanced["quality_buckets"], ["high"])
            self.assertTrue(balanced["items"])
            self.assertTrue(all(item.get("quality_bucket") == "high" for item in balanced["items"]))
            self.assertIn("medium", {str((item["payload"]["config"]).get("candidate")) for item in precise["items"]})
            self.assertNotIn("pending", {str((item["payload"]["config"]).get("candidate")) for item in precise["items"]})

    def test_runtime_setting_conflicts_prefer_score_index_over_retrieval_order(self):
        override = runtime_settings_from_retrieved_items(
            [
                {
                    "kind": "setting_trials",
                    "retrieval_score": 90.0,
                    "score_index": 40.0,
                    "payload": {"config": {"sub_max_cps": 12}},
                },
                {
                    "kind": "setting_trials",
                    "retrieval_score": 31.0,
                    "score_index": 95.0,
                    "payload": {"config": {"sub_max_cps": 17}},
                },
            ],
            min_score=28.0,
        )

        self.assertEqual(override["sub_max_cps"], 17)

    def test_subtitle_segment_lora_returns_per_subtitle_gap_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            override = lora_settings_for_subtitle_segment(
                {
                    "text": "BMW X5 고속도로 주행 소음 확인",
                    "start": 10.0,
                    "end": 13.0,
                },
                {"editor_lora_runtime_enabled": True, "stt_quality_preset": "precise"},
                store_dir=tmpdir,
            )

            self.assertEqual(override["gap_push_rate"], 0.82)
            self.assertEqual(override["sub_gap_break_sec"], 1.1)
            self.assertEqual(override["sub_max_duration"], 5.5)
            self.assertIn("_lora_segment_score", override)
            self.assertIn("_lora_generation_profile", override)
            profile = override["_lora_generation_profile"]
            self.assertIn("retrieved_settings", profile)
            self.assertIn("excluded_parentheticals", profile["used_kinds"])
            self.assertIn("prompt_trials", profile["used_kinds"])
            self.assertIn("audio_preset_lora", profile["used_kinds"])
            self.assertTrue(profile["exclusions"])
            self.assertTrue(profile["prompt_hints"])
            self.assertTrue(profile["setting_sources"])

    def test_subtitle_segment_lora_query_uses_full_context(self):
        segment = {
            "text": "주행 소음 확인",
            "start": 10.0,
            "end": 12.0,
            "speaker": "SPEAKER_01",
            "stt_ensemble_context_prev": "이전에는 외부 디자인을 봤습니다",
            "stt_ensemble_context_next": "다음은 고속도로 진입입니다",
            "stt_candidates": [{"source": "STT1", "text": "주행 소음 확인"}],
            "vad_candidates": [{"source": "VAD", "text": "주행 소음 체크"}],
            "stt_recheck_candidates": [{"source": "STT2_RECHECK", "text": "주행 노면 소음 확인"}],
            "audio_profile": {"environment": "car", "noise_level": "high", "mic_type": "builtin"},
            "_cut_boundary_guard_policy": {"action": "clamped_to_cut_scene", "scene_start": 9.5, "scene_end": 12.5},
            "roughcut_topic": "vehicle_review",
            "video_diagnostic_tags": ["outdoor", "wind_noise"],
        }
        fake_result = {
            "index_doc_count": 1,
            "quality_buckets": ["high"],
            "items": [
                {
                    "kind": "truth_table",
                    "retrieval_score": 88.0,
                    "payload": {
                        "speech_training_text": "주행 소음 확인",
                        "duration_sec": 2.0,
                        "cps": 5.0,
                    },
                }
            ],
        }

        with patch("core.personalization.subtitle_lora_runtime.retrieve_lora_context", return_value=fake_result) as retrieve:
            override = lora_settings_for_subtitle_segment(
                segment,
                {
                    "editor_lora_runtime_enabled": True,
                    "stt_quality_preset": "precise",
                    "lora_pattern_index_enabled": False,
                    "lora_pattern_query_compact_enabled": False,
                },
            )

        query = retrieve.call_args.args[0]
        context = retrieve.call_args.kwargs["context"]
        self.assertIn("이전에는 외부 디자인", query)
        self.assertIn("STT2_RECHECK/low_score_recheck", query)
        self.assertIn("noise_level=high", query)
        self.assertIn("vehicle_review", query)
        self.assertEqual(context["subtitle_segment"]["speaker"], "SPEAKER_01")
        self.assertIn("주행 노면 소음 확인", " ".join(context["stt_candidate_lattice"]["candidates"]))
        self.assertIn("action=clamped_to_cut_scene", context["cut_boundary"])
        self.assertIn("_lora_generation_profile", override)

    def test_subtitle_lora_generation_profile_feeds_runtime_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)
            build_lora_retrieval_index(tmpdir)

            runtime, override = merge_segment_lora_settings(
                {
                    "text": "BMW X5 고속도로 주행 소음 확인",
                    "start": 10.0,
                    "end": 13.0,
                },
                {"editor_lora_runtime_enabled": True, "stt_quality_preset": "precise"},
                store_dir=tmpdir,
            )
            prompt = build_runtime_lora_prompt(
                "BMW X5 고속도로 주행 소음 확인",
                {},
                runtime,
                store_dir=tmpdir,
            )

            self.assertIn("_lora_generation_profile", runtime)
            self.assertIn("자막별 LoRA 프로필", prompt)
            self.assertIn("이번 자막에 직접 적용할 LoRA 값", prompt)
            self.assertIn("자막별 프롬프트 trial 근거", prompt)
            self.assertIn("자막별 제외 문구", prompt)
            self.assertIn("ground truth", prompt)
            self.assertIn("_lora_generation_profile", override)

    def test_runtime_prompt_can_reuse_segment_profile_without_extra_retrieval(self):
        runtime = {
            "editor_lora_runtime_enabled": True,
            "stt_quality_preset": "precise",
            "_lora_generation_profile": {
                "top_score": 91.0,
                "index_doc_count": 12,
                "used_kinds": {"truth_table": 1},
                "applied_settings": {"split_length_threshold": 16},
                "examples": [{"text": "BMW X5 고속도로 주행 소음", "score": 91.0}],
            },
        }

        with patch("core.personalization.runtime_lora_context.retrieve_lora_context") as retrieve:
            prompt = build_runtime_lora_prompt(
                "BMW X5 고속도로 주행 소음",
                {},
                runtime,
                include_retrieval=False,
            )

        retrieve.assert_not_called()
        self.assertIn("자막별 LoRA 프로필", prompt)
        self.assertIn("이번 자막에 직접 적용할 LoRA 값", prompt)

    def test_exact_media_lora_override_still_prefers_higher_score_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_best_settings(
                {
                    "by_media_id": {
                        "score-conflict": {
                            "config": {"sub_max_cps": 11},
                            "score": 55.0,
                        }
                    }
                },
                tmpdir,
            )
            append_setting_trials(
                [
                    TrialRecord(
                        trial_type="setting",
                        media_id="score-conflict",
                        media_path="/training/score conflict.mp4",
                        subtitle_path="/training/score conflict.srt",
                        config={"sub_max_cps": 17},
                        status="complete",
                        score=97.0,
                        reason="score conflict exact media",
                    ).to_record()
                ],
                tmpdir,
            )
            build_lora_retrieval_index(tmpdir)

            with patch(
                "core.personalization.runtime_personalization.load_settings",
                return_value={"stt_quality_preset": "precise"},
            ):
                override = personalization_settings_override_for_media(
                    "/training/score conflict.mp4",
                    media_id="score-conflict",
                    store_dir=tmpdir,
                )

            self.assertEqual(override["sub_max_cps"], 17)


if __name__ == "__main__":
    unittest.main()
