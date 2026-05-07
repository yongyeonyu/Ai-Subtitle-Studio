from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_store_common import read_json, read_jsonl, store_paths, write_json


SUBTITLE_PATTERN_INDEX_SCHEMA = "ai_subtitle_studio.subtitle_pattern_index.v1"
SUBTITLE_PATTERN_MODEL_ID = "compact_timing_pattern_index_v1"

_SETTING_KEYS = (
    "split_length_threshold",
    "subtitle_target_line_count",
    "sub_min_duration",
    "sub_max_duration",
    "sub_max_cps",
    "sub_gap_break_sec",
    "word_timing_gap_break_sec",
    "continuous_threshold",
    "gap_push_rate",
    "gap_pull_rate",
    "single_subtitle_end",
    "deep_timing_max_shift_sec",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    return max(float(low), min(float(high), _safe_float(value, default)))


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    return max(int(low), min(int(high), _safe_int(value, default)))


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _compact_len(value: Any) -> int:
    return len("".join(str(value or "").split()))


def _line_count_from_text(value: Any) -> int:
    lines = [line.strip() for line in str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return max(1, len([line for line in lines if line])) if _clean_text(value) else 0


def _bucket(value: float, edges: tuple[float, ...], labels: tuple[str, ...]) -> str:
    number = float(value or 0.0)
    for edge, label in zip(edges, labels):
        if number <= edge:
            return label
    return labels[-1]


def _char_bucket(chars: int) -> str:
    return _bucket(float(chars), (8, 14, 24, 36), ("xs", "s", "m", "l", "xl"))


def _duration_bucket(duration: float) -> str:
    return _bucket(float(duration), (0.8, 1.6, 2.8, 4.5), ("blink", "short", "normal", "long", "very_long"))


def _cps_bucket(cps: float) -> str:
    return _bucket(float(cps), (7, 11, 15, 20), ("slow", "normal", "dense", "fast", "very_fast"))


def _gap_bucket(gap: Any) -> str:
    if gap is None:
        return "unknown"
    return _bucket(_safe_float(gap), (0.12, 0.35, 0.8, 1.5), ("none", "tight", "short", "natural", "long"))


def _source_signature(paths: dict[str, Path]) -> dict[str, Any]:
    signature: dict[str, Any] = {"schema": SUBTITLE_PATTERN_INDEX_SCHEMA, "sources": {}}
    for key in ("truth_table", "text_lora_dataset", "text_lora_corpus", "multimodal_lora_context", "deep_policy_events"):
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


def subtitle_pattern_index_is_current(index: dict[str, Any], paths: dict[str, Path]) -> bool:
    if not isinstance(index, dict):
        return False
    if str(index.get("schema") or "") != SUBTITLE_PATTERN_INDEX_SCHEMA:
        return False
    if str(index.get("model") or "") != SUBTITLE_PATTERN_MODEL_ID:
        return False
    return dict(index.get("source_signature") or {}) == _source_signature(paths)


def _style_profile_from_row(row: dict[str, Any]) -> dict[str, Any]:
    profile = row.get("style_profile") or row.get("subtitle_style_profile")
    if isinstance(profile, dict):
        return profile
    extra = row.get("extra")
    if isinstance(extra, dict):
        profile = extra.get("style_profile") or extra.get("subtitle_style_profile")
        if isinstance(profile, dict):
            return profile
    meta = row.get("meta") or row.get("metadata")
    if isinstance(meta, dict):
        profile = meta.get("style_profile") or meta.get("subtitle_style_profile")
        if isinstance(profile, dict):
            return profile
    generation = row.get("generation_context")
    if isinstance(generation, dict):
        profile = generation.get("style_profile") or generation.get("subtitle_style_profile")
        if isinstance(profile, dict):
            return profile
    return {}


def _pattern_features_from_style(style: dict[str, Any]) -> dict[str, Any]:
    line = dict(style.get("line_break") or {})
    timing = dict(style.get("timing_padding") or {})
    line_lengths = [int(_safe_int(item, 0)) for item in list(line.get("line_lengths") or []) if _safe_int(item, 0) > 0]
    char_count = sum(line_lengths)
    return {
        "line_count": _clamp_int(line.get("line_count"), 1, 3, 1) if line else 0,
        "line_lengths": line_lengths,
        "max_line_chars": max(line_lengths) if line_lengths else _safe_int(line.get("max_line_chars"), 0),
        "duration_sec": _safe_float(timing.get("duration_sec"), 0.0),
        "cps": _safe_float(timing.get("cps"), 0.0),
        "previous_gap_sec": timing.get("previous_gap_sec"),
        "next_gap_sec": timing.get("next_gap_sec"),
        "char_count": char_count,
    }


def _features_from_row(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    style = _style_profile_from_row(row)
    style_features = _pattern_features_from_style(style)
    if kind == "truth_table":
        text = _clean_text(row.get("speech_training_text") or row.get("raw_ground_truth_text"))
        duration = _safe_float(row.get("duration_sec"), style_features.get("duration_sec", 0.0))
        chars = _safe_int(row.get("char_count"), style_features.get("char_count", 0) or _compact_len(text))
        cps = _safe_float(row.get("cps"), style_features.get("cps", chars / duration if duration > 0 else 0.0))
    elif kind in {"text_lora_dataset", "text_lora_corpus"}:
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        text = _clean_text(row.get("output") or row.get("final_subtitle_text") or row.get("input"))
        duration = _safe_float(meta.get("duration_sec"), style_features.get("duration_sec", 0.0))
        chars = style_features.get("char_count") or _compact_len(text)
        cps = style_features.get("cps") or (chars / duration if duration > 0 else 0.0)
    elif kind == "multimodal_lora_context":
        text = _clean_text(row.get("final_subtitle_text") or row.get("input_text"))
        duration = _safe_float(row.get("duration_sec"), style_features.get("duration_sec", 0.0))
        chars = style_features.get("char_count") or _compact_len(text)
        cps = style_features.get("cps") or (chars / duration if duration > 0 else 0.0)
    elif kind == "deep_policy_events":
        features = row.get("features") if isinstance(row.get("features"), dict) else {}
        duration = _safe_float(features.get("duration_sec"), 0.0)
        chars = _safe_int(features.get("char_count"), _compact_len(row.get("text")))
        cps = _safe_float(features.get("cps"), chars / duration if duration > 0 else 0.0)
        text = _clean_text(row.get("text"))
    else:
        return {}

    line_count = _safe_int(style_features.get("line_count"), _line_count_from_text(text))
    line_lengths = list(style_features.get("line_lengths") or [])
    max_line_chars = _safe_int(style_features.get("max_line_chars"), max(line_lengths) if line_lengths else chars)
    return {
        "char_count": int(max(0, chars)),
        "duration_sec": round(max(0.0, duration), 3),
        "cps": round(max(0.0, cps), 3),
        "line_count": _clamp_int(line_count, 1, 3, 1) if chars else 0,
        "max_line_chars": int(max(0, max_line_chars)),
        "previous_gap_sec": style_features.get("previous_gap_sec"),
        "next_gap_sec": style_features.get("next_gap_sec"),
    }


def _pattern_key(features: dict[str, Any], *, include_gaps: bool = True) -> str:
    chars = _safe_int(features.get("char_count"), 0)
    duration = _safe_float(features.get("duration_sec"), 0.0)
    cps = _safe_float(features.get("cps"), 0.0)
    lines = _clamp_int(features.get("line_count"), 1, 3, 1) if chars else 0
    parts = [
        f"chars:{_char_bucket(chars)}",
        f"dur:{_duration_bucket(duration)}",
        f"cps:{_cps_bucket(cps)}",
        f"lines:{lines}",
    ]
    if include_gaps:
        parts.append(f"prev:{_gap_bucket(features.get('previous_gap_sec'))}")
        parts.append(f"next:{_gap_bucket(features.get('next_gap_sec'))}")
    return "|".join(parts)


def _lookup_keys(features: dict[str, Any]) -> list[str]:
    chars = _safe_int(features.get("char_count"), 0)
    duration = _safe_float(features.get("duration_sec"), 0.0)
    cps = _safe_float(features.get("cps"), 0.0)
    lines = _clamp_int(features.get("line_count"), 1, 3, 1) if chars else 0
    keys = [
        _pattern_key(features, include_gaps=True),
        _pattern_key(features, include_gaps=False),
        f"chars:{_char_bucket(chars)}|lines:{lines}",
        f"dur:{_duration_bucket(duration)}|cps:{_cps_bucket(cps)}",
        "global",
    ]
    out: list[str] = []
    for key in keys:
        if key not in out:
            out.append(key)
    return out


def _settings_from_row(kind: str, row: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for source_key in ("settings_snapshot", "applied_settings", "retrieved_settings"):
        source = row.get(source_key)
        if isinstance(source, dict):
            settings.update({key: source.get(key) for key in _SETTING_KEYS if source.get(key) not in (None, "")})
    if kind == "deep_policy_events":
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
        applied = profile.get("applied_settings") if isinstance(profile.get("applied_settings"), dict) else {}
        settings.update({key: applied.get(key) for key in _SETTING_KEYS if applied.get(key) not in (None, "")})

    chars = _safe_int(features.get("char_count"), 0)
    max_line_chars = _safe_int(features.get("max_line_chars"), chars)
    duration = _safe_float(features.get("duration_sec"), 0.0)
    cps = _safe_float(features.get("cps"), 0.0)
    line_count = _clamp_int(features.get("line_count"), 1, 3, 1) if chars else 1
    prev_gap = features.get("previous_gap_sec")
    next_gap = features.get("next_gap_sec")
    known_gaps = [_safe_float(gap) for gap in (prev_gap, next_gap) if gap not in (None, "")]
    short_gap_values = [gap for gap in known_gaps if 0.0 <= gap <= 1.5]
    observed_short_gap = max(short_gap_values) if short_gap_values else 0.0
    long_silence_threshold = max(1.45, min(3.0, observed_short_gap + 0.45 if observed_short_gap else 1.65))

    settings.setdefault("split_length_threshold", _clamp_int(max_line_chars or chars or 16, 8, 36, 16))
    settings.setdefault("subtitle_target_line_count", _clamp_int(line_count, 1, 3, 1))
    if duration > 0.0:
        settings.setdefault("sub_min_duration", round(_clamp(min(duration, 0.6), 0.12, 1.2, 0.3), 3))
        settings.setdefault("sub_max_duration", round(_clamp(max(2.0, duration * 1.7), 2.0, 8.0, 6.0), 3))
    if cps > 0.0:
        settings.setdefault("sub_max_cps", _clamp_int(max(10, cps + 2.0), 10, 24, 14))

    # Netflix-like subtitles usually bridge short pauses. Only longer silence should
    # become a real subtitle gap, and the following subtitle should be pulled earlier.
    settings.setdefault("sub_gap_break_sec", round(_clamp(long_silence_threshold, 0.8, 3.2, 1.65), 3))
    settings.setdefault("word_timing_gap_break_sec", round(_clamp(long_silence_threshold * 0.72, 0.75, 2.4, 1.05), 3))
    settings.setdefault("continuous_threshold", round(_clamp(long_silence_threshold * 1.45, 1.6, 4.0, 2.4), 3))
    settings.setdefault("gap_push_rate", 0.68)
    settings.setdefault("gap_pull_rate", 0.32)
    settings.setdefault("single_subtitle_end", 0.24)
    settings.setdefault("deep_timing_max_shift_sec", 0.1)
    return {
        key: value
        for key, value in settings.items()
        if key in _SETTING_KEYS and value not in (None, "")
    }


def _quality_for_kind(kind: str) -> float:
    return {
        "truth_table": 1.0,
        "text_lora_corpus": 0.82,
        "text_lora_dataset": 0.72,
        "multimodal_lora_context": 0.68,
        "deep_policy_events": 0.62,
    }.get(kind, 0.5)


def _add_sample(bucket: dict[str, Any], kind: str, features: dict[str, Any], settings: dict[str, Any]) -> None:
    weight = _quality_for_kind(kind)
    bucket["count"] = int(bucket.get("count", 0) or 0) + 1
    bucket["weight"] = round(_safe_float(bucket.get("weight"), 0.0) + weight, 6)
    bucket.setdefault("source_counts", {})
    bucket["source_counts"][kind] = int(bucket["source_counts"].get(kind, 0) or 0) + 1
    bucket.setdefault("_feature_values", defaultdict(list))
    bucket.setdefault("_setting_values", defaultdict(list))
    for key in ("char_count", "duration_sec", "cps", "line_count", "max_line_chars"):
        value = features.get(key)
        if value not in (None, ""):
            bucket["_feature_values"][key].append((float(value), weight))
    for key, value in settings.items():
        try:
            bucket["_setting_values"][key].append((float(value), weight))
        except Exception:
            pass


def _weighted_median(values: list[tuple[float, float]], default: float = 0.0) -> float:
    if not values:
        return float(default)
    expanded: list[float] = []
    for value, weight in values:
        repeats = max(1, int(round(float(weight) * 4)))
        expanded.extend([float(value)] * repeats)
    return float(median(expanded)) if expanded else float(default)


def _finalize_bucket(key: str, bucket: dict[str, Any]) -> dict[str, Any]:
    feature_values = dict(bucket.pop("_feature_values", {}) or {})
    setting_values = dict(bucket.pop("_setting_values", {}) or {})
    features = {
        name: round(_weighted_median(list(values or [])), 3)
        for name, values in feature_values.items()
        if values
    }
    settings: dict[str, Any] = {}
    for name, values in setting_values.items():
        value = _weighted_median(list(values or []))
        if name == "split_length_threshold":
            settings[name] = _clamp_int(value, 6, 40, int(round(value)))
        elif name == "subtitle_target_line_count":
            settings[name] = _clamp_int(value, 1, 3, int(round(value)))
        elif name == "sub_max_cps":
            settings[name] = _clamp_int(value, 6, 24, int(round(value)))
        elif name in {"gap_push_rate", "gap_pull_rate"}:
            settings[name] = round(_clamp(value, 0.0, 1.0, 0.5), 3)
        elif name == "single_subtitle_end":
            settings[name] = round(_clamp(value, 0.0, 1.2, 0.24), 3)
        else:
            settings[name] = round(_clamp(value, 0.05, 12.0, value), 3)
    count = int(bucket.get("count", 0) or 0)
    weight = _safe_float(bucket.get("weight"), 0.0)
    score = min(100.0, 42.0 + min(38.0, weight * 6.0) + min(20.0, count * 1.5))
    return {
        "key": key,
        "count": count,
        "weight": round(weight, 4),
        "score": round(score, 4),
        "source_counts": dict(sorted(dict(bucket.get("source_counts") or {}).items())),
        "features": features,
        "settings": settings,
    }


def _iter_pattern_rows(paths: dict[str, Path]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for kind in ("truth_table", "text_lora_dataset", "text_lora_corpus", "multimodal_lora_context", "deep_policy_events"):
        rows.extend((kind, dict(row)) for row in read_jsonl(paths[kind]) if isinstance(row, dict))
    return rows


def build_subtitle_pattern_index_payload(paths: dict[str, Path]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = defaultdict(dict)
    source_counts: dict[str, int] = defaultdict(int)
    accepted_rows = 0
    for kind, row in _iter_pattern_rows(paths):
        features = _features_from_row(kind, row)
        if not features or _safe_int(features.get("char_count"), 0) <= 0:
            continue
        settings = _settings_from_row(kind, row, features)
        if not settings:
            continue
        accepted_rows += 1
        source_counts[kind] += 1
        full_key = _pattern_key(features, include_gaps=True)
        compact_key = _pattern_key(features, include_gaps=False)
        _add_sample(buckets[full_key], kind, features, settings)
        _add_sample(buckets[compact_key], kind, features, settings)
        _add_sample(
            buckets[f"chars:{_char_bucket(_safe_int(features.get('char_count'), 0))}|lines:{_clamp_int(features.get('line_count'), 1, 3, 1)}"],
            kind,
            features,
            settings,
        )
        _add_sample(
            buckets[
                f"dur:{_duration_bucket(_safe_float(features.get('duration_sec'), 0.0))}|"
                f"cps:{_cps_bucket(_safe_float(features.get('cps'), 0.0))}"
            ],
            kind,
            features,
            settings,
        )
        _add_sample(buckets["global"], kind, features, settings)

    patterns = {
        key: _finalize_bucket(key, dict(bucket))
        for key, bucket in sorted(buckets.items())
        if int(bucket.get("count", 0) or 0) > 0
    }
    return {
        "schema": SUBTITLE_PATTERN_INDEX_SCHEMA,
        "model": SUBTITLE_PATTERN_MODEL_ID,
        "updated_at": iso_now(),
        "source_signature": _source_signature(paths),
        "source_counts": dict(sorted(source_counts.items())),
        "accepted_rows": int(accepted_rows),
        "pattern_count": len(patterns),
        "patterns": patterns,
        "notes": [
            "Stores compact subtitle timing/style patterns instead of full original text.",
            "Runtime matching is key-based and prefers subtitle continuity across short silence.",
        ],
    }


def save_subtitle_pattern_index(store_dir: str | Path | None = None, *, force: bool = False) -> dict[str, Any]:
    paths = store_paths(store_dir)
    path = paths["subtitle_pattern_index"]
    current = read_json(path, {})
    if not force and subtitle_pattern_index_is_current(current, paths):
        return current
    payload = build_subtitle_pattern_index_payload(paths)
    write_json(path, payload)
    return payload


def load_subtitle_pattern_index(
    store_dir: str | Path | None = None,
    *,
    rebuild_if_missing: bool = True,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    path = paths["subtitle_pattern_index"]
    payload = read_json(path, {})
    if payload and subtitle_pattern_index_is_current(payload, paths):
        return payload
    if not rebuild_if_missing:
        return payload if isinstance(payload, dict) else {}
    return save_subtitle_pattern_index(store_dir, force=True)


def segment_pattern_features(segment: dict[str, Any]) -> dict[str, Any]:
    start = _safe_float(segment.get("start"), 0.0)
    end = _safe_float(segment.get("end"), start)
    duration = max(0.0, end - start)
    text = _clean_text(segment.get("text"))
    chars = _compact_len(text)
    return {
        "char_count": chars,
        "duration_sec": round(duration, 3),
        "cps": round(chars / duration, 3) if chars and duration > 0 else 0.0,
        "line_count": _line_count_from_text(segment.get("text")) or 1,
        "max_line_chars": max([_compact_len(line) for line in str(segment.get("text") or "").splitlines()] or [chars]),
        "previous_gap_sec": segment.get("previous_gap_sec", segment.get("_previous_gap_sec")),
        "next_gap_sec": segment.get("next_gap_sec", segment.get("_next_gap_sec")),
    }


def match_subtitle_pattern(
    segment: dict[str, Any],
    settings: dict[str, Any] | None = None,
    *,
    store_dir: str | Path | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = settings.get("lora_pattern_index_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return {}
    payload = dict(index or load_subtitle_pattern_index(store_dir, rebuild_if_missing=bool(settings.get("lora_pattern_autobuild_enabled", True))))
    patterns = dict(payload.get("patterns") or {})
    if not patterns:
        return {}
    features = segment_pattern_features(segment)
    for key in _lookup_keys(features):
        row = dict(patterns.get(key) or {})
        if not row:
            continue
        pattern_settings = {
            name: value
            for name, value in dict(row.get("settings") or {}).items()
            if name in _SETTING_KEYS and value not in (None, "")
        }
        if not pattern_settings:
            continue
        score = _safe_float(row.get("score"), 0.0)
        return {
            "schema": SUBTITLE_PATTERN_INDEX_SCHEMA,
            "model": SUBTITLE_PATTERN_MODEL_ID,
            "matched_key": key,
            "score": round(score, 4),
            "count": int(row.get("count", 0) or 0),
            "settings": pattern_settings,
            "features": features,
            "pattern_features": dict(row.get("features") or {}),
            "source_counts": dict(row.get("source_counts") or {}),
            "index_updated_at": payload.get("updated_at"),
            "index_id": stable_hash({"updated_at": payload.get("updated_at"), "pattern_count": payload.get("pattern_count")})[:12],
        }
    return {}


__all__ = [
    "SUBTITLE_PATTERN_INDEX_SCHEMA",
    "SUBTITLE_PATTERN_MODEL_ID",
    "build_subtitle_pattern_index_payload",
    "load_subtitle_pattern_index",
    "match_subtitle_pattern",
    "save_subtitle_pattern_index",
    "segment_pattern_features",
    "subtitle_pattern_index_is_current",
]
