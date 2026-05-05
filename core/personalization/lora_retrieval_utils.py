from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.lora_context_classifier import classify_lora_context
from core.personalization.lora_retrieval_config import LORA_RETRIEVAL_HASH_DIM


def norm_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().casefold()


def path_leaf_terms(path: Any) -> str:
    text = str(path or "").replace("\\", "/")
    leaf = Path(text).name if text else ""
    stem = Path(leaf).stem if leaf else ""
    return " ".join(part for part in re.split(r"[\s._\-/]+", f"{leaf} {stem}") if part)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def parse_iso_seconds(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def strip_editorial_brackets(text: Any) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    open_to_close = {"(": ")", "[": "]", "{": "}", "（": "）", "【": "】"}
    close_to_open = {value: key for key, value in open_to_close.items()}
    kept: list[str] = []
    stack: list[tuple[str, list[str]]] = []
    for char in raw:
        if char in open_to_close:
            stack.append((open_to_close[char], []))
            continue
        if stack:
            expected, buf = stack[-1]
            if char == expected:
                stack.pop()
                continue
            buf.append(char)
            stack[-1] = (expected, buf)
            continue
        kept.append(char)
    for expected, buf in stack:
        kept.append(close_to_open.get(expected, "("))
        kept.extend(buf)
    return norm_text("".join(kept))


def json_preview(value: Any, *, max_depth: int = 4, max_items: int = 16, max_chars: int = 700) -> Any:
    if max_depth <= 0:
        return norm_text(value)[:max_chars]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return norm_text(value)[:max_chars]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:max_items]:
            out[str(key)] = json_preview(item, max_depth=max_depth - 1, max_items=max_items, max_chars=max_chars)
        return out
    if isinstance(value, (list, tuple, set)):
        return [
            json_preview(item, max_depth=max_depth - 1, max_items=max_items, max_chars=max_chars)
            for item in list(value)[:max_items]
        ]
    return norm_text(value)[:max_chars]


def flatten_search_text(value: Any, *, max_depth: int = 5, max_items: int = 32) -> list[str]:
    if max_depth <= 0:
        return []
    if value is None or value == "":
        return []
    if isinstance(value, (str, int, float, bool)):
        text = norm_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in list(value.items())[:max_items]:
            parts.append(str(key))
            parts.extend(flatten_search_text(item, max_depth=max_depth - 1, max_items=max_items))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in list(value)[:max_items]:
            parts.extend(flatten_search_text(item, max_depth=max_depth - 1, max_items=max_items))
        return parts
    text = norm_text(value)
    return [text] if text else []


def classification_summary(classification: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(classification or {})
    scene = dict(data.get("scene_environment") or {})
    mic = dict(data.get("microphone_environment") or {})
    topic = dict(data.get("topic") or {})
    return {
        "scene": str(scene.get("label") or ""),
        "topic": str(topic.get("primary") or ""),
        "mic_type": str(mic.get("mic_type") or ""),
        "noise_level": str(mic.get("noise_level") or ""),
        "noise_sources": [str(item) for item in list(mic.get("noise_sources") or []) if str(item or "").strip()],
        "training_focus": [str(item) for item in list(data.get("training_focus") or []) if str(item or "").strip()],
    }


def _bucket(token: str) -> str:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest()
    return str(int(digest, 16) % LORA_RETRIEVAL_HASH_DIM)


def term_hash(token: str) -> str:
    return hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest()


def tokenize_lora_text(text: Any) -> list[str]:
    normalized = norm_text(text).casefold()
    if not normalized:
        return []
    raw_tokens = re.findall(r"[0-9a-z_]+|[가-힣]+", normalized)
    tokens: list[str] = []
    for token in raw_tokens:
        if not token:
            continue
        tokens.append(token)
        if len(token) >= 2 and re.search(r"[가-힣]", token):
            tokens.extend(f"ko2:{token[idx:idx + 2]}" for idx in range(max(0, len(token) - 1)))
        if len(token) >= 3:
            tokens.extend(f"tri:{token[idx:idx + 3]}" for idx in range(max(0, len(token) - 2)))
    return tokens


def term_counts(text: Any) -> Counter[str]:
    return Counter(term_hash(token) for token in tokenize_lora_text(text))


def vectorize_lora_text(text: Any) -> dict[str, float]:
    tokens = tokenize_lora_text(text)
    if not tokens:
        return {}
    counts = Counter(_bucket(token) for token in tokens)
    weighted = {bucket: 1.0 + math.log(float(count)) for bucket, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in weighted.values()))
    if norm <= 0.0:
        return {}
    return {bucket: round(value / norm, 6) for bucket, value in weighted.items()}


