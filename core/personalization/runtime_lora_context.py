from __future__ import annotations

import json
import re
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from core.runtime import config
from core.utils import load_subtitle_rules
from core.subtitle_quality.correction_memory import search_correction_memory
from core.subtitle_quality.wrong_answer_memory import search_wrong_answer_memory


TEXT_LORA_CORPUS_PATH = Path(config.DATASET_DIR) / "personalization" / "text_lora_corpus.jsonl"
TEXT_LORA_DATASET_PATH = Path(config.DATASET_DIR) / "personalization" / "text_lora_dataset.jsonl"
LEGACY_CORRECTION_PATH = Path(getattr(config, "CORRECTIONS_FILE", Path(config.DATASET_DIR) / "dataset_correction.json"))


def runtime_lora_enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(
        settings.get("subtitle_quality_auto_correct_enabled")
        or settings.get("editor_lora_runtime_enabled")
    )


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _limit_items(items: list[Any], limit: int, *, max_chars: int = 36) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        text = _norm(item)
        if not text:
            continue
        text = text[:max_chars]
        key = _compact(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _legacy_correction_matches(text: str, limit: int = 6) -> list[dict[str, str]]:
    data = _read_json(LEGACY_CORRECTION_PATH)
    if not isinstance(data, dict):
        return []
    haystack = _norm(text)
    matches: list[dict[str, str]] = []
    for original, corrected in data.items():
        src = _norm(original)
        dst = _norm(corrected)
        if src and dst and src != dst and src in haystack:
            matches.append({"original": src, "corrected": dst})
    matches.sort(key=lambda item: len(item["original"]), reverse=True)
    return matches[: max(0, int(limit or 0))]


def _recent_jsonl_rows(path: Path, limit: int = 120) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, int(limit or 1)))
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
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
    return list(rows)


def _score_example(text: str, row: dict[str, Any]) -> float:
    src = _compact(row.get("input"))
    dst = _compact(row.get("output"))
    needle = _compact(text)
    if not needle or not src:
        return 0.0
    if src in needle or needle in src:
        return 1.0
    score = SequenceMatcher(None, needle[:120], src[:120]).ratio()
    if dst and (dst in needle or needle in dst):
        score = max(score, 0.72)
    return score


def _lora_examples(text: str, limit: int = 4) -> list[dict[str, str]]:
    rows = _recent_jsonl_rows(TEXT_LORA_CORPUS_PATH) + _recent_jsonl_rows(TEXT_LORA_DATASET_PATH)
    candidates: list[tuple[float, dict[str, Any]]] = []
    seen = set()
    for row in rows:
        src = _norm(row.get("input"))
        dst = _norm(row.get("output"))
        if not src or not dst or src == dst:
            continue
        key = (_compact(src), _compact(dst))
        if key in seen:
            continue
        seen.add(key)
        candidates.append((_score_example(text, row), row))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = [row for score, row in candidates if score >= 0.32][:limit]
    if not selected:
        selected = [row for _, row in candidates[-limit:]]
    out: list[dict[str, str]] = []
    for row in selected[:limit]:
        out.append({
            "input": _norm(row.get("input"))[:80],
            "output": _norm(row.get("output"))[:80],
            "source": _norm(row.get("source") or row.get("task"))[:32],
        })
    return out


def _gap_summary(settings: dict[str, Any] | None) -> list[str]:
    settings = settings or {}
    items = [
        ("목표 글자 수", "split_length_threshold", "10자"),
        ("최대 자막 길이", "sub_max_duration", "6.0초"),
        ("최소 유지 시간", "sub_min_duration", "0.2초"),
        ("최대 CPS", "sub_max_cps", "12자/초"),
        ("강제 줄바꿈 무음", "sub_gap_break_sec", "1.5초"),
        ("연속자막 기준", "continuous_threshold", "2.0초"),
        ("자막간격 조정", "gap_push_rate", "0.7"),
        ("단일자막 유지", "single_subtitle_end", "0.2초"),
    ]
    summary: list[str] = []
    for label, key, default in items:
        value = settings.get(key, default)
        if value in (None, ""):
            value = default
        summary.append(f"{label}={value}")
    return summary


