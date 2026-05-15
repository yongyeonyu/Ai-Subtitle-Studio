from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from core.coerce import safe_float as _safe_float
from core.media_fingerprint import media_fingerprint_digest
from core.audio.stt_candidate_scorer import score_stt_candidate
from core.native_text_similarity import similarity_ratio
from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_storage import LORA_INTERNAL_CACHE_DIR
from core.runtime.json_utils import json_safe as _json_safe
from core.text_utils import clean_text as _normalize


STT_LATTICE_SCHEMA = "ai_subtitle_studio.stt_candidate_lattice.v1"
STT_LATTICE_ARTIFACT_SCHEMA = "ai_subtitle_studio.stt_candidate_lattice_artifact.v1"
STT_LATTICE_MODEL_ID = "word_confidence_lattice_v1"
STT_LATTICE_CANDIDATE_KEYS = (
    "stt_candidates",
    "stt_lattice_candidates",
    "vad_candidates",
    "stt_retry_candidates",
    "stt_recheck_candidates",
    "stt_rescue_candidates",
    "manual_stt_candidates",
    "manual_recheck_candidates",
    "manual_rerecognition_candidates",
    "manual_re_recognition_candidates",
    "stt_manual_candidates",
)


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    return bool(value)

def _compact(text: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def _similarity(left: Any, right: Any) -> float:
    ltxt = _compact(left)
    rtxt = _compact(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    return similarity_ratio(ltxt, rtxt)


def _word_text(word: dict[str, Any]) -> str:
    return _normalize(word.get("word") or word.get("text") or "")


def _word_confidence(word: dict[str, Any], fallback: float = 0.45) -> float:
    for key in ("confidence", "probability", "score"):
        if word.get(key) is not None:
            return max(0.0, min(1.0, _safe_float(word.get(key), fallback)))
    return fallback


def _candidate_score_100(candidate: dict[str, Any]) -> float:
    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        if candidate.get(key) is None:
            continue
        score = _safe_float(candidate.get(key), 0.0)
        if score <= 1.0:
            score *= 100.0
        return max(0.0, min(100.0, score))
    return float(score_stt_candidate(candidate).get("score", 0.0) or 0.0)


def _source_label(source: Any, *, default: str = "CURRENT") -> str:
    text = str(source or "").strip()
    return text or default


def _candidate_role(candidate_key: str, candidate: dict[str, Any]) -> str:
    key = str(candidate_key or "").strip()
    source = str(candidate.get("source") or candidate.get("stt_source") or "").lower()
    if key == "current":
        return "selected_current"
    if key == "vad_candidates":
        return "vad_variant"
    if key == "stt_retry_candidates":
        return "retry"
    if key == "stt_recheck_candidates":
        return "low_score_recheck"
    if key == "stt_rescue_candidates":
        return "rescue"
    if key == "stt_lattice_candidates":
        return "lattice"
    if key in {"manual_stt_candidates", "manual_recheck_candidates", "manual_rerecognition_candidates", "manual_re_recognition_candidates", "stt_manual_candidates"}:
        return "manual_re_recognition"
    if "vad" in source:
        return "vad_variant"
    if "retry" in source:
        return "retry"
    if "recheck" in source:
        return "low_score_recheck"
    if "rescue" in source:
        return "rescue"
    if "manual" in source:
        return "manual_re_recognition"
    return "stt_candidate"


def _words_from_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    raw_words = [word for word in list(candidate.get("words") or []) if isinstance(word, dict)]
    words: list[dict[str, Any]] = []
    for raw in raw_words:
        text = _word_text(raw)
        if not text:
            continue
        start = _safe_float(raw.get("start"), _safe_float(candidate.get("start"), 0.0))
        end = _safe_float(raw.get("end"), start)
        item = dict(raw)
        item["word"] = text
        item["start"] = round(start, 3)
        item["end"] = round(max(start, end), 3)
        words.append(item)
    if words:
        return words

    tokens = [token for token in re.split(r"\s+", _normalize(candidate.get("text"))) if token]
    if not tokens:
        return []
    start = _safe_float(candidate.get("start"), 0.0)
    end = max(start + 0.05, _safe_float(candidate.get("end"), start + 0.05))
    step = (end - start) / max(1, len(tokens))
    return [
        {
            "word": token,
            "start": round(start + step * idx, 3),
            "end": round(start + step * (idx + 1), 3),
            "synthetic": True,
        }
        for idx, token in enumerate(tokens)
    ]


def _word_time_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    start = max(_safe_float(left.get("start")), _safe_float(right.get("start")))
    end = min(_safe_float(left.get("end")), _safe_float(right.get("end")))
    overlap = max(0.0, end - start)
    span = max(
        _safe_float(left.get("end")) - _safe_float(left.get("start")),
        _safe_float(right.get("end")) - _safe_float(right.get("start")),
        0.05,
    )
    overlap_score = overlap / span
    left_mid = (_safe_float(left.get("start")) + _safe_float(left.get("end"))) / 2.0
    right_mid = (_safe_float(right.get("start")) + _safe_float(right.get("end"))) / 2.0
    midpoint_score = max(0.0, 1.0 - abs(left_mid - right_mid) / 0.75)
    return max(overlap_score, midpoint_score * 0.75)


def _protected_word(text: Any) -> bool:
    raw = str(text or "")
    compact = _compact(raw)
    if not compact:
        return True
    if any(ch.isdigit() for ch in compact):
        return True
    if len(compact) <= 1:
        return True
    return bool(re.search(r"[A-Z]{2,}", raw))


def _find_match(anchor: dict[str, Any], words: list[dict[str, Any]], used: set[int], min_match_score: float) -> tuple[int | None, float]:
    best_idx = None
    best_score = 0.0
    for idx, word in enumerate(words):
        if idx in used:
            continue
        temporal = _word_time_score(anchor, word)
        textual = _similarity(_word_text(anchor), _word_text(word))
        score = temporal * 0.62 + textual * 0.38
        if score > best_score:
            best_idx = idx
            best_score = score
    if best_score < min_match_score:
        return None, best_score
    return best_idx, best_score


def collect_stt_lattice_candidates(
    segment: dict[str, Any],
    *,
    include_current: bool = True,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Collect every STT candidate family into one replayable lattice."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, float, str]] = set()

    def add(candidate_key: str, candidate: dict[str, Any], fallback_source: str = "CURRENT") -> None:
        if not isinstance(candidate, dict):
            return
        text = _normalize(candidate.get("text"))
        if not text:
            return
        start = _safe_float(candidate.get("start", candidate.get("timeline_start", segment.get("start", 0.0))))
        end = _safe_float(candidate.get("end", candidate.get("timeline_end", segment.get("end", start))), start)
        source = _source_label(
            candidate.get("source")
            or candidate.get("stt_source")
            or candidate.get("stt_preview_source")
            or candidate.get("label"),
            default=fallback_source,
        )
        key = (str(candidate_key), source.upper(), round(start, 3), round(end, 3), _compact(text))
        if key in seen:
            return
        seen.add(key)
        item = dict(candidate)
        item["source"] = source
        item["text"] = text
        item.setdefault("start", start)
        item.setdefault("end", end)
        item["candidate_key"] = str(candidate_key)
        item["candidate_role"] = _candidate_role(candidate_key, item)
        item["candidate_index"] = len(out)
        out.append(item)

    if include_current:
        current = {
            "source": str(segment.get("stt_ensemble_source") or segment.get("stt_selected_source") or segment.get("source") or "CURRENT"),
            "text": _normalize(segment.get("text")),
            "start": segment.get("start", segment.get("timeline_start")),
            "end": segment.get("end", segment.get("timeline_end")),
            "words": list(segment.get("words") or []),
            "score": segment.get("score") or segment.get("stt_score"),
        }
        add("current", current, "CURRENT")
    for candidate_key in STT_LATTICE_CANDIDATE_KEYS:
        fallback_source = "MANUAL" if "manual" in candidate_key else "STT"
        for candidate in list(segment.get(candidate_key) or []):
            add(candidate_key, candidate, fallback_source)
            if limit is not None and limit > 0 and len(out) >= limit:
                return out
    return out


def _candidate_sources(segment: dict[str, Any]) -> list[dict[str, Any]]:
    return collect_stt_lattice_candidates(segment, include_current=True)


def _segment_id(segment: dict[str, Any], index: int) -> str:
    explicit = str(segment.get("id") or segment.get("segment_id") or "").strip()
    if explicit:
        return explicit
    return stable_hash(
        {
            "index": index,
            "start": round(_safe_float(segment.get("start", segment.get("timeline_start"))), 3),
            "end": round(_safe_float(segment.get("end", segment.get("timeline_end"))), 3),
            "text": str(segment.get("text") or "")[:160],
        }
    )[:20]


def _candidate_for_artifact(candidate: dict[str, Any], *, word_limit: int = 128) -> dict[str, Any]:
    words = [dict(word) for word in list(candidate.get("words") or []) if isinstance(word, dict)]
    compact = {
        "candidate_index": candidate.get("candidate_index"),
        "candidate_key": str(candidate.get("candidate_key") or ""),
        "candidate_role": str(candidate.get("candidate_role") or ""),
        "source": str(candidate.get("source") or ""),
        "label": str(candidate.get("label") or ""),
        "start": round(_safe_float(candidate.get("start", candidate.get("timeline_start"))), 3),
        "end": round(_safe_float(candidate.get("end", candidate.get("timeline_end"))), 3),
        "text": str(candidate.get("text") or ""),
        "score": _json_safe(candidate.get("score", candidate.get("stt_score"))),
        "confidence": _json_safe(candidate.get("confidence", candidate.get("confidence_score"))),
    }
    for key in (
        "stt_score",
        "avg_confidence",
        "avg_logprob",
        "no_speech_prob",
        "compression_ratio",
        "stt_recheck_applied",
        "stt_recheck_original_scores",
        "selected",
        "selection_reason",
    ):
        if key in candidate:
            compact[key] = _json_safe(candidate.get(key))
    if words:
        compact["words"] = _json_safe(words[: max(1, int(word_limit or 1))], max_depth=5)
        compact["word_count"] = len(words)
    return compact


def build_stt_lattice_artifact(
    segments: Iterable[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
    *,
    media_path: str = "",
    project_path: str = "",
) -> dict[str, Any]:
    settings = dict(settings or {})
    candidate_limit = int(_safe_float(settings.get("stt_lattice_artifact_candidate_limit"), 64))
    word_limit = int(_safe_float(settings.get("stt_lattice_artifact_word_limit"), 128))
    rows = [dict(row) for row in list(segments or []) if isinstance(row, dict) and not row.get("is_gap")]
    role_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    segment_rows: list[dict[str, Any]] = []
    accepted_count = 0

    for index, segment in enumerate(rows):
        candidates = collect_stt_lattice_candidates(segment, include_current=True, limit=max(1, candidate_limit))
        for candidate in candidates:
            role = str(candidate.get("candidate_role") or "unknown")
            source = str(candidate.get("source") or "unknown").upper()
            role_counts[role] = role_counts.get(role, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1
        policy = dict(segment.get("_stt_lattice_policy") or {})
        if policy.get("accepted"):
            accepted_count += 1
        segment_rows.append(
            {
                "segment_id": _segment_id(segment, index),
                "index": index,
                "start": round(_safe_float(segment.get("start", segment.get("timeline_start"))), 3),
                "end": round(_safe_float(segment.get("end", segment.get("timeline_end"))), 3),
                "text": str(segment.get("text") or ""),
                "speaker": str(segment.get("speaker") or ""),
                "selected": {
                    "source": str(segment.get("stt_selected_source") or segment.get("stt_ensemble_source") or segment.get("source") or ""),
                    "text": str(segment.get("text") or ""),
                    "score": _json_safe(segment.get("score", segment.get("stt_score"))),
                },
                "selector_policy": _json_safe(policy),
                "candidate_lattice": [_candidate_for_artifact(candidate, word_limit=word_limit) for candidate in candidates],
                "candidate_count": len(candidates),
                "candidate_role_counts": {
                    role: sum(1 for candidate in candidates if str(candidate.get("candidate_role") or "") == role)
                    for role in sorted({str(candidate.get("candidate_role") or "") for candidate in candidates})
                    if role
                },
            }
        )

    try:
        media_digest = media_fingerprint_digest(media_path, sample_bytes=0, include_samples=False) if media_path else ""
    except Exception:
        media_digest = ""
    return {
        "schema": STT_LATTICE_ARTIFACT_SCHEMA,
        "created_at": iso_now(),
        "media_path": str(media_path or ""),
        "media_fingerprint_digest": media_digest,
        "project_path": str(project_path or ""),
        "segment_count": len(segment_rows),
        "summary": {
            "candidate_count": sum(row.get("candidate_count", 0) for row in segment_rows),
            "accepted_count": accepted_count,
            "role_counts": role_counts,
            "source_counts": source_counts,
        },
        "segments": segment_rows,
    }


def stt_lattice_artifact_path(
    *,
    project_path: str = "",
    media_path: str = "",
    cache_dir: str | Path | None = None,
) -> Path:
    if project_path:
        path = Path(project_path)
        return path.with_name(f"{path.stem}.stt_lattice.json")
    root = Path(cache_dir) if cache_dir else Path(LORA_INTERNAL_CACHE_DIR) / "stt_lattices"
    try:
        media_digest = media_fingerprint_digest(media_path, sample_bytes=0, include_samples=False) if media_path else ""
    except Exception:
        media_digest = ""
    key = stable_hash({"media_path": str(media_path or ""), "media_fingerprint_digest": media_digest, "project_path": str(project_path or "")})[:20]
    return root / f"{key}.stt_lattice.json"


def persist_stt_lattice_artifact(
    segments: Iterable[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
    *,
    media_path: str = "",
    project_path: str = "",
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = _safe_bool(settings.get("stt_lattice_persist_enabled"), True)
    if not enabled:
        return {"schema": STT_LATTICE_ARTIFACT_SCHEMA, "enabled": False, "path": ""}
    artifact = build_stt_lattice_artifact(segments, settings, media_path=media_path, project_path=project_path)
    path = stt_lattice_artifact_path(project_path=project_path, media_path=media_path, cache_dir=cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    return {
        "schema": STT_LATTICE_ARTIFACT_SCHEMA,
        "enabled": True,
        "path": str(path),
        "segment_count": artifact["segment_count"],
        "summary": artifact["summary"],
    }


def select_stt_lattice_text(
    segment: dict[str, Any],
    settings: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Use all STT candidates as a word lattice and replace only confidently better words."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("stt_lattice_selector_enabled"), True):
        return None, {"schema": STT_LATTICE_SCHEMA, "model": STT_LATTICE_MODEL_ID, "enabled": False, "reason": "disabled"}
    if segment.get("stt_ensemble_primary_locked"):
        return None, {"schema": STT_LATTICE_SCHEMA, "model": STT_LATTICE_MODEL_ID, "enabled": False, "reason": "primary_locked"}

    candidates = _candidate_sources(segment)
    if len(candidates) < 2:
        return None, {"schema": STT_LATTICE_SCHEMA, "model": STT_LATTICE_MODEL_ID, "enabled": False, "reason": "not_enough_candidates"}
    if _safe_bool(settings.get("stt_lattice_require_word_timestamps"), True):
        real_word_candidates = [candidate for candidate in candidates if any(isinstance(word, dict) for word in list(candidate.get("words") or []))]
        if len(real_word_candidates) < 2:
            return None, {"schema": STT_LATTICE_SCHEMA, "model": STT_LATTICE_MODEL_ID, "enabled": False, "reason": "word_timestamps_missing"}

    base_text = _normalize(segment.get("text"))
    base = next((candidate for candidate in candidates if _compact(candidate.get("text")) == _compact(base_text)), candidates[0])
    base_words = _words_from_candidate(base)
    if not base_words:
        return None, {"schema": STT_LATTICE_SCHEMA, "model": STT_LATTICE_MODEL_ID, "enabled": False, "reason": "base_words_missing"}

    min_match_score = max(0.1, min(0.95, _safe_float(settings.get("stt_lattice_min_match_score"), 0.42)))
    replace_margin = max(0.0, min(0.75, _safe_float(settings.get("stt_lattice_replace_margin"), 0.14)))
    min_confidence = max(0.0, min(1.0, _safe_float(settings.get("stt_lattice_min_confidence"), 0.62)))
    used_by_source: dict[str, set[int]] = {}
    selected_words: list[dict[str, Any]] = []
    replacements = 0
    alternatives_examined = 0
    replacement_margins: list[float] = []

    base_source = str(base.get("source") or "CURRENT").upper()
    base_parent = _candidate_score_100(base) / 100.0
    for base_word in base_words:
        chosen = dict(base_word)
        chosen["stt_word_source"] = base_source
        base_word_score = (_word_confidence(base_word, 0.45) * 0.72) + (base_parent * 0.28)
        protected = _protected_word(_word_text(base_word))
        best_alt: tuple[float, dict[str, Any], str, float] | None = None

        for candidate in candidates:
            source = str(candidate.get("source") or "CURRENT").upper()
            if candidate is base:
                continue
            words = _words_from_candidate(candidate)
            used = used_by_source.setdefault(source, set())
            match_idx, match_score = _find_match(base_word, words, used, min_match_score)
            if match_idx is None:
                continue
            alt_word = words[match_idx]
            alt_text = _word_text(alt_word)
            if not alt_text:
                continue
            alternatives_examined += 1
            word_similarity = _similarity(_word_text(base_word), alt_text)
            if word_similarity >= 0.98:
                continue
            alt_parent = _candidate_score_100(candidate) / 100.0
            alt_score = (_word_confidence(alt_word, 0.45) * 0.72) + (alt_parent * 0.28)
            if protected and word_similarity < 0.72:
                continue
            margin = alt_score - base_word_score
            if margin >= replace_margin and (best_alt is None or alt_score > best_alt[0]):
                best_alt = (alt_score, alt_word, source, match_score)

        if best_alt is not None:
            alt_score, alt_word, source, match_score = best_alt
            chosen = dict(alt_word)
            chosen["stt_word_source"] = source
            chosen["stt_word_replaced_from"] = _word_text(base_word)
            chosen["stt_lattice_match_score"] = round(match_score, 4)
            replacements += 1
            replacement_margins.append(round(alt_score - base_word_score, 4))
        selected_words.append(chosen)

    selected_text = _normalize(" ".join(_word_text(word) for word in selected_words if _word_text(word)))
    avg_margin = sum(replacement_margins) / max(1, len(replacement_margins))
    lora_score = _safe_float(dict(profile or {}).get("top_score"), 0.0) / 100.0
    confidence = min(0.98, 0.42 + min(0.32, avg_margin) + min(0.16, replacements / max(1, len(base_words))) + min(0.08, lora_score * 0.08))
    accepted = replacements > 0 and selected_text and selected_text != base_text and confidence >= min_confidence
    meta = {
        "schema": STT_LATTICE_SCHEMA,
        "model": STT_LATTICE_MODEL_ID,
        "enabled": True,
        "accepted": bool(accepted),
        "base_source": base_source,
        "candidate_count": len(candidates),
        "base_word_count": len(base_words),
        "alternatives_examined": alternatives_examined,
        "replacements": replacements,
        "confidence": round(confidence, 4),
        "min_confidence": round(min_confidence, 4),
        "replace_margin": round(replace_margin, 4),
        "replacement_margins": replacement_margins[:12],
        "candidate_roles": {
            role: sum(1 for candidate in candidates if str(candidate.get("candidate_role") or "") == role)
            for role in sorted({str(candidate.get("candidate_role") or "") for candidate in candidates})
            if role
        },
        "source_counts": {
            source: sum(1 for candidate in candidates if str(candidate.get("source") or "").upper() == source)
            for source in sorted({str(candidate.get("source") or "").upper() for candidate in candidates})
            if source
        },
    }
    if not accepted:
        meta["reason"] = "no_confident_replacement" if replacements == 0 else "confidence_below_threshold"
        return None, meta
    return {
        "text": selected_text,
        "words": selected_words,
        "source": "LATTICE",
        "label": "L",
        "selector": STT_LATTICE_MODEL_ID,
        "score": round(confidence, 4),
        "margin": round(avg_margin, 4),
        "_stt_lattice_policy": meta,
    }, meta


__all__ = [
    "STT_LATTICE_ARTIFACT_SCHEMA",
    "STT_LATTICE_CANDIDATE_KEYS",
    "STT_LATTICE_MODEL_ID",
    "STT_LATTICE_SCHEMA",
    "build_stt_lattice_artifact",
    "collect_stt_lattice_candidates",
    "persist_stt_lattice_artifact",
    "select_stt_lattice_text",
    "stt_lattice_artifact_path",
]