def facet_label(value: Any) -> str:
    text = str(value or "").strip()
    if text.casefold() in {"", "-", "none", "null", "unknown"}:
        return ""
    return text


def facet_list(value: Any, *, limit: int = 12) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = facet_label(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def facets_from_classification(classification: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(classification or {})
    summary = classification_summary(data)
    facets = {
        "scene": facet_label(summary.get("scene")),
        "topic": facet_label(summary.get("topic")),
        "mic_type": facet_label(summary.get("mic_type")),
        "noise_level": facet_label(summary.get("noise_level")),
        "noise_sources": facet_list(summary.get("noise_sources") or []),
        "training_focus": facet_list(summary.get("training_focus") or []),
        "topic_terms": facet_list(data.get("topic_terms") or []),
    }
    return {key: value for key, value in facets.items() if value not in ("", [], {})}


def infer_facets_from_text(
    text: Any,
    *,
    media_path: str = "",
    row: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = dict(row or {})
    context = dict(context or {})
    audio_profile = dict(row.get("audio_profile") or row.get("features") or context.get("audio_profile") or {})
    media_profile = dict(row.get("media_profile") or context.get("media_profile") or {})
    subtitle_profile = dict(row.get("subtitle_profile") or context.get("subtitle_profile") or {})
    try:
        classification = classify_lora_context(
            media_profile=media_profile,
            subtitle_profile=subtitle_profile,
            texts=[text],
            file_hints=[media_path, row.get("subtitle_path") or ""],
            audio_profile=audio_profile,
            generation_context=context,
        )
    except Exception:
        return {}
    return facets_from_classification(classification)


def doc_facets(kind: str, row: dict[str, Any], payload: dict[str, Any], text: str) -> dict[str, Any]:
    classification = row.get("context_classification") or payload.get("context_classification")
    facets = facets_from_classification(classification if isinstance(classification, dict) else {})
    metrics = dict(row.get("metrics") or {})
    if metrics:
        facets.setdefault("scene", facet_label(metrics.get("scene_environment")))
        facets.setdefault("topic", facet_label(metrics.get("topic")))
        facets.setdefault("noise_level", facet_label(metrics.get("noise_level")))
    if not facets.get("scene") or not facets.get("topic"):
        inferred = infer_facets_from_text(text, media_path=str(row.get("media_path") or row.get("clip_path") or ""), row=row)
        for key, value in inferred.items():
            facets.setdefault(key, value)
    if kind == "excluded_parentheticals":
        facets["training_focus"] = facet_list(list(facets.get("training_focus") or []) + ["exclude_editorial_brackets"])
    return {key: value for key, value in facets.items() if value not in ("", [], {})}


def query_facets(
    query: str,
    *,
    media_path: str = "",
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    classification = context.get("context_classification")
    if not classification and str(context.get("schema") or "") == "ai_subtitle_studio.lora_context_classification.v1":
        classification = context
    facets = facets_from_classification(classification if isinstance(classification, dict) else {})
    inferred = infer_facets_from_text(
        query,
        media_path=media_path,
        row={},
        context={**context, "settings": dict(settings or {})},
    )
    for key, value in inferred.items():
        facets.setdefault(key, value)
    return {key: value for key, value in facets.items() if value not in ("", [], {})}


def query_text(
    text: Any,
    *,
    media_path: str = "",
    media_id: str = "",
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    settings = dict(settings or {})
    setting_terms = []
    for key in (
        "selected_audio_ai",
        "stt_quality_preset",
        "selected_model",
        "selected_llm_provider",
        "continuous_threshold",
        "gap_push_rate",
        "single_subtitle_end",
        "split_length_threshold",
        "sub_min_duration",
        "sub_max_duration",
        "sub_max_cps",
        "sub_dedup_window",
        "sub_gap_break_sec",
    ):
        value = settings.get(key)
        if value not in (None, ""):
            setting_terms.append(f"{key} {value}")
    return norm_text(
        " ".join(
            [
                strip_editorial_brackets(text),
                str(media_id or ""),
                str(media_path or ""),
                path_leaf_terms(media_path),
                " ".join(setting_terms),
                " ".join(flatten_search_text(context or {})),
            ]
        )
    )


def token_overlap_score(query: str, preview: str) -> float:
    query_tokens = set(tokenize_lora_text(query))
    preview_tokens = set(tokenize_lora_text(preview))
    if not query_tokens or not preview_tokens:
        return 0.0
    return len(query_tokens & preview_tokens) / max(1, len(query_tokens | preview_tokens))
