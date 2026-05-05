from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from core.personalization.lora_models import stable_hash
from core.personalization.lora_retrieval_config import (
    FACET_POINT_WEIGHTS,
    LIST_FACET_POINT_WEIGHTS,
    LORA_RETRIEVAL_SCORE_MODEL,
    RUNTIME_SETTING_KEYS,
    SCORE_POINT_WEIGHTS,
)
from core.personalization.lora_retrieval_utils import (
    compact_text,
    facet_label,
    facet_list,
    json_preview,
    parse_iso_seconds,
    path_leaf_terms,
    safe_float,
    safe_int,
    term_counts,
    token_overlap_score,
    vectorize_lora_text,
)
from core.personalization.lora_storage import personalization_path_lookup_keys


def _media_match_boost(doc: dict[str, Any], *, media_path: str = "", media_id: str = "") -> float:
    boost = 0.0
    if media_id and str(doc.get("media_id") or "") == str(media_id):
        boost += 18.0
    if media_path:
        query_keys = set(personalization_path_lookup_keys(media_path))
        doc_keys = set(str(item) for item in list(doc.get("media_lookup_keys") or []))
        if query_keys and doc_keys and query_keys.intersection(doc_keys):
            boost += 22.0
        query_leaf = compact_text(path_leaf_terms(media_path))
        doc_leaf = compact_text(path_leaf_terms(doc.get("media_path")))
        if query_leaf and doc_leaf and (query_leaf in doc_leaf or doc_leaf in query_leaf):
            boost += 8.0
    return boost


def _kind_boost(kind: str) -> float:
    return {
        "truth_table": 7.0,
        "text_lora_corpus": 8.0,
        "text_lora_dataset": 5.0,
        "multimodal_lora_context": 6.0,
        "setting_trials": 5.0,
        "prompt_trials": 4.0,
        "audio_preset_lora": 5.0,
        "voice_lora_bridge": 3.0,
        "excluded_parentheticals": 6.0,
        "learned_split_rules": 4.0,
        "learned_line_break_rules": 4.0,
        "best_settings": 3.0,
    }.get(kind, 1.0)


def _bm25_scores(index: dict[str, Any], query_terms: Counter[str]) -> dict[int, float]:
    bm25 = dict(index.get("bm25") or {})
    postings = dict(bm25.get("term_postings") or {})
    idf = dict(bm25.get("idf") or {})
    doc_lengths = list(bm25.get("doc_lengths") or [])
    avg_doc_len = max(1.0, safe_float(bm25.get("avg_doc_len"), 1.0))
    scores: dict[int, float] = defaultdict(float)
    k1 = 1.35
    b = 0.72
    for term_hash, query_tf in query_terms.items():
        term_idf = safe_float(idf.get(str(term_hash)), 0.0)
        if term_idf <= 0.0:
            continue
        query_weight = 1.0 + math.log(max(1.0, float(query_tf)))
        for doc_index_raw, tf_raw in list(postings.get(str(term_hash), []) or []):
            try:
                doc_index = int(doc_index_raw)
                tf = float(tf_raw)
            except Exception:
                continue
            if tf <= 0.0:
                continue
            doc_len = float(doc_lengths[doc_index]) if 0 <= doc_index < len(doc_lengths) else avg_doc_len
            denom = tf + k1 * (1.0 - b + b * doc_len / avg_doc_len)
            scores[doc_index] += term_idf * ((tf * (k1 + 1.0)) / max(0.0001, denom)) * query_weight
    return scores


