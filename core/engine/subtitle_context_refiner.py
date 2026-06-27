from __future__ import annotations

import json
import hashlib
import re
import time
from pathlib import Path
from typing import Any, Callable

from core.engine.llm_correction_guard import normalized_edit_distance
from core.runtime import config

CONTEXT_BOUNDARY_SCHEMA = "ai_subtitle_studio.subtitle_llm_context_boundary.v1"
KEEP_DECISION_CACHE_SCHEMA = "ai_subtitle_studio.high_context_keep_decision_cache.v1"
_KEEP_DECISION_CACHE_BY_PATH: dict[str, dict[str, Any]] = {}


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool = False) -> bool:
    value = dict(settings or {}).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _setting_int(settings: dict[str, Any] | None, key: str, default: int) -> int:
    try:
        value = dict(settings or {}).get(key, default)
        if value in (None, ""):
            value = default
        return int(value)
    except Exception:
        return int(default)


def _setting_float(settings: dict[str, Any] | None, key: str, default: float) -> float:
    try:
        value = dict(settings or {}).get(key, default)
        if value in (None, ""):
            value = default
        return float(value)
    except Exception:
        return float(default)


def _is_high_mode(settings: dict[str, Any] | None) -> bool:
    s = dict(settings or {})
    mode = str(s.get("subtitle_mode") or s.get("user_facing_mode") or s.get("mode") or "").strip().lower()
    return mode in {"high", "precise", "정밀"}


def _supports_context_refine_model(model: str) -> bool:
    label = str(model or "").strip().lower()
    if not label or "사용 안함" in label:
        return False
    # The existing macro LLM path already supports API/Codex/Gemini. This
    # timing-sensitive pair refiner stays on local Ollama models to avoid
    # blocking generation on external API latency or Codex CLI timeouts.
    if "openai" in label or "codex" in label or label.startswith("gpt-") or "gemini" in label:
        return False
    return True


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except Exception:
        if default is None:
            return None
        return float(default)


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _word_text(word: dict[str, Any]) -> str:
    return str(word.get("word") or word.get("text") or "").strip()


def _normal_word(text: Any) -> str:
    return re.sub(r"[^\w가-힣]", "", str(text or "")).strip().lower()


def _minimal_word_correction_allowed(old: str, new: str, settings: dict[str, Any]) -> bool:
    old_norm = _normal_word(old)
    new_norm = _normal_word(new)
    if not old_norm or not new_norm or old_norm == new_norm:
        return bool(old_norm and new_norm)
    if old_norm[0] != new_norm[0]:
        return False
    default_distance = 1 if len(old_norm) <= 3 else 2
    max_distance = max(1, _setting_int(settings, "subtitle_llm_context_max_correction_edit_distance", default_distance))
    max_distance = min(max_distance, 2)
    if abs(len(new_norm) - len(old_norm)) > max_distance:
        return False
    return normalized_edit_distance(old_norm, new_norm, limit=max_distance) <= max_distance


