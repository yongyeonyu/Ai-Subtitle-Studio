from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.engine.llm_candidate_policy import build_llm_candidate_options
from core.native_swift_policy import (
    build_llm_candidate_options_batch_via_swift,
    build_llm_candidate_options_via_swift,
    rerank_subtitle_candidates_batch_via_swift,
    rerank_subtitle_candidates_via_swift,
    score_lora_docs_via_swift,
)
from core.native_swift_subtitle import find_native_cli_path
from core.personalization.deep_subtitle_policy import rerank_subtitle_candidates
from core.personalization.lora_retrieval_scoring import score_lora_docs
from core.personalization.lora_retrieval_utils import term_counts, vectorize_lora_text


def _bench(label: str, fn: Callable[[], Any], rounds: int) -> tuple[float, Any]:
    samples: list[float] = []
    last: Any = None
    for _ in range(max(1, rounds)):
        start = time.perf_counter()
        last = fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), last


def _speedup(py_sec: float, native_sec: float) -> float:
    if native_sec <= 0:
        return 0.0
    return py_sec / native_sec


def _adoption_label(speedup: float, *, parity: bool, threshold: float, fallback: str) -> str:
    if not parity:
        return "blocked_quality_mismatch"
    return "native" if float(speedup) >= float(threshold) else fallback


def _quality_speed_adoption(
    *,
    timings: dict[str, tuple[float, float]],
    outputs: dict[str, Any],
) -> tuple[dict[str, float], dict[str, Any], dict[str, str]]:
    quality_check = {
        "llm_candidate_count_match": len(outputs.get("llm_py") or []) == len(outputs.get("llm_native") or []),
        "deep_chunks_match": (outputs.get("deep_py") or ([], {}))[0] == (outputs.get("deep_native") or ([], {}))[0],
        "llm_batch_count_match": len(outputs.get("llm_batch_py") or []) == len(outputs.get("llm_batch_native") or []),
        "deep_batch_count_match": len(outputs.get("deep_batch_py") or []) == len(outputs.get("deep_batch_native") or []),
        "lora_top5_python": [item.get("doc_id") for item in list(outputs.get("lora_py") or [])[:5]],
        "lora_top5_native": [item.get("doc_id") for item in list(outputs.get("lora_native") or [])[:5]],
    }
    speedup = {
        key: round(_speedup(pair[0], pair[1]), 3)
        for key, pair in timings.items()
    }
    adoption = {
        "llm_candidates": _adoption_label(speedup["llm"], parity=quality_check["llm_candidate_count_match"], threshold=0.9, fallback="python_small_batch_preferred"),
        "deep_rerank": _adoption_label(speedup["deep"], parity=quality_check["deep_chunks_match"], threshold=0.9, fallback="python_small_batch_preferred"),
        "llm_candidates_batch": _adoption_label(speedup["llm_batch"], parity=quality_check["llm_batch_count_match"], threshold=1.0, fallback="python_batch_preferred"),
        "deep_rerank_batch": _adoption_label(speedup["deep_batch"], parity=quality_check["deep_batch_count_match"], threshold=1.0, fallback="python_batch_preferred"),
        "lora_scoring": _adoption_label(
            speedup["lora"],
            parity=quality_check["lora_top5_python"] == quality_check["lora_top5_native"],
            threshold=1.0,
            fallback="python_for_this_index_size",
        ),
    }
    return speedup, quality_check, adoption


def _idf(doc_count: int, df: int) -> float:
    return math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))


