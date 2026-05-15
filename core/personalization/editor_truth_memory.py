"""Immediate runtime memory for user-confirmed subtitle edits."""
from __future__ import annotations

import json
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from core.native_text_similarity import similarity_ratio
from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_storage import LORA_INTERNAL_CACHE_DIR
from core.runtime.json_utils import json_safe as _json_safe
from core.text_utils import clean_text as _clean_text, compact_text as _compact


EDITOR_TRUTH_PATTERN_SCHEMA = "ai_subtitle_studio.editor_truth_pattern.v1"
EDITOR_TRUTH_PATTERN_FILE = "editor_truth_patterns.jsonl"


def _cache_dir(store_dir: str | Path | None = None) -> Path:
    if store_dir is None:
        return Path(LORA_INTERNAL_CACHE_DIR)
    root = Path(store_dir)
    return root if root.name == ".cache" else root / ".cache"


def editor_truth_pattern_path(store_dir: str | Path | None = None) -> Path:
    return _cache_dir(store_dir) / EDITOR_TRUTH_PATTERN_FILE

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
    except Exception:
        return []
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _extra(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get("extra")
    merged = dict(extra) if isinstance(extra, dict) else {}
    for key in (
        "source_before_edit",
        "original_text",
        "dictated_text",
        "stt_candidate_snapshot",
        "trigger",
        "hard_case_reasons",
    ):
        if key in row and key not in merged:
            merged[key] = row.get(key)
    return merged


def _candidate_source_text(row: dict[str, Any]) -> str:
    extra = _extra(row)
    for key in ("source_before_edit", "original_text", "dictated_text"):
        text = _clean_text(extra.get(key))
        if text:
            return text
    snapshot = extra.get("stt_candidate_snapshot") if isinstance(extra.get("stt_candidate_snapshot"), dict) else {}
    selected = str(snapshot.get("selected_source") or snapshot.get("llm_selected_source") or snapshot.get("ensemble_source") or "").strip().upper()
    candidates = [item for item in list(snapshot.get("candidates") or []) if isinstance(item, dict)]
    if selected:
        for candidate in candidates:
            if str(candidate.get("source") or "").strip().upper() == selected:
                text = _clean_text(candidate.get("text"))
                if text:
                    return text
    for candidate in candidates:
        text = _clean_text(candidate.get("text"))
        if text:
            return text
    return ""


def _single_replacement(source: str, corrected: str) -> dict[str, Any]:
    source_clean = _clean_text(source)
    corrected_clean = _clean_text(corrected)
    if not source_clean or not corrected_clean or source_clean == corrected_clean:
        return {}
    matcher = SequenceMatcher(None, source_clean, corrected_clean)
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    if len(changes) != 1:
        return {}
    _tag, i1, i2, j1, j2 = changes[0]
    old = source_clean[i1:i2]
    new = corrected_clean[j1:j2]
    if not old or not old.strip() or old == new or len(old) > 48 or len(new) > 64:
        return {}
    return {"old": old, "new": new}


def build_editor_truth_patterns(rows: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        corrected = _clean_text(row.get("speech_training_text") or row.get("raw_ground_truth_text"))
        source = _candidate_source_text(row)
        if not source or not corrected or _clean_text(source) == _clean_text(corrected):
            continue
        replacement = _single_replacement(source, corrected)
        pattern_id = stable_hash(
            {
                "source": _compact(source),
                "corrected": _compact(corrected),
                "segment_id": str(row.get("segment_id") or ""),
            }
        )[:24]
        patterns.append(
            {
                "schema": EDITOR_TRUTH_PATTERN_SCHEMA,
                "pattern_id": pattern_id,
                "source_text": source,
                "corrected_text": corrected,
                "source_compact": _compact(source),
                "corrected_compact": _compact(corrected),
                "replacement": replacement,
                "media_id": str(row.get("media_id") or ""),
                "segment_id": str(row.get("segment_id") or ""),
                "captured_at": str(row.get("captured_at") or iso_now()),
                "extra": {
                    "trigger": _extra(row).get("trigger"),
                    "line_break_pattern": row.get("line_break_pattern"),
                    "punctuation_pattern": row.get("punctuation_pattern"),
                    "word_boundary_learning": row.get("word_boundary_learning"),
                    "hard_case_reasons": _extra(row).get("hard_case_reasons"),
                },
            }
        )
    return patterns


def append_editor_truth_patterns(
    rows: Iterable[dict[str, Any]] | None,
    store_dir: str | Path | None = None,
    *,
    max_rows: int = 500,
) -> dict[str, Any]:
    patterns = build_editor_truth_patterns(rows)
    path = editor_truth_pattern_path(store_dir)
    existing = _read_jsonl(path)
    by_id = {
        str(row.get("pattern_id") or ""): dict(row)
        for row in existing
        if str(row.get("pattern_id") or "")
    }
    appended = 0
    for pattern in patterns:
        pid = str(pattern.get("pattern_id") or "")
        if not pid:
            continue
        if pid not in by_id:
            appended += 1
        by_id[pid] = _json_safe(pattern)
    merged = list(by_id.values())[-max(1, int(max_rows or 500)) :]
    _write_jsonl(path, merged)
    return {
        "schema": EDITOR_TRUTH_PATTERN_SCHEMA,
        "path": str(path),
        "input_patterns": len(patterns),
        "appended_patterns": appended,
        "total_patterns": len(merged),
    }


def load_editor_truth_patterns(
    store_dir: str | Path | None = None,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    rows = _read_jsonl(editor_truth_pattern_path(store_dir))
    return rows[-max(1, int(limit or 200)) :]


def apply_recent_editor_truth_patterns(
    text: str,
    settings: dict[str, Any] | None = None,
    *,
    store_dir: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    settings = dict(settings or {})
    enabled = settings.get("editor_truth_runtime_apply_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return str(text or ""), {}
    source_text = _clean_text(text)
    source_compact = _compact(source_text)
    if not source_compact:
        return source_text, {}
    min_similarity = max(0.5, min(1.0, float(settings.get("editor_truth_runtime_min_similarity", 0.94) or 0.94)))
    patterns = load_editor_truth_patterns(store_dir, limit=int(settings.get("editor_truth_runtime_pattern_limit", 200) or 200))
    for pattern in reversed(patterns):
        pattern_source = _clean_text(pattern.get("source_text"))
        pattern_corrected = _clean_text(pattern.get("corrected_text"))
        if not pattern_source or not pattern_corrected:
            continue
        pattern_compact = str(pattern.get("source_compact") or _compact(pattern_source))
        if pattern_compact and pattern_compact == source_compact:
            return pattern_corrected, {
                "schema": EDITOR_TRUTH_PATTERN_SCHEMA,
                "task": "editor_truth_runtime_apply",
                "applied": True,
                "reason": "exact_source_match",
                "pattern_id": str(pattern.get("pattern_id") or ""),
                "similarity": 1.0,
            }
        replacement = pattern.get("replacement") if isinstance(pattern.get("replacement"), dict) else {}
        old = str(replacement.get("old") or "")
        new = str(replacement.get("new") or "")
        if old and old in source_text and old != new:
            updated = source_text.replace(old, new, 1)
            if updated != source_text:
                similarity = similarity_ratio(_compact(pattern_source), source_compact)
                return updated, {
                    "schema": EDITOR_TRUTH_PATTERN_SCHEMA,
                    "task": "editor_truth_runtime_apply",
                    "applied": True,
                    "reason": "replacement_pattern",
                    "pattern_id": str(pattern.get("pattern_id") or ""),
                    "old": old,
                    "new": new,
                    "similarity": round(similarity, 4),
                }
        similarity = similarity_ratio(pattern_compact, source_compact) if pattern_compact else 0.0
        length_delta = abs(len(pattern_compact) - len(source_compact)) / max(1, len(pattern_compact))
        if similarity >= min_similarity and length_delta <= 0.12:
            return pattern_corrected, {
                "schema": EDITOR_TRUTH_PATTERN_SCHEMA,
                "task": "editor_truth_runtime_apply",
                "applied": True,
                "reason": "high_similarity_match",
                "pattern_id": str(pattern.get("pattern_id") or ""),
                "similarity": round(similarity, 4),
                "length_delta_ratio": round(length_delta, 4),
            }
    return source_text, {}


__all__ = [
    "EDITOR_TRUTH_PATTERN_FILE",
    "EDITOR_TRUTH_PATTERN_SCHEMA",
    "append_editor_truth_patterns",
    "apply_recent_editor_truth_patterns",
    "build_editor_truth_patterns",
    "editor_truth_pattern_path",
    "load_editor_truth_patterns",
]
