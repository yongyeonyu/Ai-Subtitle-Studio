import unittest

from core.native_swift_policy import (
    build_llm_candidate_options_batch_via_swift,
    build_llm_candidate_options_via_swift,
    rerank_subtitle_candidates_batch_via_swift,
    rerank_subtitle_candidates_via_swift,
    score_lora_docs_via_swift,
)
from core.native_swift_subtitle import find_native_cli_path
from core.personalization.lora_retrieval_utils import term_counts, vectorize_lora_text
from tools.benchmark_native_policy_engine import _adoption_label


def _tiny_lora_index() -> dict:
    docs = [
        {
            "doc_id": "bmw",
            "kind": "truth_table",
            "quality": 0.95,
            "quality_bucket": "green",
            "text_preview": "BMW X5 고속도로 주행 소음 리뷰 브랜드 모델명 보호",
            "media_id": "bmw-x5",
            "media_path": "/training/vehicle_review/clip_0.mp4",
            "media_lookup_keys": ["vehicle_review", "clip_0"],
            "facets": {"scene": "car", "topic": "vehicle_review"},
            "created_at": "2026-05-09T00:00:00",
        },
        {
            "doc_id": "kids",
            "kind": "text_lora_corpus",
            "quality": 0.8,
            "quality_bucket": "green",
            "text_preview": "티니핑 뉴스 어드벤처 전시 관람 소감",
            "media_id": "",
            "media_path": "/training/kids/clip_1.mp4",
            "media_lookup_keys": ["kids", "clip_1"],
            "facets": {"scene": "exhibition", "topic": "kids"},
            "created_at": "2026-04-01T00:00:00",
        },
    ]
    inverted: dict[str, list[list[float]]] = {}
    postings: dict[str, list[list[float]]] = {}
    doc_lengths: list[int] = []
    for index, doc in enumerate(docs):
        vector = vectorize_lora_text(str(doc["text_preview"]))
        for bucket, weight in vector.items():
            inverted.setdefault(str(bucket), []).append([index, float(weight)])
        terms = term_counts(str(doc["text_preview"]))
        doc_lengths.append(sum(terms.values()))
        for term, count in terms.items():
            postings.setdefault(str(term), []).append([index, float(count)])
    return {
        "source_signature": "tiny",
        "updated_at": "2026-05-09T00:00:00",
        "doc_count": len(docs),
        "docs": docs,
        "inverted_index": inverted,
        "bm25": {
            "term_postings": postings,
            "idf": {key: 1.0 for key in postings},
            "doc_lengths": doc_lengths,
            "avg_doc_len": sum(doc_lengths) / len(doc_lengths),
        },
    }


class NativePolicyBenchmarkReportTests(unittest.TestCase):
    def test_adoption_label_blocks_native_when_parity_fails(self):
        self.assertEqual(
            _adoption_label(50.0, parity=False, threshold=1.0, fallback="python"),
            "blocked_quality_mismatch",
        )
        self.assertEqual(
            _adoption_label(1.2, parity=True, threshold=1.0, fallback="python"),
            "native",
        )


@unittest.skipUnless(find_native_cli_path(), "AIStudioNativeCLI release binary not available")
class NativePolicyEngineTests(unittest.TestCase):
    def test_swift_llm_candidate_policy_matches_basic_shape(self):
        candidates = build_llm_candidate_options_via_swift(
            "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다",
            8,
            {"end_words": ["습니다"]},
            {
                "llm_candidate_policy_enabled": True,
                "llm_candidate_policy_max_candidates": 4,
                "native_swift_policy_experimental_enabled": True,
                "native_swift_llm_candidate_policy_enabled": True,
            },
        )

        self.assertIsNotNone(candidates)
        self.assertEqual(candidates[0]["strategy"], "source")
        self.assertTrue(any(item["chunk_count"] > 1 for item in candidates))

    def test_swift_deep_reranker_keeps_safe_candidate(self):
        result = rerank_subtitle_candidates_via_swift(
            "오늘은 여기까지 정리할게요",
            [["오늘은 자막 생성 중 여기까지 정리할게요"], ["오늘은 여기까지 정리할게요"]],
            {
                "deep_subtitle_policy_enabled": True,
                "deep_subtitle_reranker_min_margin": 0.0,
                "native_swift_policy_experimental_enabled": True,
                "native_swift_deep_policy_enabled": True,
            },
            {
                "top_score": 90.0,
                "examples": [{"text": "오늘은 여기까지 정리할게요"}],
                "exclusions": [{"text": "자막 생성 중"}],
            },
        )

        self.assertIsNotNone(result)
        chunks, metadata = result
        self.assertEqual(chunks, ["오늘은 여기까지 정리할게요"])
        self.assertEqual(metadata["task"], "subtitle_rerank")
        self.assertIn(":swift", metadata["model"])

    def test_swift_policy_batch_apis_preserve_item_count(self):
        settings = {
            "llm_candidate_policy_enabled": True,
            "llm_candidate_policy_max_candidates": 4,
            "deep_subtitle_policy_enabled": True,
            "native_swift_policy_experimental_enabled": True,
            "native_swift_llm_candidate_policy_enabled": True,
            "native_swift_deep_policy_enabled": True,
        }
        candidate_rows = build_llm_candidate_options_batch_via_swift(
            [
                {
                    "id": "a",
                    "text": "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다",
                    "threshold": 8,
                    "rules": {"end_words": ["습니다"]},
                    "settings": settings,
                },
                {
                    "id": "b",
                    "text": "맥북 네이티브 최적화를 진행합니다",
                    "threshold": 8,
                    "rules": {"end_words": ["합니다"]},
                    "settings": settings,
                },
            ],
            settings=settings,
        )
        self.assertIsNotNone(candidate_rows)
        self.assertEqual(len(candidate_rows), 2)
        self.assertEqual(candidate_rows[0][0]["strategy"], "source")

        reranked = rerank_subtitle_candidates_batch_via_swift(
            [
                {
                    "id": "a",
                    "original_text": "오늘은 여기까지 정리할게요",
                    "candidate_lists": [["오늘은 자막 생성 중 여기까지 정리할게요"], ["오늘은 여기까지 정리할게요"]],
                    "settings": settings,
                    "profile": {
                        "top_score": 90.0,
                        "examples": [{"text": "오늘은 여기까지 정리할게요"}],
                        "exclusions": [{"text": "자막 생성 중"}],
                    },
                }
            ],
            settings=settings,
        )
        self.assertIsNotNone(reranked)
        self.assertEqual(reranked[0][0], ["오늘은 여기까지 정리할게요"])

    def test_swift_lora_scoring_returns_ranked_docs(self):
        query = "BMW X5 고속도로 주행 소음 리뷰"
        ranked = score_lora_docs_via_swift(
            _tiny_lora_index(),
            query,
            media_path="/training/vehicle_review/clip_0.mp4",
            media_id="bmw-x5",
            query_facets={"scene": "car", "topic": "vehicle_review"},
            kinds={"truth_table", "text_lora_corpus"},
            quality_buckets={"green"},
            query_vector=dict(vectorize_lora_text(query)),
            query_terms=dict(term_counts(query)),
            media_lookup_keys=["vehicle_review", "clip_0"],
            settings={
                "native_swift_policy_experimental_enabled": True,
                "native_swift_lora_scoring_enabled": True,
                "native_swift_lora_scoring_min_docs": 1,
            },
        )

        self.assertIsNotNone(ranked)
        self.assertEqual(ranked[0]["doc_id"], "bmw")
        self.assertIn("score_breakdown", ranked[0])


if __name__ == "__main__":
    unittest.main()