def _facet_match_points(doc: dict[str, Any], query_facets: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    if not query_facets:
        return 0.0, {}
    facets = dict(doc.get("facets") or {})
    points = 0.0
    matches: dict[str, Any] = {}
    for key, weight in FACET_POINT_WEIGHTS.items():
        query_value = facet_label(query_facets.get(key))
        doc_value = facet_label(facets.get(key))
        if query_value and doc_value and query_value == doc_value:
            points += weight
            matches[key] = query_value
    for key, (weight, cap) in LIST_FACET_POINT_WEIGHTS.items():
        query_values = {item.casefold(): item for item in facet_list(query_facets.get(key) or [])}
        doc_values = {item.casefold(): item for item in facet_list(facets.get(key) or [])}
        overlap_keys = sorted(set(query_values) & set(doc_values))
        if overlap_keys:
            points += min(cap, len(overlap_keys) * weight)
            matches[key] = [query_values[item] for item in overlap_keys[:6]]
    return min(14.0, points), matches


def _recency_points(doc: dict[str, Any]) -> float:
    created_at = parse_iso_seconds(doc.get("created_at"))
    if created_at is None:
        return 0.0
    age_days = max(0.0, (datetime.utcnow() - created_at).total_seconds() / 86400.0)
    recency_cap = float(SCORE_POINT_WEIGHTS["recency_cap"])
    return round(max(0.0, min(recency_cap, recency_cap * math.exp(-age_days / 180.0))), 4)


def query_cache_key(
    index: dict[str, Any],
    query: str,
    *,
    media_path: str = "",
    media_id: str = "",
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    kinds: set[str] | None = None,
    limit: int = 16,
    per_kind: int = 5,
) -> str:
    return stable_hash(
        {
            "score_model": LORA_RETRIEVAL_SCORE_MODEL,
            "index_updated_at": index.get("updated_at"),
            "source_signature": index.get("source_signature"),
            "doc_count": index.get("doc_count"),
            "query": query,
            "media_path": media_path,
            "media_id": media_id,
            "settings": json_preview(settings or {}),
            "context": json_preview(context or {}),
            "kinds": sorted(kinds or []),
            "limit": int(limit or 0),
            "per_kind": int(per_kind or 0),
        }
    )


def score_lora_docs(
    index: dict[str, Any],
    query: str,
    *,
    media_path: str = "",
    media_id: str = "",
    query_facets: dict[str, Any] | None = None,
    kinds: set[str] | None = None,
) -> list[dict[str, Any]]:
    docs = list(index.get("docs") or [])
    query_vector = vectorize_lora_text(query)
    query_terms = term_counts(query)
    if not docs or (not query_vector and not query_terms):
        return []
    inverted = dict(index.get("inverted_index") or {})
    vector_scores: dict[int, float] = defaultdict(float)
    for bucket, query_weight in query_vector.items():
        for doc_index, doc_weight in list(inverted.get(str(bucket), []) or []):
            try:
                vector_scores[int(doc_index)] += float(query_weight) * float(doc_weight)
            except Exception:
                continue
    bm25_scores = _bm25_scores(index, query_terms)
    ranked: list[dict[str, Any]] = []
    for doc_index in set(vector_scores) | set(bm25_scores):
        if doc_index < 0 or doc_index >= len(docs):
            continue
        doc = dict(docs[doc_index] or {})
        kind = str(doc.get("kind") or "")
        if kinds is not None and kind not in kinds:
            continue
        quality = max(0.0, min(1.0, safe_float(doc.get("quality"), 0.0)))
        overlap = token_overlap_score(query, str(doc.get("text_preview") or ""))
        vector_score = float(vector_scores.get(doc_index, 0.0) or 0.0)
        bm25_raw = float(bm25_scores.get(doc_index, 0.0) or 0.0)
        vector_points = vector_score * float(SCORE_POINT_WEIGHTS["vector"])
        bm25_points = min(
            float(SCORE_POINT_WEIGHTS["bm25_cap"]),
            math.log1p(max(0.0, bm25_raw)) * float(SCORE_POINT_WEIGHTS["bm25"]),
        )
        overlap_points = overlap * float(SCORE_POINT_WEIGHTS["overlap"])
        quality_points = quality * float(SCORE_POINT_WEIGHTS["quality"])
        kind_points = _kind_boost(kind)
        media_points = _media_match_boost(doc, media_path=media_path, media_id=media_id)
        facet_points, facet_matches = _facet_match_points(doc, query_facets)
        recency_points = _recency_points(doc)
        final_score = min(
            100.0,
            vector_points + bm25_points + overlap_points + quality_points + kind_points + media_points + facet_points + recency_points,
        )
        doc["vector_score"] = round(float(vector_score), 6)
        doc["bm25_score"] = round(float(bm25_raw), 6)
        doc["overlap_score"] = round(overlap, 6)
        doc["retrieval_score"] = round(final_score, 4)
        doc["score_model"] = LORA_RETRIEVAL_SCORE_MODEL
        doc["score_breakdown"] = {
            "vector": round(vector_points, 4),
            "bm25": round(bm25_points, 4),
            "overlap": round(overlap_points, 4),
            "quality": round(quality_points, 4),
            "kind": round(kind_points, 4),
            "media": round(media_points, 4),
            "facet": round(facet_points, 4),
            "recency": round(recency_points, 4),
            "final": round(final_score, 4),
        }
        if facet_matches:
            doc["facet_matches"] = facet_matches
        ranked.append(doc)
    ranked.sort(
        key=lambda item: (float(item.get("retrieval_score", 0.0) or 0.0), float(item.get("quality", 0.0) or 0.0)),
        reverse=True,
    )
    return ranked


def runtime_settings_from_retrieved_items(
    items: list[dict[str, Any]],
    *,
    min_score: float = 28.0,
) -> dict[str, Any]:
    override: dict[str, Any] = {}
    for item in list(items or []):
        score = safe_float(item.get("retrieval_score"), 0.0)
        if score < min_score:
            continue
        kind = str(item.get("kind") or "")
        payload = dict(item.get("payload") or {})
        if kind in {"setting_trials", "best_settings"}:
            config = dict(payload.get("config") or {})
            for key, value in config.items():
                if key in RUNTIME_SETTING_KEYS and value not in (None, ""):
                    override[key] = value
        elif kind == "audio_preset_lora":
            config = dict(payload.get("audio_tune_settings") or payload.get("settings") or {})
            for key, value in config.items():
                if key in RUNTIME_SETTING_KEYS and value not in (None, ""):
                    override[key] = value
        elif kind == "multimodal_lora_context":
            summary = dict(payload.get("classification_summary") or {})
            scene = str(summary.get("scene") or "")
            noise_level = str(summary.get("noise_level") or "")
            noise_sources = {str(item) for item in list(summary.get("noise_sources") or [])}
            subtitle_profile = dict(payload.get("subtitle_profile") or {})
            reading = dict(subtitle_profile.get("reading_speed") or {})
            max_cps = safe_float(reading.get("max_cps"), 0.0)
            if scene in {"car", "outdoor"} or noise_level == "high" or noise_sources.intersection({"engine", "traffic", "wind", "crowd", "music"}):
                override.setdefault("selected_audio_ai", "clearvoice")
                override.setdefault("stt_quality_preset", "precise")
                override.setdefault("subtitle_quality_enabled", True)
            if max_cps > 0:
                override.setdefault("sub_max_cps", max(10, min(18, safe_int(max_cps))))
            excluded_ratio = safe_float(subtitle_profile.get("excluded_parenthetical_ratio"), 0.0)
            if excluded_ratio >= 0.1:
                override.setdefault("subtitle_quality_auto_correct_enabled", True)
    return {key: value for key, value in override.items() if key in RUNTIME_SETTING_KEYS and value not in (None, "")}
