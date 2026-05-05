import json
import tempfile
import unittest

from core.personalization.lora_models import TrialRecord, TruthTableRow
from core.personalization.lora_storage import (
    append_multimodal_lora_context_rows,
    append_setting_trials,
    append_truth_table_rows,
    initialize_lora_personalization_store,
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

    def test_retrieved_settings_apply_to_similar_media_without_exact_path_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._seed_vehicle_store(tmpdir)

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


if __name__ == "__main__":
    unittest.main()