def _split_rule_summary(rules: dict[str, Any] | None, settings: dict[str, Any] | None) -> list[str]:
    merged = dict(load_subtitle_rules())
    merged.update(dict(rules or {}))
    settings = settings or {}
    max_chars = int(
        settings.get("split_length_threshold")
        or merged.get("max_chars")
        or getattr(config, "DEFAULT_MAX_CHARS", 20)
    )
    split_rules = _limit_items(list(merged.get("split_rules") or []), 16, max_chars=12)
    split_punctuation = _limit_items(list(merged.get("split_punctuation") or []), 8, max_chars=4)
    summary = [f"기본 분리 글자수={max_chars}자"]
    if split_rules:
        summary.append(f"분리 어미/접속어={', '.join(split_rules)}")
    if split_punctuation:
        summary.append(f"분리 문장부호={', '.join(split_punctuation)}")
    return summary


def build_runtime_lora_prompt(
    text: str,
    rules: dict[str, Any] | None,
    settings: dict[str, Any] | None,
) -> str:
    if not runtime_lora_enabled(settings):
        return ""

    merged_rules = dict(load_subtitle_rules())
    merged_rules.update(dict(rules or {}))
    start_words = _limit_items(list(merged_rules.get("start_words") or []), 18)
    end_words = _limit_items(list(merged_rules.get("end_words") or []), 24)
    correction_hits = search_correction_memory(text, limit=6, min_confidence=0.45)
    wrong_hits = search_wrong_answer_memory(text, limit=6)
    legacy_hits = _legacy_correction_matches(text, limit=6)
    examples = _lora_examples(text, limit=4)

    lines = [
        "[텍스트 LoRA/개인화 컨텍스트 - 자동 교정 허용 ON]",
        "사용자가 직접 고친 자막 데이터와 규칙을 최우선 참고하되, 원문에 없는 말은 절대 추가하지 마세요.",
        "이 컨텍스트는 최종 자막의 검수, 줄바꿈, 시작/끝 단어, 사용자 단어, 오답 회피에만 사용합니다.",
        "간격 메뉴 값은 시간 생성 지시가 아니라 분리 판단 참고값이며, 실제 시간 보정은 최종 간격 패스에서 적용됩니다.",
        f"- 간격/분할 값: {', '.join(_gap_summary(settings))}",
    ]
    split_summary = _split_rule_summary(merged_rules, settings)
    if split_summary:
        lines.append(f"- 자막 분리 규칙: {'; '.join(split_summary)}")
    if end_words:
        lines.append(f"- 줄바꿈/끝단어 후보: {', '.join(end_words)}")
    if start_words:
        lines.append(f"- 새 자막 시작단어 후보: {', '.join(start_words)}")
    if legacy_hits:
        lines.append("- 사용자 단어/교정사전: " + "; ".join(
            f"{item['original']} -> {item['corrected']}" for item in legacy_hits
        ))
    if correction_hits:
        lines.append("- 교정 memory: " + "; ".join(
            f"{_norm(item.get('original'))} -> {_norm(item.get('corrected'))}"
            for item in correction_hits
        ))
    if wrong_hits:
        lines.append("- 오답/환각 memory: " + "; ".join(
            _norm(item.get("phrase")) for item in wrong_hits if _norm(item.get("phrase"))
        ))
    if examples:
        lines.append("- 누적 자막 작업 예시:")
        for idx, item in enumerate(examples, 1):
            lines.append(f"  {idx}. {_norm(item.get('input'))} -> {_norm(item.get('output'))}")
    lines.append("위 예시와 충돌하면 원문 무결성, 짧고 자연스러운 한국어 구어체, 사용자 교정 memory 순서로 판단하세요.")
    return "\n".join(lines)


__all__ = ["build_runtime_lora_prompt", "runtime_lora_enabled"]