def _segment_words(seg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for word in list(seg.get("words") or []):
        if not isinstance(word, dict):
            continue
        text = _word_text(word)
        if not text:
            continue
        if word.get("start") in (None, "") or word.get("end") in (None, ""):
            continue
        start = _as_float(word.get("start"), None)
        end = _as_float(word.get("end"), None)
        if start is None or end is None or end <= start:
            continue
        item = dict(word)
        item["word"] = text
        item["start"] = float(start)
        item["end"] = float(end)
        rows.append(item)
    return sorted(rows, key=lambda row: (_as_float(row.get("start"), 0.0), _as_float(row.get("end"), 0.0)))


def _words_cover_text(words: list[dict[str, Any]], text: str, *, min_ratio: float = 0.72) -> bool:
    compact_text = _compact(text)
    if not compact_text:
        return False
    compact_words = _compact(_text_from_words(words))
    if not compact_words:
        return False
    if compact_words in compact_text or compact_text in compact_words:
        return True
    return len(compact_words) / max(1, len(compact_text)) >= min_ratio


def _same_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("_clip_idx", "clip_idx", "_clip_file", "clip_file", "source_video"):
        lv = left.get(key)
        rv = right.get(key)
        if lv not in (None, "") and rv not in (None, "") and lv != rv:
            return False
    left_cut = left.get("cut_scene_index")
    right_cut = right.get("cut_scene_index")
    if left_cut not in (None, "") and right_cut not in (None, "") and left_cut != right_cut:
        return False
    return True


def _terminal_text(text: str) -> bool:
    stripped = str(text or "").strip()
    return bool(stripped and stripped[-1] in ".!?…。？！~")


def _starts_continuation(text: str) -> bool:
    clean = _normal_word(text)
    return clean.startswith(
        (
            "그리고",
            "그래서",
            "근데",
            "그런데",
            "이렇게",
            "여기",
            "저기",
            "그러면",
            "일단",
            "근데요",
        )
    )


def _quality_label(seg: dict[str, Any]) -> str:
    quality = dict(seg.get("quality") or {})
    return str(quality.get("confidence_label") or seg.get("subtitle_confidence_label") or "").strip().lower()


def _has_uncertainty_signal(seg: dict[str, Any]) -> bool:
    bucket = str(seg.get("_uncertainty_bucket") or "").strip().lower()
    if bucket == "precision":
        return True
    policy = dict(seg.get("_uncertainty_policy") or {})
    bucket = str(policy.get("bucket") or "").strip().lower()
    return bucket == "precision"


def _pair_has_context_risk(left: dict[str, Any], right: dict[str, Any], settings: dict[str, Any]) -> bool:
    if not _setting_bool(settings, "subtitle_llm_context_require_risk_signal", True):
        return True
    if _is_micro_fragment(left, settings) or _is_micro_fragment(right, settings):
        return True
    if _quality_label(left) in {"yellow", "red"} or _quality_label(right) in {"yellow", "red"}:
        return True
    if _has_uncertainty_signal(left) or _has_uncertainty_signal(right):
        return True
    left_text = str(left.get("text", "") or "")
    right_text = str(right.get("text", "") or "")
    left_chars = len(_compact(left_text))
    right_chars = len(_compact(right_text))
    threshold = max(8, _setting_int(settings, "split_length_threshold", 20))
    if not _terminal_text(left_text) and _starts_continuation(right_text) and left_chars <= int(threshold * 0.85):
        return True
    if left_chars >= int(threshold * 1.2) and right_chars <= max(4, int(threshold * 0.35)):
        return True
    if _normal_word(left_text) and _normal_word(left_text) == _normal_word(right_text):
        return True
    return False


def _candidate_pair(left: dict[str, Any], right: dict[str, Any], settings: dict[str, Any]) -> bool:
    if left.get("is_gap") or right.get("is_gap"):
        return False
    if not _same_scope(left, right):
        return False
    left_text = str(left.get("text", "") or "").strip()
    right_text = str(right.get("text", "") or "").strip()
    if not left_text or not right_text:
        return False
    left_words = _segment_words(left)
    right_words = _segment_words(right)
    if not left_words or not right_words:
        return False
    if not _words_cover_text(left_words, left_text) or not _words_cover_text(right_words, right_text):
        return False
    gap = _as_float(right.get("start"), 0.0) - _as_float(left.get("end"), _as_float(right.get("start"), 0.0))
    max_gap = max(0.0, _setting_float(settings, "subtitle_llm_context_max_pair_gap_sec", 0.85))
    if gap > max_gap:
        return False
    combined_chars = len(_compact(left_text + right_text))
    min_chars = max(0, _setting_int(settings, "subtitle_llm_context_min_pair_chars", 6))
    max_chars = max(min_chars + 1, _setting_int(settings, "subtitle_llm_context_max_pair_chars", 58))
    if combined_chars < min_chars or combined_chars > max_chars:
        return False
    if not _pair_has_context_risk(left, right, settings):
        return False
    if not _terminal_text(left_text):
        return True
    if _starts_continuation(right_text):
        return True
    left_chars = len(_compact(left_text))
    target = max(8, _setting_int(settings, "split_length_threshold", 20))
    return left_chars < max(6, int(target * 0.45))


def _strip_json_fence(text: str) -> str:
    out = str(text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:json)?", "", out, flags=re.IGNORECASE).strip()
        out = re.sub(r"```$", "", out).strip()
    return out


def _parse_decision(raw: str) -> dict[str, Any] | None:
    text = _strip_json_fence(raw)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _vad_hints_for_pair(vad_segments: list[dict[str, Any]], start: float, end: float) -> list[dict[str, float]]:
    hints: list[dict[str, float]] = []
    for row in list(vad_segments or []):
        if not isinstance(row, dict):
            continue
        vad_start = _as_float(row.get("start"), None)
        vad_end = _as_float(row.get("end"), None)
        if vad_start is None or vad_end is None:
            continue
        if vad_end < start - 0.4 or vad_start > end + 0.4:
            continue
        hints.append({"start": round(float(vad_start), 3), "end": round(float(vad_end), 3)})
        if len(hints) >= 8:
            break
    return hints


def _build_pair_prompt(
    left: dict[str, Any],
    right: dict[str, Any],
    words: list[dict[str, Any]],
    vad_hints: list[dict[str, float]],
    settings: dict[str, Any],
    rules: dict[str, Any] | None,
) -> str:
    max_chars = _setting_int(settings, "split_length_threshold", 20)
    max_cps = _setting_float(settings, "sub_max_cps", 12.0)
    word_rows = [
        {
            "index": index,
            "word": _word_text(word),
            "start": round(_as_float(word.get("start"), 0.0), 3),
            "end": round(_as_float(word.get("end"), 0.0), 3),
        }
        for index, word in enumerate(words)
    ]
    end_words = list((rules or {}).get("end_words") or [])[:18]
    start_words = list((rules or {}).get("start_words") or [])[:18]
    payload = {
        "left": {
            "text": str(left.get("text", "") or ""),
            "start": round(_as_float(left.get("start"), 0.0), 3),
            "end": round(_as_float(left.get("end"), 0.0), 3),
        },
        "right": {
            "text": str(right.get("text", "") or ""),
            "start": round(_as_float(right.get("start"), 0.0), 3),
            "end": round(_as_float(right.get("end"), 0.0), 3),
        },
        "word_timestamps": word_rows,
        "vad_speech_hints": vad_hints,
        "style": {
            "target_max_chars_without_spaces": max_chars,
            "max_cps": max_cps,
            "natural_end_words": end_words,
            "natural_start_words": start_words,
        },
    }
    return (
        "당신은 한국어 자막 High 모드의 문맥 경계 검수기입니다.\n"
        "현재 자막과 다음 자막을 함께 보고, 문장이 어색하게 끊겼으면 정확한 STT 단어 timestamp 경계에서만 나누거나 합치세요.\n"
        "규칙:\n"
        "1. 새 단어를 만들거나 의미를 바꾸지 마세요.\n"
        "2. 경계를 옮길 때는 word_timestamps의 0-based index 뒤에서만 끊으세요.\n"
        "3. 불확실하면 keep을 선택하세요.\n"
        "4. merge는 한쪽 자막이 4글자 이하의 매우 짧은 조각일 때만 선택하세요. 보통은 keep 또는 move_boundary를 선택하세요.\n"
        "5. 문맥상 명백한 단어 오인식만 한 단어 단위로 corrections에 넣으세요. 예: 음요->음료.\n"
        "6. JSON만 반환하세요.\n"
        "반환 형식: "
        '{"action":"keep|move_boundary|merge","boundary_after_word_index":null,'
        '"corrections":[{"word_index":0,"from":"음요","to":"음료"}],"reason":"..."}\n'
        f"입력:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _default_llm_decision(
    left: dict[str, Any],
    right: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    from core.llm.ollama_provider import generate_text

    model = str(context.get("model") or "").strip()
    if not model or "사용 안함" in model:
        return None
    # The contextual boundary prompt is intentionally local-Ollama only for now.
    # API/Codex subtitle splitting remains handled by the existing macro LLM path.
    raw = generate_text(
        model,
        str(context.get("prompt") or ""),
        timeout=_setting_float(context.get("settings") or {}, "subtitle_llm_context_timeout_sec", 45.0),
        keep_alive=-1,
        num_predict=_setting_int(context.get("settings") or {}, "subtitle_llm_context_num_predict", 180),
        temperature=0.0,
        json_format=True,
        attempts=2,
    )
    return _parse_decision(raw or "")


def _valid_correction(item: Any, words: list[dict[str, Any]], settings: dict[str, Any]) -> tuple[int | None, str, str] | None:
    if not isinstance(item, dict):
        return None
    old = str(item.get("from") or item.get("source") or "").strip()
    new = str(item.get("to") or item.get("target") or "").strip()
    if not old or not new or old == new:
        return None
    if re.search(r"\s", old) or re.search(r"\s", new):
        return None
    if len(new) > _setting_int(settings, "subtitle_llm_context_max_correction_chars", 8):
        return None
    if abs(len(new) - len(old)) > _setting_int(settings, "subtitle_llm_context_max_correction_delta", 3):
        return None
    if not _minimal_word_correction_allowed(old, new, settings):
        return None
    idx: int | None = None
    try:
        raw_idx = item.get("word_index")
        if raw_idx not in (None, ""):
            idx = int(raw_idx)
    except Exception:
        idx = None
    if idx is not None and 0 <= idx < len(words):
        word_norm = _normal_word(_word_text(words[idx]))
        if word_norm == _normal_word(old) or _normal_word(old) in word_norm:
            return idx, old, new
        return None
    old_norm = _normal_word(old)
    matches = [index for index, word in enumerate(words) if _normal_word(_word_text(word)) == old_norm]
    if len(matches) == 1:
        return matches[0], old, new
    return None


def _apply_corrections(
    words: list[dict[str, Any]],
    decision: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not _setting_bool(settings, "subtitle_llm_context_word_correction_enabled", True):
        return [dict(word) for word in words], []
    corrected = [dict(word) for word in words]
    applied: list[dict[str, Any]] = []
    max_count = max(0, _setting_int(settings, "subtitle_llm_context_max_word_corrections", 2))
    for item in list(decision.get("corrections") or [])[:max_count]:
        valid = _valid_correction(item, corrected, settings)
        if not valid:
            continue
        idx, old, new = valid
        current = _word_text(corrected[idx])
        corrected[idx]["word"] = current.replace(old, new) if old in current else new
        corrected[idx]["text"] = corrected[idx]["word"]
        applied.append({"word_index": idx, "from": old, "to": new})
    return corrected, applied


def _text_from_words(words: list[dict[str, Any]]) -> str:
    return " ".join(_word_text(word) for word in words if _word_text(word)).strip()


def _drop_stale_timing_fields(row: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "timeline_start",
        "timeline_end",
        "timeline_start_frame",
        "timeline_end_frame",
        "start_frame",
        "end_frame",
        "frame_range",
        "_final_gap_settings_applied",
    ):
        row.pop(key, None)
    return row


def _is_micro_fragment(seg: dict[str, Any], settings: dict[str, Any]) -> bool:
    text_chars = len(_compact(seg.get("text", "")))
    start = _as_float(seg.get("start"), 0.0) or 0.0
    end = _as_float(seg.get("end"), start) or start
    duration = max(0.0, end - start)
    max_chars = max(1, _setting_int(settings, "subtitle_llm_context_merge_micro_max_chars", 4))
    max_duration = max(0.05, _setting_float(settings, "subtitle_llm_context_merge_micro_max_duration_sec", 0.55))
    return text_chars <= max_chars or duration <= max_duration


def _row_from_words(
    source: dict[str, Any],
    words: list[dict[str, Any]],
    policy: dict[str, Any],
    corrections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    clean_words = [dict(word) for word in words if _word_text(word)]
    if not clean_words:
        return None
    start = _as_float(clean_words[0].get("start"), _as_float(source.get("start"), 0.0))
    end = _as_float(clean_words[-1].get("end"), _as_float(source.get("end"), start + 0.05))
    if end <= start:
        end = start + 0.05
    row = dict(source)
    row.update(
        {
            "start": round(max(0.0, start), 3),
            "end": round(max(start + 0.05, end), 3),
            "text": _text_from_words(clean_words),
            "words": clean_words,
            "_llm_context_boundary_policy": dict(policy),
        }
    )
    if corrections:
        row["_llm_context_word_corrections"] = list(corrections)
    return _drop_stale_timing_fields(row)


def _decision_action(decision: dict[str, Any]) -> str:
    action = str(decision.get("action") or "keep").strip().lower()
    if action in {"move", "split", "move_boundary", "boundary"}:
        return "move_boundary"
    if action in {"merge", "combine"}:
        return "merge"
    return "keep"


def _requested_correction_count(decision: Any) -> int:
    if not isinstance(decision, dict):
        return 0
    return sum(1 for item in list(decision.get("corrections") or []) if isinstance(item, dict))


def _applied_correction_count(rows: list[dict[str, Any]]) -> int:
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for item in list(row.get("_llm_context_word_corrections") or []):
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("word_index") or ""),
                str(item.get("from") or ""),
                str(item.get("to") or ""),
            )
            if key[1] and key[2]:
                seen.add(key)
    return len(seen)


def _keep_cache_path(settings: dict[str, Any]) -> Path:
    override = str(settings.get("subtitle_llm_context_keep_cache_path") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(config.OUTPUT_DIR) / "high_context_boundary_cache" / "keep_decisions_v1.json"


def _keep_cache_key(*, model: str, prompt: str, settings: dict[str, Any]) -> str:
    payload = {
        "schema": KEEP_DECISION_CACHE_SCHEMA,
        "model": str(model or "").strip(),
        "prompt": str(prompt or ""),
        "word_correction_enabled": bool(_setting_bool(settings, "subtitle_llm_context_word_correction_enabled", True)),
        "allow_merge": bool(_setting_bool(settings, "subtitle_llm_context_allow_merge", True)),
        "max_word_corrections": int(_setting_int(settings, "subtitle_llm_context_max_word_corrections", 2)),
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _load_keep_cache(path: Path) -> dict[str, Any]:
    cache_key = str(path)
    if cache_key in _KEEP_DECISION_CACHE_BY_PATH:
        return _KEEP_DECISION_CACHE_BY_PATH[cache_key]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != KEEP_DECISION_CACHE_SCHEMA:
            raise ValueError("unsupported cache schema")
        entries = payload.get("entries")
        cache = dict(entries) if isinstance(entries, dict) else {}
    except Exception:
        cache = {}
    _KEEP_DECISION_CACHE_BY_PATH[cache_key] = cache
    return cache


def _save_keep_cache(path: Path, cache: dict[str, Any], *, max_entries: int = 512) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = dict(list(cache.items())[-max(1, int(max_entries)) :])
        payload = {
            "schema": KEEP_DECISION_CACHE_SCHEMA,
            "updated_epoch": round(time.time(), 3),
            "entries": entries,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        _KEEP_DECISION_CACHE_BY_PATH[str(path)] = entries
    except Exception:
        pass


def _cached_keep_decision(cache: dict[str, Any], key: str) -> dict[str, Any] | None:
    entry = cache.get(key)
    if not isinstance(entry, dict):
        return None
    decision = entry.get("decision")
    if not isinstance(decision, dict):
        return None
    if _decision_action(decision) != "keep" or _requested_correction_count(decision) > 0:
        return None
    return {"action": "keep", "corrections": [], "reason": str(decision.get("reason") or "cached_keep_no_change")}


def _apply_decision_to_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    decision: dict[str, Any] | None,
    settings: dict[str, Any],
    *,
    pair_index: int,
) -> tuple[list[dict[str, Any]], bool]:
    left_words = _segment_words(left)
    right_words = _segment_words(right)
    combined = left_words + right_words
    if not left_words or not right_words or len(combined) < 2:
        return [dict(left), dict(right)], False
    if not _words_cover_text(left_words, str(left.get("text", "") or "")) or not _words_cover_text(
        right_words,
        str(right.get("text", "") or ""),
    ):
        return [dict(left), dict(right)], False
    if not isinstance(decision, dict):
        return [dict(left), dict(right)], False

    corrected_words, corrections = _apply_corrections(combined, decision, settings)
    action = _decision_action(decision)
    policy_base = {
        "schema": CONTEXT_BOUNDARY_SCHEMA,
        "task": "subtitle_llm_context_boundary",
        "applies_to_modes": ["high"],
        "pair_index": int(pair_index),
        "action": action,
        "reason": str(decision.get("reason") or ""),
        "source_left_start": round(_as_float(left.get("start"), 0.0), 3),
        "source_left_end": round(_as_float(left.get("end"), 0.0), 3),
        "source_right_start": round(_as_float(right.get("start"), 0.0), 3),
        "source_right_end": round(_as_float(right.get("end"), 0.0), 3),
    }

    if action == "merge" and _setting_bool(settings, "subtitle_llm_context_allow_merge", True):
        merged_chars = len(_compact(_text_from_words(corrected_words)))
        max_merged = max(8, _setting_int(settings, "subtitle_llm_context_merge_max_chars", 32))
        if merged_chars <= max_merged and (_is_micro_fragment(left, settings) or _is_micro_fragment(right, settings)):
            row = _row_from_words(
                left,
                corrected_words,
                {**policy_base, "merged_source_count": 2, "corrections": corrections},
                corrections,
            )
            return ([row] if row else [dict(left), dict(right)]), bool(row)

    if action == "move_boundary":
        try:
            boundary_idx = int(decision.get("boundary_after_word_index"))
        except Exception:
            boundary_idx = -1
        if 0 <= boundary_idx < len(corrected_words) - 1:
            left_group = corrected_words[: boundary_idx + 1]
            right_group = corrected_words[boundary_idx + 1 :]
            if left_group and right_group:
                left_row = _row_from_words(
                    left,
                    left_group,
                    {
                        **policy_base,
                        "boundary_after_word_index": boundary_idx,
                        "boundary_time": round(_as_float(left_group[-1].get("end"), 0.0), 3),
                        "corrections": corrections,
                    },
                    corrections,
                )
                right_row = _row_from_words(
                    right,
                    right_group,
                    {
                        **policy_base,
                        "boundary_after_word_index": boundary_idx,
                        "boundary_time": round(_as_float(right_group[0].get("start"), 0.0), 3),
                        "corrections": corrections,
                    },
                    corrections,
                )
                if left_row and right_row:
                    changed = (
                        abs(_as_float(left_row.get("end"), 0.0) - _as_float(left.get("end"), 0.0)) > 0.001
                        or abs(_as_float(right_row.get("start"), 0.0) - _as_float(right.get("start"), 0.0)) > 0.001
                        or bool(corrections)
                    )
                    return [left_row, right_row], changed

    if corrections:
        split = len(left_words)
        left_row = _row_from_words(
            left,
            corrected_words[:split],
            {**policy_base, "action": "keep_with_word_correction", "corrections": corrections},
            corrections,
        )
        right_row = _row_from_words(
            right,
            corrected_words[split:],
            {**policy_base, "action": "keep_with_word_correction", "corrections": corrections},
            corrections,
        )
        if left_row and right_row:
            return [left_row, right_row], True

    return [dict(left), dict(right)], False


def refine_high_contextual_boundaries(
    segments: list[dict[str, Any]],
    *,
    vad_segments: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
    model: str = "",
    logger: Any = None,
    decision_func: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None,
    diagnostics_out: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    started = time.perf_counter()
    diagnostics = diagnostics_out if isinstance(diagnostics_out, dict) else None

    def _record_diagnostics(
        *,
        enabled: bool,
        reason: str,
        output_count: int,
        candidate_pairs: int = 0,
        skipped_pairs: int = 0,
        calls: int = 0,
        failed_calls: int = 0,
        changed_pairs: int = 0,
        max_pairs: int = 0,
        keep_decisions: int = 0,
        move_boundary_decisions: int = 0,
        merge_decisions: int = 0,
        invalid_decisions: int = 0,
        correction_requests: int = 0,
        applied_corrections: int = 0,
        keep_cache_enabled: bool = False,
        keep_cache_hits: int = 0,
        keep_cache_misses: int = 0,
        keep_cache_writes: int = 0,
    ) -> None:
        if diagnostics is None:
            return
        diagnostics.clear()
        diagnostics.update(
            {
                "schema": "ai_subtitle_studio.high_context_boundary_diagnostics.v1",
                "enabled": bool(enabled),
                "reason": str(reason or ""),
                "input_segment_count": len(rows),
                "output_segment_count": int(output_count),
                "candidate_pair_count": int(candidate_pairs),
                "skipped_pair_count": int(skipped_pairs),
                "llm_call_count": int(calls),
                "failed_call_count": int(failed_calls),
                "changed_pair_count": int(changed_pairs),
                "max_pairs": int(max_pairs),
                "keep_decision_count": int(keep_decisions),
                "move_boundary_decision_count": int(move_boundary_decisions),
                "merge_decision_count": int(merge_decisions),
                "invalid_decision_count": int(invalid_decisions),
                "correction_request_count": int(correction_requests),
                "applied_correction_count": int(applied_corrections),
                "keep_cache_enabled": bool(keep_cache_enabled),
                "keep_cache_hit_count": int(keep_cache_hits),
                "keep_cache_miss_count": int(keep_cache_misses),
                "keep_cache_write_count": int(keep_cache_writes),
                "elapsed_sec": round(max(0.0, time.perf_counter() - started), 6),
            }
        )

    s = dict(settings or {})
    if not rows:
        _record_diagnostics(enabled=False, reason="empty", output_count=0)
        return []
    if not _is_high_mode(s):
        _record_diagnostics(enabled=False, reason="not_high_mode", output_count=len(rows))
        return rows
    if not _setting_bool(s, "subtitle_llm_context_boundary_refine_enabled", False):
        _record_diagnostics(enabled=False, reason="disabled", output_count=len(rows))
        return rows
    if not _supports_context_refine_model(model):
        _record_diagnostics(enabled=False, reason="unsupported_model", output_count=len(rows))
        return rows

    ask = decision_func or _default_llm_decision
    max_pairs = max(0, _setting_int(s, "subtitle_llm_context_max_pairs", 24))
    if max_pairs <= 0:
        _record_diagnostics(enabled=False, reason="max_pairs_zero", output_count=len(rows), max_pairs=max_pairs)
        return rows

    keep_cache_enabled = _setting_bool(s, "subtitle_llm_context_keep_cache_enabled", False)
    keep_cache: dict[str, Any] = {}
    keep_cache_path: Path | None = None
    keep_cache_max_entries = max(1, _setting_int(s, "subtitle_llm_context_keep_cache_max_entries", 512))
    if keep_cache_enabled:
        keep_cache_path = _keep_cache_path(s)
        keep_cache = _load_keep_cache(keep_cache_path)

    idx = 0
    calls = 0
    candidate_pairs = 0
    skipped_pairs = 0
    failed_calls = 0
    changed_pairs = 0
    keep_decisions = 0
    move_boundary_decisions = 0
    merge_decisions = 0
    invalid_decisions = 0
    correction_requests = 0
    applied_corrections = 0
    keep_cache_hits = 0
    keep_cache_misses = 0
    keep_cache_writes = 0
    output: list[dict[str, Any]] = []
    while idx < len(rows):
        if idx >= len(rows) - 1 or candidate_pairs >= max_pairs:
            output.append(dict(rows[idx]))
            idx += 1
            continue
        left = dict(rows[idx])
        right = dict(rows[idx + 1])
        if not _candidate_pair(left, right, s):
            skipped_pairs += 1
            output.append(left)
            idx += 1
            continue

        candidate_pairs += 1
        words = _segment_words(left) + _segment_words(right)
        pair_start = _as_float(left.get("start"), 0.0)
        pair_end = _as_float(right.get("end"), _as_float(right.get("start"), pair_start))
        prompt = _build_pair_prompt(
            left,
            right,
            words,
            _vad_hints_for_pair(vad_segments or [], pair_start, pair_end),
            s,
            rules,
        )
        context = {
            "schema": CONTEXT_BOUNDARY_SCHEMA,
            "model": str(model or ""),
            "settings": s,
            "prompt": prompt,
            "pair_index": idx,
        }
        cache_key = ""
        cache_hit = False
        decision: dict[str, Any] | None = None
        if keep_cache_enabled:
            cache_key = _keep_cache_key(model=str(model or ""), prompt=prompt, settings=s)
            cached_decision = _cached_keep_decision(keep_cache, cache_key)
            if cached_decision is not None:
                decision = cached_decision
                cache_hit = True
                keep_cache_hits += 1
            else:
                keep_cache_misses += 1
        if not cache_hit:
            calls += 1
            try:
                decision = ask(left, right, context)
            except Exception as exc:
                failed_calls += 1
                if logger is not None:
                    try:
                        logger.log(f"[High-문맥경계] LLM 경계 검수 실패: {exc}")
                    except Exception:
                        pass
                decision = None
        if isinstance(decision, dict):
            action = _decision_action(decision)
            if action == "move_boundary":
                move_boundary_decisions += 1
            elif action == "merge":
                merge_decisions += 1
            else:
                keep_decisions += 1
            correction_requests += _requested_correction_count(decision)
        else:
            invalid_decisions += 1
        pair_rows, changed = _apply_decision_to_pair(left, right, decision, s, pair_index=idx)
        applied_count = _applied_correction_count(pair_rows)
        applied_corrections += applied_count
        if (
            keep_cache_enabled
            and not cache_hit
            and cache_key
            and keep_cache_path is not None
            and isinstance(decision, dict)
            and _decision_action(decision) == "keep"
            and _requested_correction_count(decision) == 0
            and applied_count == 0
            and not changed
        ):
            keep_cache[cache_key] = {
                "schema": KEEP_DECISION_CACHE_SCHEMA,
                "created_epoch": round(time.time(), 3),
                "decision": {
                    "action": "keep",
                    "corrections": [],
                    "reason": str(decision.get("reason") or ""),
                },
            }
            _save_keep_cache(keep_cache_path, keep_cache, max_entries=keep_cache_max_entries)
            keep_cache_writes += 1
        if len(pair_rows) == 1:
            output.extend(pair_rows)
            idx += 2
            changed_pairs += 1 if changed else 0
            continue
        if len(pair_rows) >= 2:
            output.append(pair_rows[0])
            rows[idx + 1] = pair_rows[1]
            changed_pairs += 1 if changed else 0
            idx += 1
            continue
        output.append(left)
        idx += 1

    if logger is not None and calls:
        try:
            logger.log(f"[High-문맥경계] 현재+다음 자막 {calls}쌍 검수, 경계/단어 보정 {changed_pairs}쌍")
        except Exception:
            pass
    _record_diagnostics(
        enabled=True,
        reason="completed",
        output_count=len(output),
        candidate_pairs=candidate_pairs,
        skipped_pairs=skipped_pairs,
        calls=calls,
        failed_calls=failed_calls,
        changed_pairs=changed_pairs,
        max_pairs=max_pairs,
        keep_decisions=keep_decisions,
        move_boundary_decisions=move_boundary_decisions,
        merge_decisions=merge_decisions,
        invalid_decisions=invalid_decisions,
        correction_requests=correction_requests,
        applied_corrections=applied_corrections,
        keep_cache_enabled=keep_cache_enabled,
        keep_cache_hits=keep_cache_hits,
        keep_cache_misses=keep_cache_misses,
        keep_cache_writes=keep_cache_writes,
    )
    return output