def _synthetic_lora_index(doc_count: int) -> dict[str, Any]:
    topics = [
        ("vehicle_review", "BMW X5 고속도로 주행 소음 리뷰 브랜드 모델명 보호"),
        ("kids_exhibition", "티니핑 뉴스 어드벤처 전시 관람 소감"),
        ("travel", "제주도 바다 여행 브이로그 풍경 설명"),
        ("tech", "맥북 네이티브 Swift 최적화 STT 자막 처리"),
    ]
    docs: list[dict[str, Any]] = []
    inverted: dict[str, list[list[float]]] = defaultdict(list)
    postings: dict[str, list[list[float]]] = defaultdict(list)
    doc_lengths: list[int] = []
    now = datetime.utcnow()
    for index in range(doc_count):
        topic, base = topics[index % len(topics)]
        text = f"{base} 샘플 {index} 반복 학습 데이터 정확도 품질 보정"
        if index % 7 == 0:
            text += " ClearVoice 오디오 전처리 잡음 제거"
        quality = 0.55 + ((index % 40) / 100.0)
        kind = ["truth_table", "text_lora_corpus", "multimodal_lora_context", "setting_trials"][index % 4]
        doc = {
            "doc_id": f"doc-{index}",
            "kind": kind,
            "quality": min(0.99, quality),
            "quality_bucket": "green" if quality >= 0.72 else "yellow",
            "text_preview": text,
            "media_id": "bmw-x5" if topic == "vehicle_review" else "",
            "media_path": f"/training/{topic}/clip_{index}.mp4",
            "media_lookup_keys": [topic, f"clip_{index}"],
            "facets": {
                "scene": "car" if topic == "vehicle_review" else "exhibition",
                "topic": topic,
                "mic_type": "builtin_or_far",
                "noise_level": "high" if index % 7 == 0 else "medium",
                "noise_sources": ["engine", "traffic"] if topic == "vehicle_review" else ["crowd"],
                "training_focus": ["protect_brand_model_names", "line_break"],
                "topic_terms": topic.split("_"),
            },
            "created_at": (now - timedelta(days=index % 365)).isoformat(),
        }
        docs.append(doc)
        vector = vectorize_lora_text(text)
        for bucket, weight in vector.items():
            inverted[str(bucket)].append([index, float(weight)])
        terms = term_counts(text)
        doc_lengths.append(sum(terms.values()))
        for term_hash, tf in terms.items():
            postings[str(term_hash)].append([index, float(tf)])
    idf = {term: round(_idf(doc_count, len(rows)), 8) for term, rows in postings.items()}
    return {
        "schema": "ai_subtitle_studio.lora_retrieval_index.v1",
        "score_model": "hybrid_hash_vector_bm25_context_facet_quality_bucket_v3",
        "source_signature": f"synthetic-{doc_count}",
        "updated_at": now.isoformat(),
        "doc_count": doc_count,
        "docs": docs,
        "inverted_index": dict(inverted),
        "bm25": {
            "term_postings": dict(postings),
            "idf": idf,
            "doc_lengths": doc_lengths,
            "avg_doc_len": sum(doc_lengths) / max(1, len(doc_lengths)),
            "term_count": len(postings),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Swift-native LLM/LoRA/Deep policy helpers.")
    parser.add_argument("--docs", type=int, default=2500)
    parser.add_argument("--rounds", type=int, default=80)
    parser.add_argument("--lora-rounds", type=int, default=8)
    args = parser.parse_args()

    cli = find_native_cli_path()
    if cli is None:
        print(json.dumps({"ok": False, "error": "AIStudioNativeCLI release binary not found. Run swift build -c release."}, ensure_ascii=False))
        return 2

    text = "오늘은 티니핑 뉴스 어드벤처 전시장에서 촬영을 시작합니다"
    rules = {"end_words": ["습니다"]}
    settings = {
        "llm_candidate_policy_enabled": True,
        "llm_candidate_policy_max_candidates": 4,
        "split_length_threshold": 16,
        "deep_subtitle_policy_enabled": True,
        "deep_subtitle_reranker_enabled": True,
        "deep_subtitle_reranker_min_margin": 0.0,
        "native_swift_llm_candidate_policy_enabled": False,
        "native_swift_deep_policy_enabled": False,
    }
    native_settings = {**settings, "native_swift_llm_candidate_policy_enabled": True, "native_swift_deep_policy_enabled": True}
    profile = {
        "top_score": 92.0,
        "examples": [{"text": "오늘은 티니핑 뉴스 어드벤처 전시장입니다"}],
        "exclusions": [{"text": "자막 생성 중"}],
    }
    candidate_lists = [
        ["오늘은 자막 생성 중 티니핑 뉴스 어드벤처 전시장입니다"],
        ["오늘은 티니핑 뉴스 어드벤처 전시장입니다"],
        ["오늘은 티니핑 뉴스", "어드벤처 전시장입니다"],
    ]
    batch_items = [
        {
            "id": f"seg-{idx}",
            "text": f"{text} {idx}",
            "threshold": 10 + (idx % 5),
            "rules": rules,
            "settings": native_settings,
        }
        for idx in range(max(1, args.rounds * 4))
    ]
    deep_batch_items = [
        {
            "id": f"deep-{idx}",
            "original_text": text,
            "candidate_lists": candidate_lists,
            "settings": native_settings,
            "profile": profile,
        }
        for idx in range(max(1, args.rounds * 4))
    ]

    # Warm native worker so the measured number reflects steady-state app usage.
    build_llm_candidate_options_via_swift(text, 10, rules, native_settings)
    rerank_subtitle_candidates_via_swift(text, candidate_lists, native_settings, profile)
    build_llm_candidate_options_batch_via_swift(batch_items[:4], settings=native_settings)
    rerank_subtitle_candidates_batch_via_swift(deep_batch_items[:4], settings=native_settings)

    llm_py, llm_py_out = _bench(
        "llm_python",
        lambda: build_llm_candidate_options(text, 10, rules, settings),
        args.rounds,
    )
    llm_native, llm_native_out = _bench(
        "llm_native",
        lambda: build_llm_candidate_options_via_swift(text, 10, rules, native_settings),
        args.rounds,
    )
    deep_py, deep_py_out = _bench(
        "deep_python",
        lambda: rerank_subtitle_candidates(text, candidate_lists, settings, profile),
        args.rounds,
    )
    deep_native, deep_native_out = _bench(
        "deep_native",
        lambda: rerank_subtitle_candidates_via_swift(text, candidate_lists, native_settings, profile),
        args.rounds,
    )
    llm_batch_py, llm_batch_py_out = _bench(
        "llm_batch_python",
        lambda: [
            build_llm_candidate_options(
                str(item["text"]),
                int(item["threshold"]),
                dict(item["rules"]),
                settings,
            )
            for item in batch_items
        ],
        3,
    )
    llm_batch_native, llm_batch_native_out = _bench(
        "llm_batch_native",
        lambda: build_llm_candidate_options_batch_via_swift(batch_items, settings=native_settings),
        3,
    )
    deep_batch_py, deep_batch_py_out = _bench(
        "deep_batch_python",
        lambda: [
            rerank_subtitle_candidates(
                str(item["original_text"]),
                list(item["candidate_lists"]),
                settings,
                profile,
            )
            for item in deep_batch_items
        ],
        3,
    )
    deep_batch_native, deep_batch_native_out = _bench(
        "deep_batch_native",
        lambda: rerank_subtitle_candidates_batch_via_swift(deep_batch_items, settings=native_settings),
        3,
    )

    lora_index = _synthetic_lora_index(max(64, args.docs))
    query = "BMW X5 고속도로 주행 소음 리뷰 브랜드 모델명 보호"
    query_vector = vectorize_lora_text(query)
    query_terms = term_counts(query)
    query_facets = {
        "scene": "car",
        "topic": "vehicle_review",
        "mic_type": "builtin_or_far",
        "noise_level": "high",
        "noise_sources": ["engine", "traffic"],
        "training_focus": ["protect_brand_model_names"],
        "topic_terms": ["vehicle", "review"],
    }
    lora_kinds = {"truth_table", "text_lora_corpus", "multimodal_lora_context", "setting_trials"}
    lora_buckets = {"green", "yellow"}
    score_lora_docs_via_swift(
        lora_index,
        query,
        media_path="/training/vehicle_review/clip_0.mp4",
        media_id="bmw-x5",
        query_facets=query_facets,
        kinds=lora_kinds,
        quality_buckets=lora_buckets,
        query_vector=dict(query_vector),
        query_terms=dict(query_terms),
        media_lookup_keys=["vehicle_review", "clip_0"],
        settings={"native_swift_lora_scoring_enabled": True, "native_swift_lora_scoring_min_docs": 1},
    )

    previous_env = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_POLICY")
    os.environ["AI_SUBTITLE_STUDIO_SWIFT_POLICY"] = "0"
    try:
        lora_py, lora_py_out = _bench(
            "lora_python",
            lambda: score_lora_docs(
                lora_index,
                query,
                media_path="/training/vehicle_review/clip_0.mp4",
                media_id="bmw-x5",
                query_facets=query_facets,
                kinds=lora_kinds,
                quality_buckets=lora_buckets,
            ),
            args.lora_rounds,
        )
    finally:
        if previous_env is None:
            os.environ.pop("AI_SUBTITLE_STUDIO_SWIFT_POLICY", None)
        else:
            os.environ["AI_SUBTITLE_STUDIO_SWIFT_POLICY"] = previous_env
    lora_native, lora_native_out = _bench(
        "lora_native",
        lambda: score_lora_docs_via_swift(
            lora_index,
            query,
            media_path="/training/vehicle_review/clip_0.mp4",
            media_id="bmw-x5",
            query_facets=query_facets,
            kinds=lora_kinds,
            quality_buckets=lora_buckets,
            query_vector=dict(query_vector),
            query_terms=dict(query_terms),
            media_lookup_keys=["vehicle_review", "clip_0"],
            settings={"native_swift_lora_scoring_enabled": True, "native_swift_lora_scoring_min_docs": 1},
        ),
        args.lora_rounds,
    )

    speedup, quality_check, adoption = _quality_speed_adoption(
        timings={
            "llm": (llm_py, llm_native), "deep": (deep_py, deep_native),
            "llm_batch": (llm_batch_py, llm_batch_native), "deep_batch": (deep_batch_py, deep_batch_native),
            "lora": (lora_py, lora_native),
        },
        outputs={
            "llm_py": llm_py_out, "llm_native": llm_native_out,
            "deep_py": deep_py_out, "deep_native": deep_native_out,
            "llm_batch_py": llm_batch_py_out, "llm_batch_native": llm_batch_native_out,
            "deep_batch_py": deep_batch_py_out, "deep_batch_native": deep_batch_native_out,
            "lora_py": lora_py_out, "lora_native": lora_native_out,
        },
    )
    report = {
        "ok": True,
        "native_cli": str(cli),
        "rounds": args.rounds,
        "lora_docs": len(lora_index["docs"]),
        "median_ms": {
            "llm_python": round(llm_py * 1000, 4),
            "llm_native_swift": round(llm_native * 1000, 4),
            "deep_python": round(deep_py * 1000, 4),
            "deep_native_swift": round(deep_native * 1000, 4),
            "llm_batch_python_total": round(llm_batch_py * 1000, 4),
            "llm_batch_native_swift_total": round(llm_batch_native * 1000, 4),
            "deep_batch_python_total": round(deep_batch_py * 1000, 4),
            "deep_batch_native_swift_total": round(deep_batch_native * 1000, 4),
            "lora_python": round(lora_py * 1000, 4),
            "lora_native_swift": round(lora_native * 1000, 4),
        },
        "speedup": speedup,
        "quality_check": quality_check,
        "adoption": adoption,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
