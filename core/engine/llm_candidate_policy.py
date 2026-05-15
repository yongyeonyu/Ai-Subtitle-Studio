from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Iterable

from core.coerce import safe_float as _safe_float, safe_round_int as _safe_int
from core.engine.llm_correction_guard import normalized_text, validate_llm_chunks
from core.native_macos_acceleration import mac_native_swift_policy_experimental_enabled
from core.native_text_similarity import similarity_ratio
from core.runtime.setting_utils import setting_bool as _setting_bool


LLM_CANDIDATE_POLICY_SCHEMA = "ai_subtitle_studio.llm_candidate_policy.v1"
LLM_CANDIDATE_POLICY_MODEL_ID = "candidate_locked_minimal_diff_v1"


def _safe_bool(value: Any, default: bool = True) -> bool:
    return _setting_bool(
        value,
        default,
        false_values={"0", "false", "off", "no", "끔", "아니오"},
        false_only_strings=True,
        empty_is_default=False,
    )

def _clean_line(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _clean_chunks(chunks: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for chunk in chunks or ():
        cleaned = _clean_line(chunk)
        if cleaned:
            out.append(cleaned)
    return out


def _chunks_signature(chunks: Iterable[Any] | None) -> str:
    return "\x1f".join(normalized_text(chunk) for chunk in _clean_chunks(chunks))


def _is_natural_break(word: str, next_word: str, rules: dict[str, Any] | None) -> bool:
    rules = dict(rules or {})
    w_clean = re.sub(r"[^\w가-힣]", "", str(word or ""))
    nw_clean = re.sub(r"[^\w가-힣]", "", str(next_word or ""))
    if str(word or "").strip().endswith((",", "!", "?", "~")):
        return True
    for rule in list(rules.get("end_words") or []):
        if rule and w_clean.endswith(str(rule)):
            return True
    for rule in list(rules.get("start_words") or []):
        if rule and nw_clean.startswith(str(rule)):
            return True
    return False


def _tokenize(text: str) -> list[str]:
    stripped = str(text or "").strip()
    tokens = [item for item in re.split(r"\s+", stripped) if item]
    return tokens or ([stripped] if stripped else [])


def _greedy_rule_chunks(text: str, threshold: int, rules: dict[str, Any] | None) -> list[str]:
    tokens = _tokenize(text)
    if len(tokens) <= 1:
        return [text.strip()] if text.strip() else []
    threshold = max(2, int(threshold or 10))
    hard_limit = max(threshold + 2, int(math.ceil(threshold * 1.45)))
    chunks: list[str] = []
    buf: list[str] = []
    for index, token in enumerate(tokens):
        buf.append(token)
        is_last = index == len(tokens) - 1
        clen = _compact_len(" ".join(buf))
        flush = is_last
        if not is_last:
            next_token = tokens[index + 1]
            flush = (clen >= threshold and _is_natural_break(token, next_token, rules)) or clen >= hard_limit
        if flush:
            chunk = _clean_line(" ".join(buf))
            if chunk:
                chunks.append(chunk)
            buf = []
    return chunks or ([text.strip()] if text.strip() else [])


def _balanced_chunks(text: str, threshold: int) -> list[str]:
    tokens = _tokenize(text)
    if len(tokens) <= 1:
        return [text.strip()] if text.strip() else []
    char_count = max(1, _compact_len(text))
    target_chunks = max(1, min(6, int(math.ceil(char_count / max(2, int(threshold or 10))))))
    if target_chunks <= 1:
        return [_clean_line(text)]
    target_chars = max(1, int(math.ceil(char_count / target_chunks)))
    chunks: list[str] = []
    buf: list[str] = []
    for token in tokens:
        if buf and _compact_len(" ".join(buf + [token])) > target_chars and len(chunks) < target_chunks - 1:
            chunks.append(_clean_line(" ".join(buf)))
            buf = [token]
        else:
            buf.append(token)
    if buf:
        chunks.append(_clean_line(" ".join(buf)))
    return chunks or [_clean_line(text)]


def _balanced_chunks_for_count(text: str, target_count: int) -> list[str]:
    tokens = _tokenize(text)
    target_count = max(1, min(4, _safe_int(target_count, 1)))
    if target_count <= 1 or len(tokens) <= 1:
        return [_clean_line(text)] if _clean_line(text) else []
    target_count = min(target_count, len(tokens))
    char_count = max(1, _compact_len(text))
    target_chars = max(1, int(math.ceil(char_count / target_count)))
    chunks: list[str] = []
    buf: list[str] = []
    for token in tokens:
        if buf and len(chunks) < target_count - 1 and _compact_len(" ".join(buf + [token])) > target_chars:
            chunks.append(_clean_line(" ".join(buf)))
            buf = [token]
        else:
            buf.append(token)
    if buf:
        chunks.append(_clean_line(" ".join(buf)))
    return chunks or [_clean_line(text)]


def _pattern_chunks(text: str, pattern: str) -> list[str]:
    targets = [
        _safe_int(part, 0)
        for part in re.split(r"[|,/ ]+", str(pattern or "").strip())
        if str(part or "").strip()
    ]
    targets = [max(1, value) for value in targets if value > 0]
    if len(targets) <= 1:
        return []
    tokens = _tokenize(text)
    if len(tokens) <= 1:
        return [_clean_line(text)] if _clean_line(text) else []
    chunks: list[str] = []
    buf: list[str] = []
    target_index = 0
    for token in tokens:
        if (
            buf
            and target_index < len(targets) - 1
            and _compact_len(" ".join(buf + [token])) > targets[target_index]
        ):
            chunks.append(_clean_line(" ".join(buf)))
            buf = [token]
            target_index += 1
        else:
            buf.append(token)
    if buf:
        chunks.append(_clean_line(" ".join(buf)))
    return chunks if len(chunks) >= 2 else []


def _lora_line_break_patterns(settings: dict[str, Any], *, limit: int = 3) -> list[str]:
    profile = dict(settings.get("_lora_generation_profile") or {})
    patterns: list[str] = []
    seen: set[str] = set()

    def add(pattern: Any) -> None:
        text = str(pattern or "").strip()
        if not text or "|" not in text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        patterns.append(text)

    add(settings.get("lora_line_break_pattern"))
    for item in list(profile.get("examples") or []):
        if isinstance(item, dict):
            add(item.get("line_break_pattern"))
            style = item.get("style_profile") if isinstance(item.get("style_profile"), dict) else {}
            add((style.get("line_break") or {}).get("pattern") if isinstance(style.get("line_break"), dict) else "")
    for item in list(profile.get("learned_rules") or []):
        if isinstance(item, dict) and str(item.get("kind") or "") == "learned_line_break_rules":
            add(item.get("rule_text"))
    return patterns[: max(0, int(limit or 0))]


def _existing_line_chunks(text: str) -> list[str]:
    return [_clean_line(line) for line in str(text or "").splitlines() if _clean_line(line)]


def build_llm_candidate_options(
    text: str,
    threshold: int,
    rules: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    native_requested = mac_native_swift_policy_experimental_enabled(settings) and (
        _safe_bool(settings.get("native_swift_llm_candidate_policy_enabled"), False)
        or any(
            os.environ.get(key, "").strip().lower() in {"1", "true", "on", "yes"}
            for key in ("AI_SUBTITLE_STUDIO_SWIFT_LLM_POLICY", "AI_SUBTITLE_STUDIO_SWIFT_POLICY")
        )
    )
    if native_requested:
        try:
            from core.native_swift_policy import build_llm_candidate_options_via_swift

            native = build_llm_candidate_options_via_swift(text, threshold, rules, settings)
            if native is not None:
                return native
        except Exception:
            pass
    if not _safe_bool(settings.get("llm_candidate_policy_enabled"), True):
        return []
    max_candidates = max(1, min(6, _safe_int(settings.get("llm_candidate_policy_max_candidates"), 4)))
    source = _clean_line(text)
    if not source:
        return []

    target_line_count = _safe_int(settings.get("subtitle_target_line_count"), 0)
    lora_pattern_limit = max(0, min(6, _safe_int(settings.get("linebreak_lora_policy_max_patterns"), 3)))
    lora_patterns = (
        _lora_line_break_patterns(settings, limit=lora_pattern_limit)
        if _safe_bool(settings.get("linebreak_lora_policy_enabled"), True)
        else []
    )
    raw_candidates = [
        ("A", "원문 유지", [source], "source"),
    ]
    for index, pattern in enumerate(lora_patterns, start=1):
        raw_candidates.append(
            (
                f"L{index}",
                f"LoRA ground truth 줄바꿈({pattern})",
                _pattern_chunks(source, pattern),
                "lora_ground_truth_line_break",
            )
        )
    raw_candidates.extend(
        [
            ("B", "기존 줄바꿈 유지", _existing_line_chunks(text), "existing_linebreak"),
            ("C", "규칙 기반 안전 분할", _greedy_rule_chunks(source, threshold, rules), "rule_greedy"),
        ]
    )
    if target_line_count >= 2:
        raw_candidates.append(("D", "LoRA 줄 수 맞춤", _balanced_chunks_for_count(source, target_line_count), "lora_line_count"))
    raw_candidates.append(("E", "균형 길이 분할", _balanced_chunks(source, threshold), "balanced"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate_id, label, chunks, strategy in raw_candidates:
        cleaned = _clean_chunks(chunks)
        if not cleaned:
            continue
        signature = _chunks_signature(cleaned)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        out.append(
            {
                "id": candidate_id,
                "label": label,
                "strategy": strategy,
                "chunks": cleaned,
                "chunk_count": len(cleaned),
                "compact_len": _compact_len("".join(cleaned)),
                "lora_primary": strategy == "lora_ground_truth_line_break",
            }
        )
        if len(out) >= max_candidates:
            break
    return out


def format_candidate_options_for_prompt(candidates: list[dict[str, Any]] | None) -> str:
    rows = []
    for item in list(candidates or []):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or ""),
                "result": _clean_chunks(item.get("chunks") or []),
            }
        )
    if not rows:
        return ""
    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    return (
        "[후보 잠금 모드]\n"
        "아래 후보 중 하나의 result를 우선 그대로 선택하세요. 새 문장을 쓰거나 후보끼리 섞지 마세요.\n"
        "LoRA ground truth 후보가 있으면 줄 구성은 그 후보를 최우선 기준으로 삼으세요.\n"
        "명백한 띄어쓰기/오탈자/문장부호 최소 수정이 필요할 때만 후보를 아주 조금 고칠 수 있습니다.\n"
        "단, 원문에 없는 명사, 숫자, 브랜드명, 설명, 감정 표현은 절대 추가하지 마세요.\n"
        "최종 출력 JSON의 result는 선택한 후보의 줄 구성과 거의 같아야 합니다.\n"
        f"{payload}"
    )


def validate_candidate_locked_chunks(
    source_text: str,
    chunks: Iterable[str] | None,
    candidates: list[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
) -> tuple[list[str] | None, dict[str, Any]]:
    settings = dict(settings or {})
    cleaned = _clean_chunks(chunks)
    candidate_rows = [dict(item) for item in list(candidates or []) if isinstance(item, dict)]
    if not _safe_bool(settings.get("llm_candidate_policy_enabled"), True) or not candidate_rows:
        return cleaned or None, {
            "schema": LLM_CANDIDATE_POLICY_SCHEMA,
            "task": "llm_candidate_policy",
            "model": LLM_CANDIDATE_POLICY_MODEL_ID,
            "accepted": bool(cleaned),
            "reason": "disabled_or_no_candidates",
            "candidate_count": len(candidate_rows),
        }

    output_sig = _chunks_signature(cleaned)
    source_sig = normalized_text(source_text)
    best_id = ""
    best_label = ""
    best_similarity = 0.0
    for candidate in candidate_rows:
        candidate_sig = _chunks_signature(candidate.get("chunks") or [])
        similarity = similarity_ratio(candidate_sig, output_sig) if candidate_sig and output_sig else 0.0
        if similarity > best_similarity:
            best_similarity = similarity
            best_id = str(candidate.get("id") or "")
            best_label = str(candidate.get("label") or "")
        if candidate_sig and candidate_sig == output_sig:
            return cleaned, {
                "schema": LLM_CANDIDATE_POLICY_SCHEMA,
                "task": "llm_candidate_policy",
                "model": LLM_CANDIDATE_POLICY_MODEL_ID,
                "accepted": True,
                "reason": "candidate_match",
                "selected_candidate_id": str(candidate.get("id") or ""),
                "selected_candidate_label": str(candidate.get("label") or ""),
                "candidate_count": len(candidate_rows),
                "similarity_to_best_candidate": 1.0,
                "edit_ratio": 0.0,
            }

    allow_minimal = _safe_bool(settings.get("llm_candidate_policy_allow_minimal_edit"), True)
    max_edit_ratio = max(0.0, min(0.5, _safe_float(settings.get("llm_candidate_policy_max_edit_ratio"), 0.08)))
    edit_similarity = similarity_ratio(source_sig, output_sig) if source_sig and output_sig else 0.0
    edit_ratio = 1.0 - edit_similarity
    ok, guard_reason = validate_llm_chunks(
        source_text,
        cleaned,
        min_similarity=max(0.9, _safe_float(settings.get("llm_verifier_min_similarity"), 0.86)),
        max_length_delta_ratio=min(0.10, _safe_float(settings.get("llm_verifier_max_length_delta_ratio"), 0.16)),
    )
    if allow_minimal and ok and edit_ratio <= max_edit_ratio:
        return cleaned, {
            "schema": LLM_CANDIDATE_POLICY_SCHEMA,
            "task": "llm_candidate_policy",
            "model": LLM_CANDIDATE_POLICY_MODEL_ID,
            "accepted": True,
            "reason": "minimal_edit",
            "selected_candidate_id": best_id,
            "selected_candidate_label": best_label,
            "candidate_count": len(candidate_rows),
            "similarity_to_best_candidate": round(best_similarity, 4),
            "edit_ratio": round(edit_ratio, 4),
            "max_edit_ratio": round(max_edit_ratio, 4),
        }

    return None, {
        "schema": LLM_CANDIDATE_POLICY_SCHEMA,
        "task": "llm_candidate_policy",
        "model": LLM_CANDIDATE_POLICY_MODEL_ID,
        "accepted": False,
        "reason": f"not_candidate_or_minimal_edit:{guard_reason}",
        "selected_candidate_id": best_id,
        "selected_candidate_label": best_label,
        "candidate_count": len(candidate_rows),
        "similarity_to_best_candidate": round(best_similarity, 4),
        "edit_ratio": round(edit_ratio, 4),
        "max_edit_ratio": round(max_edit_ratio, 4),
    }


__all__ = [
    "LLM_CANDIDATE_POLICY_MODEL_ID",
    "LLM_CANDIDATE_POLICY_SCHEMA",
    "build_llm_candidate_options",
    "format_candidate_options_for_prompt",
    "validate_candidate_locked_chunks",
]
