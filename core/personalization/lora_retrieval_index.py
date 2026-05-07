from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_quality_buckets import lora_bucket_for_row, lora_score_for_row
from core.personalization.lora_retrieval_config import (
    INDEX_JSON_SOURCE_KEYS,
    INDEX_JSONL_SOURCE_KEYS,
    LORA_RETRIEVAL_HASH_DIM,
    LORA_RETRIEVAL_INDEX_SCHEMA,
    LORA_RETRIEVAL_MAX_TEXT_CHARS,
    LORA_RETRIEVAL_SCORE_MODEL,
)
from core.personalization.lora_retrieval_utils import (
    classification_summary,
    doc_facets,
    facet_label,
    facet_list,
    flatten_search_text,
    json_preview,
    norm_text,
    path_leaf_terms,
    read_json,
    read_jsonl,
    strip_editorial_brackets,
    term_counts,
    vectorize_lora_text,
)
from core.personalization.lora_storage import personalization_path_lookup_keys


def source_signature(paths: dict[str, Path]) -> dict[str, Any]:
    signature: dict[str, Any] = {
        "schema": LORA_RETRIEVAL_INDEX_SCHEMA,
        "hash_dim": LORA_RETRIEVAL_HASH_DIM,
        "sources": {},
    }
    for key in INDEX_JSONL_SOURCE_KEYS + INDEX_JSON_SOURCE_KEYS:
        path = paths.get(key)
        if path is None:
            continue
        try:
            stat = path.stat()
            signature["sources"][key] = {
                "path": str(path),
                "exists": True,
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        except OSError:
            signature["sources"][key] = {"path": str(path), "exists": False, "size": 0, "mtime_ns": 0}
    return signature


def index_is_current(index: dict[str, Any], paths: dict[str, Path]) -> bool:
    if not isinstance(index, dict):
        return False
    if str(index.get("schema") or "") != LORA_RETRIEVAL_INDEX_SCHEMA:
        return False
    if str(index.get("score_model") or "") != LORA_RETRIEVAL_SCORE_MODEL:
        return False
    if int(index.get("hash_dim", 0) or 0) != LORA_RETRIEVAL_HASH_DIM:
        return False
    return dict(index.get("source_signature") or {}) == source_signature(paths)


def _payload_for_kind(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    base_keys = (
        "media_id",
        "media_path",
        "subtitle_path",
        "created_at",
        "captured_at",
        "updated_at",
        "source",
        "task",
        "score",
        "metrics",
        "reason",
    )
    payload = {key: json_preview(row.get(key)) for key in base_keys if row.get(key) not in (None, "", [], {})}
    if kind == "truth_table":
        payload.update(
            {
                "speech_training_text": strip_editorial_brackets(row.get("speech_training_text")),
                "line_break_pattern": json_preview(row.get("line_break_pattern")),
                "punctuation_pattern": json_preview(row.get("punctuation_pattern")),
                "cps": row.get("cps"),
                "duration_sec": row.get("duration_sec"),
                "detected_split_rule": json_preview(row.get("detected_split_rule")),
                "style_profile": json_preview(row.get("style_profile") or row.get("subtitle_style_profile") or {}),
            }
        )
    elif kind in {"text_lora_dataset", "text_lora_corpus"}:
        meta = row.get("meta") or row.get("metadata") or {}
        meta = meta if isinstance(meta, dict) else {}
        payload.update(
            {
                "input": strip_editorial_brackets(row.get("input")),
                "output": strip_editorial_brackets(row.get("output")),
                "meta": json_preview(meta),
                "style_profile": json_preview(meta.get("style_profile") or {}),
            }
        )
    elif kind == "excluded_parentheticals":
        payload.update(
            {
                "excluded_text": json_preview(row.get("excluded_text")),
                "kept_text": strip_editorial_brackets(row.get("kept_text")),
                "reason_code": json_preview(row.get("reason_code")),
            }
        )
    elif kind in {"setting_trials", "prompt_trials"}:
        payload.update(
            {
                "config": json_preview(row.get("config") or {}),
                "prompt_template_id": json_preview(row.get("prompt_template_id")),
                "prompt_text": json_preview(row.get("prompt_text")),
            }
        )
    elif kind == "multimodal_lora_context":
        payload.update(
            {
                "context_classification": json_preview(row.get("context_classification") or {}),
                "classification_summary": classification_summary(row.get("context_classification") or {}),
                "media_profile": json_preview(row.get("media_profile") or {}),
                "subtitle_profile": json_preview(row.get("subtitle_profile") or {}),
                "subtitle_style_profile": json_preview(row.get("subtitle_style_profile") or {}),
                "candidate_context": json_preview(row.get("candidate_context") or {}),
                "generation_targets": json_preview(row.get("generation_targets") or {}),
            }
        )
    elif kind == "audio_preset_lora":
        payload.update(
            {
                "audio_strategy": json_preview(row.get("audio_strategy")),
                "audio_strategy_label": json_preview(row.get("audio_strategy_label")),
                "confidence": row.get("confidence"),
                "audio_profile": json_preview(row.get("audio_profile") or {}),
                "features": json_preview(row.get("features") or {}),
                "audio_tune_settings": json_preview(row.get("audio_tune_settings") or row.get("settings") or {}),
            }
        )
    elif kind == "deep_policy_events":
        payload.update(
            {
                "event_type": json_preview(row.get("event_type")),
                "text": strip_editorial_brackets(row.get("text")),
                "decision": json_preview(row.get("decision") or {}),
                "features": json_preview(row.get("features") or {}),
                "applied_settings": json_preview(row.get("applied_settings") or {}),
                "hard_case": bool(row.get("hard_case")),
            }
        )
    elif kind == "voice_lora_bridge":
        payload.update(
            {
                "speaker": json_preview(row.get("speaker")),
                "text": strip_editorial_brackets(row.get("text")),
                "duration_sec": row.get("duration_sec"),
                "clip_path": json_preview(row.get("clip_path")),
            }
        )
    elif kind == "stt1_whisper_adapter_dataset":
        payload.update(
            {
                "transcript_text": strip_editorial_brackets(row.get("transcript_text")),
                "weak_input_text": strip_editorial_brackets(row.get("weak_input_text")),
                "speaker": json_preview(row.get("speaker")),
                "classification_summary": json_preview(row.get("classification_summary") or {}),
                "candidate_context_summary": json_preview(row.get("candidate_context_summary") or {}),
                "training_tags": json_preview(row.get("training_tags") or []),
            }
        )
    elif kind.startswith("learned_"):
        payload.update(
            {
                "rule_text": json_preview(row.get("rule_text")),
                "rule_type": json_preview(row.get("rule_type")),
                "confidence": row.get("confidence"),
                "frequency": row.get("frequency"),
                "examples": json_preview(row.get("examples") or []),
            }
        )
    elif kind == "best_settings":
        payload.update({"config": json_preview(row.get("config") or {})})
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _quality_for_doc(kind: str, row: dict[str, Any]) -> float:
    return max(0.0, min(1.0, lora_score_for_row(kind, row) / 100.0))


def _created_at_for_doc(row: dict[str, Any]) -> str:
    return str(row.get("updated_at") or row.get("captured_at") or row.get("created_at") or "")


def _document_text(kind: str, row: dict[str, Any]) -> str:
    media_path = str(row.get("media_path") or row.get("clip_path") or "")
    common = [kind, str(row.get("media_id") or ""), media_path, path_leaf_terms(media_path), str(row.get("source") or ""), str(row.get("task") or "")]
    if kind == "truth_table":
        return norm_text(
            " ".join(
                [
                    *common,
                    strip_editorial_brackets(row.get("speech_training_text")),
                    str(row.get("line_break_pattern") or ""),
                    str(row.get("punctuation_pattern") or ""),
                    str(row.get("detected_split_rule") or ""),
                    *flatten_search_text(row.get("style_profile") or row.get("subtitle_style_profile") or {}),
                    *flatten_search_text(row.get("extra") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind in {"text_lora_dataset", "text_lora_corpus"}:
        meta = row.get("meta") or row.get("metadata") or {}
        meta = meta if isinstance(meta, dict) else {}
        return norm_text(
            " ".join(
                [
                    *common,
                    strip_editorial_brackets(row.get("input")),
                    strip_editorial_brackets(row.get("output")),
                    *flatten_search_text(meta),
                    *flatten_search_text(meta.get("style_profile") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "excluded_parentheticals":
        return norm_text(
            " ".join(
                [
                    *common,
                    "editorial bracket parenthetical exclusion do not learn spoken subtitle 설명 자막 제외",
                    str(row.get("excluded_text") or ""),
                    strip_editorial_brackets(row.get("kept_text")),
                    str(row.get("reason_code") or ""),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind in {"setting_trials", "prompt_trials"}:
        return norm_text(
            " ".join(
                [
                    *common,
                    str(row.get("reason") or ""),
                    str(row.get("prompt_template_id") or ""),
                    str(row.get("prompt_text") or ""),
                    *flatten_search_text(row.get("config") or {}),
                    *flatten_search_text(row.get("metrics") or {}),
                    *flatten_search_text(row.get("metadata") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "multimodal_lora_context":
        return norm_text(
            " ".join(
                [
                    *common,
                    "video audio subtitle context scene microphone topic classification",
                    *flatten_search_text(row.get("context_classification") or {}),
                    *flatten_search_text(row.get("media_profile") or {}),
                    *flatten_search_text(row.get("subtitle_profile") or {}),
                    *flatten_search_text(row.get("subtitle_style_profile") or {}),
                    *flatten_search_text(row.get("candidate_context") or {}),
                    *flatten_search_text(row.get("generation_targets") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "audio_preset_lora":
        return norm_text(
            " ".join(
                [
                    *common,
                    str(row.get("audio_strategy") or ""),
                    str(row.get("audio_strategy_label") or ""),
                    str(row.get("reason") or ""),
                    *flatten_search_text(row.get("audio_profile") or {}),
                    *flatten_search_text(row.get("features") or {}),
                    *flatten_search_text(row.get("audio_tune_settings") or {}),
                    *flatten_search_text(row.get("candidate_scores") or []),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "deep_policy_events":
        return norm_text(
            " ".join(
                [
                    *common,
                    "deep policy decision subtitle rerank timing stt setting sequence hard case active learning",
                    strip_editorial_brackets(row.get("text")),
                    str(row.get("event_type") or ""),
                    *flatten_search_text(row.get("decision") or {}),
                    *flatten_search_text(row.get("features") or {}),
                    *flatten_search_text(row.get("applied_settings") or {}),
                    *flatten_search_text(row.get("metadata") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "voice_lora_bridge":
        return norm_text(
            " ".join(
                [
                    *common,
                    str(row.get("speaker") or ""),
                    strip_editorial_brackets(row.get("text")),
                    *flatten_search_text(row.get("context_classification") or {}),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    if kind == "stt1_whisper_adapter_dataset":
        return norm_text(
            " ".join(
                [
                    *common,
                    "stt1 whisper adapter training runtime personalization",
                    strip_editorial_brackets(row.get("transcript_text")),
                    strip_editorial_brackets(row.get("weak_input_text")),
                    str(row.get("speaker") or ""),
                    *flatten_search_text(row.get("classification_summary") or {}),
                    *flatten_search_text(row.get("candidate_context_summary") or {}),
                    *flatten_search_text(row.get("training_tags") or []),
                ]
            )
        )[:LORA_RETRIEVAL_MAX_TEXT_CHARS]
    return norm_text(" ".join([*common, *flatten_search_text(row)]))[:LORA_RETRIEVAL_MAX_TEXT_CHARS]


def _make_doc(kind: str, row: dict[str, Any], ordinal: int) -> dict[str, Any] | None:
    text = _document_text(kind, row)
    vector = vectorize_lora_text(text)
    if not vector:
        return None
    media_path = str(row.get("media_path") or row.get("clip_path") or "")
    media_keys = personalization_path_lookup_keys(media_path)
    doc_id = str(row.get("signature") or row.get("dedupe_hash") or row.get("trial_id") or row.get("rule_id") or "")
    if not doc_id:
        doc_id = stable_hash({"kind": kind, "ordinal": ordinal, "text": text})[:24]
    payload = _payload_for_kind(kind, row)
    counts = term_counts(text)
    quality_score = max(0.0, min(100.0, lora_score_for_row(kind, row)))
    quality_bucket = lora_bucket_for_row(kind, row)
    return {
        "doc_id": f"{kind}:{doc_id}",
        "kind": kind,
        "created_at": _created_at_for_doc(row),
        "quality": round(_quality_for_doc(kind, row), 4),
        "quality_score": round(quality_score, 4),
        "quality_bucket": quality_bucket,
        "score_index": round(quality_score, 4),
        "media_id": str(row.get("media_id") or ""),
        "media_path": media_path,
        "media_lookup_keys": media_keys[:6],
        "text_preview": text[:420],
        "payload": payload,
        "facets": doc_facets(kind, row, payload, text),
        "doc_len": int(sum(counts.values())),
        "_vector": vector,
        "_terms": counts,
    }


def _iter_jsonl_docs(paths: dict[str, Path]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for kind in INDEX_JSONL_SOURCE_KEYS:
        for ordinal, row in enumerate(read_jsonl(paths[kind])):
            doc = _make_doc(kind, dict(row), ordinal)
            if doc is not None:
                docs.append(doc)
    return docs


def _iter_learned_rule_docs(paths: dict[str, Path]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for rule_kind, path_key in (("learned_split_rules", "learned_split_rules"), ("learned_line_break_rules", "learned_line_break_rules")):
        payload = read_json(paths[path_key], {})
        for ordinal, item in enumerate(list((payload or {}).get("items") or [])):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["source"] = path_key
            doc = _make_doc(rule_kind, row, ordinal)
            if doc is not None:
                docs.append(doc)
    return docs


def _iter_best_setting_docs(paths: dict[str, Path]) -> list[dict[str, Any]]:
    payload = read_json(paths["best_settings"], {})
    if not isinstance(payload, dict):
        return []
    docs: list[dict[str, Any]] = []
    defaults = dict(payload.get("global_recommended_defaults") or {})
    if defaults:
        doc = _make_doc(
            "best_settings",
            {"media_id": "global", "config": defaults, "score": 78.0, "updated_at": payload.get("updated_at"), "source": "global_defaults"},
            0,
        )
        if doc is not None:
            docs.append(doc)
    ordinal = 1
    for section in ("by_media_id", "by_media_path", "by_audio_profile", "by_style_cluster"):
        for key, item in dict(payload.get(section) or {}).items():
            if not isinstance(item, dict):
                continue
            row = {
                "media_id": str(key) if section == "by_media_id" else str(item.get("media_id") or ""),
                "media_path": str(item.get("media_path") or (key if section == "by_media_path" else "")),
                "config": dict(item.get("config") or {}),
                "score": item.get("score"),
                "source": section,
                "reason": str(key),
                "updated_at": payload.get("updated_at"),
            }
            doc = _make_doc("best_settings", row, ordinal)
            ordinal += 1
            if doc is not None:
                docs.append(doc)
    return docs


def _iter_manifest_plan_docs(paths: dict[str, Path]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for ordinal, key in enumerate(
        (
            "text_lora_manifest",
            "text_lora_corpus_manifest",
            "text_lora_training_plan",
        )
    ):
        payload = read_json(paths[key], {})
        if not isinstance(payload, dict) or not payload:
            continue
        row = {
            "media_id": "global",
            "source": key,
            "task": "lora_training_manifest",
            "updated_at": payload.get("updated_at"),
            "metadata": payload,
        }
        doc = _make_doc("training_manifest", row, ordinal)
        if doc is not None:
            docs.append(doc)
    return docs


def _build_bm25_index(docs: list[dict[str, Any]]) -> dict[str, Any]:
    postings: dict[str, list[list[int]]] = defaultdict(list)
    doc_lengths: list[int] = []
    for doc_index, doc in enumerate(docs):
        counts = Counter(doc.pop("_terms", {}) or {})
        doc_len = int(sum(int(value) for value in counts.values()))
        doc_lengths.append(doc_len)
        doc["doc_len"] = doc_len
        for term_hash, tf in counts.items():
            try:
                tf_int = int(tf)
            except Exception:
                continue
            if tf_int > 0:
                postings[str(term_hash)].append([doc_index, tf_int])
    doc_count = len(docs)
    avg_doc_len = sum(doc_lengths) / max(1, doc_count)
    idf: dict[str, float] = {}
    for term_hash, values in postings.items():
        df = len(values)
        idf[term_hash] = round(math.log(1.0 + (doc_count - df + 0.5) / max(0.5, df + 0.5)), 6)
    return {
        "model": "bm25_hash_terms.v1",
        "doc_count": doc_count,
        "avg_doc_len": round(float(avg_doc_len), 6),
        "doc_lengths": doc_lengths,
        "term_count": len(postings),
        "idf": idf,
        "term_postings": {term_hash: values for term_hash, values in postings.items()},
    }


def _adaptive_profiles(docs: list[dict[str, Any]]) -> dict[str, Any]:
    facet_counts: dict[str, Counter[str]] = {
        "scene": Counter(),
        "topic": Counter(),
        "mic_type": Counter(),
        "noise_level": Counter(),
        "noise_sources": Counter(),
        "training_focus": Counter(),
    }
    kind_by_topic: dict[str, Counter[str]] = defaultdict(Counter)
    for doc in docs:
        kind = str(doc.get("kind") or "")
        facets = dict(doc.get("facets") or {})
        for key in ("scene", "topic", "mic_type", "noise_level"):
            value = facet_label(facets.get(key))
            if value:
                facet_counts[key][value] += 1
        for key in ("noise_sources", "training_focus"):
            for value in facet_list(facets.get(key) or []):
                facet_counts[key][value] += 1
        topic = facet_label(facets.get("topic"))
        if kind and topic:
            kind_by_topic[kind][topic] += 1
    return {
        "schema": "ai_subtitle_studio.lora_adaptive_profiles.v1",
        "score_model": LORA_RETRIEVAL_SCORE_MODEL,
        "facets": {key: dict(counter.most_common(16)) for key, counter in facet_counts.items()},
        "kind_by_topic": {kind: dict(counter.most_common(12)) for kind, counter in kind_by_topic.items()},
    }


def _build_inverted_index(docs: list[dict[str, Any]]) -> dict[str, list[list[float]]]:
    postings: dict[str, list[list[float]]] = defaultdict(list)
    for doc_index, doc in enumerate(docs):
        vector = dict(doc.pop("_vector", {}) or {})
        for bucket, weight in vector.items():
            postings[str(bucket)].append([doc_index, float(weight)])
    return {bucket: values for bucket, values in postings.items()}


def build_lora_retrieval_index_payload(paths: dict[str, Path]) -> dict[str, Any]:
    docs = _iter_jsonl_docs(paths)
    docs.extend(_iter_learned_rule_docs(paths))
    docs.extend(_iter_best_setting_docs(paths))
    docs.extend(_iter_manifest_plan_docs(paths))
    kind_counts = Counter(str(doc.get("kind") or "") for doc in docs)
    return {
        "schema": LORA_RETRIEVAL_INDEX_SCHEMA,
        "updated_at": iso_now(),
        "score_model": LORA_RETRIEVAL_SCORE_MODEL,
        "hash_dim": LORA_RETRIEVAL_HASH_DIM,
        "source_signature": source_signature(paths),
        "doc_count": len(docs),
        "kind_counts": dict(sorted(kind_counts.items())),
        "docs": docs,
        "bm25": _build_bm25_index(docs),
        "adaptive_profiles": _adaptive_profiles(docs),
        "inverted_index": _build_inverted_index(docs),
        "notes": [
            "Hybrid hashed-vector + BM25 + context-facet scorer for fast LoRA/RAG subtitle personalization retrieval.",
            "Bracketed editorial text is indexed only as exclusion policy, not as spoken subtitle target.",
        ],
    }
