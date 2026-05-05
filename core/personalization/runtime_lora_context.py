from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.personalization.lora_storage import load_best_settings, load_learned_rules
from core.personalization.lora_vector_retriever import retrieve_lora_context
from core.runtime import config
from core.utils import load_subtitle_rules
from core.subtitle_quality.correction_memory import search_correction_memory
from core.subtitle_quality.wrong_answer_memory import search_wrong_answer_memory


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


def _learned_rule_summary_lines(store_dir: str | Path | None = None) -> list[str]:
    lines: list[str] = []
    try:
        learned_split = load_learned_rules("split", store_dir)
        split_items = list(learned_split.get("items") or [])
        top_split = [str(item.get("rule_text") or "").strip() for item in split_items[:8] if str(item.get("rule_text") or "").strip()]
        if top_split:
            lines.append(f"- 학습된 분리 우선순위: {', '.join(top_split)}")
    except Exception:
        pass
    try:
        learned_break = load_learned_rules("line_break", store_dir)
        line_items = list(learned_break.get("items") or [])
        top_line = [str(item.get("rule_text") or "").strip() for item in line_items[:4] if str(item.get("rule_text") or "").strip()]
        if top_line:
            lines.append(f"- 학습된 줄바꿈 패턴: {', '.join(top_line)}")
    except Exception:
        pass
    try:
        best = load_best_settings(store_dir)
        defaults = dict(best.get("global_recommended_defaults") or {})
        if defaults:
            compact = []
            for key in ("selected_audio_ai", "stt_quality_preset", "split_length_threshold", "sub_max_cps", "sub_gap_break_sec"):
                value = defaults.get(key)
                if value not in (None, ""):
                    compact.append(f"{key}={value}")
            if compact:
                lines.append(f"- 학습된 기본 추천값: {', '.join(compact)}")
    except Exception:
        pass
    return lines


def _config_bits(config: dict[str, Any], limit: int = 5) -> str:
    keys = (
        "selected_audio_ai",
        "stt_quality_preset",
        "subtitle_quality_enabled",
        "split_length_threshold",
        "sub_min_duration",
        "sub_max_duration",
        "sub_max_cps",
        "sub_dedup_window",
        "sub_gap_break_sec",
        "continuous_threshold",
        "gap_push_rate",
        "single_subtitle_end",
        "selected_model",
    )
    bits = [f"{key}={config[key]}" for key in keys if config.get(key) not in (None, "")]
    return ", ".join(bits[:limit])


def _retrieved_lora_context_lines(
    text: str,
    settings: dict[str, Any] | None,
    *,
    store_dir: str | Path | None = None,
) -> list[str]:
    try:
        result = retrieve_lora_context(
            text,
            settings=settings,
            store_dir=store_dir,
            limit=14,
            per_kind=4,
        )
    except Exception:
        return []
    items = list(result.get("items") or [])
    if not items:
        return []

    score_model = _norm(result.get("score_model") or "hybrid")
    lines = [
        f"- LoRA 검색 인덱스: {int(result.get('index_doc_count', 0) or 0)}개 기억에서 {score_model} 방식으로 현재 자막과 가까운 근거를 점수화해 사용",
    ]

    examples: list[str] = []
    contexts: list[str] = []
    settings_hits: list[str] = []
    prompts: list[str] = []
    exclusions: list[str] = []
    rules: list[str] = []
    seen = set()
    for item in items:
        kind = str(item.get("kind") or "")
        payload = dict(item.get("payload") or {})
        score = float(item.get("retrieval_score", 0.0) or 0.0)
        if kind in {"text_lora_corpus", "text_lora_dataset"}:
            src = _norm(payload.get("input"))[:72]
            dst = _norm(payload.get("output"))[:72]
            key = ("example", src, dst)
            if src and dst and src != dst and key not in seen:
                examples.append(f"{src} -> {dst} (score {score:.1f})")
                seen.add(key)
        elif kind == "truth_table":
            speech = _norm(payload.get("speech_training_text"))[:76]
            if speech:
                pattern = _norm(payload.get("line_break_pattern"))
                suffix = f", line={pattern}" if pattern else ""
                key = ("truth", speech, pattern)
                if key not in seen:
                    examples.append(f"ground truth: {speech}{suffix} (score {score:.1f})")
                    seen.add(key)
        elif kind == "multimodal_lora_context":
            summary = dict(payload.get("classification_summary") or {})
            focus = ", ".join(list(summary.get("training_focus") or [])[:4])
            noise = ", ".join(list(summary.get("noise_sources") or [])[:4])
            bits = [
                f"scene={summary.get('scene') or '-'}",
                f"topic={summary.get('topic') or '-'}",
                f"mic={summary.get('mic_type') or '-'}",
                f"noise={summary.get('noise_level') or '-'}",
            ]
            if noise:
                bits.append(f"sources={noise}")
            if focus:
                bits.append(f"focus={focus}")
            contexts.append(f"{', '.join(bits)} (score {score:.1f})")
        elif kind in {"setting_trials", "best_settings", "audio_preset_lora"}:
            config = dict(payload.get("config") or payload.get("audio_tune_settings") or {})
            bits = _config_bits(config)
            if bits:
                settings_hits.append(f"{bits} (score {score:.1f})")
        elif kind == "prompt_trials":
            prompt = _norm(payload.get("prompt_text"))[:120]
            if prompt:
                prompts.append(f"{prompt} (score {score:.1f})")
        elif kind == "excluded_parentheticals":
            excluded = _norm(payload.get("excluded_text"))[:48]
            if excluded:
                exclusions.append(f"{excluded} 제외 (score {score:.1f})")
        elif kind in {"learned_split_rules", "learned_line_break_rules"}:
            rule = _norm(payload.get("rule_text"))[:32]
            if rule:
                rules.append(f"{rule} (score {score:.1f})")

    if examples:
        lines.append("- 검색된 유사 자막/ground truth: " + "; ".join(examples[:5]))
    if contexts:
        lines.append("- 검색된 유사 영상/마이크/주제 context: " + "; ".join(contexts[:3]))
    if settings_hits:
        lines.append("- 검색된 유사 설정 근거: " + "; ".join(settings_hits[:3]))
    if prompts:
        lines.append("- 검색된 유사 프롬프트 근거: " + "; ".join(prompts[:2]))
    if exclusions:
        lines.append("- 설명 자막 제외 근거: " + "; ".join(exclusions[:4]))
    if rules:
        lines.append("- 검색된 learned rule: " + "; ".join(rules[:4]))
    lines.append("- 괄호(), 대괄호[], 중괄호{} 안 설명은 사용자 메모이므로 발화 자막으로 학습/생성하지 마세요.")
    return lines


def build_runtime_lora_prompt(
    text: str,
    rules: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    store_dir: str | Path | None = None,
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
    retrieval_lines = _retrieved_lora_context_lines(text, settings, store_dir=store_dir)

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
    lines.extend(retrieval_lines)
    lines.extend(_learned_rule_summary_lines(store_dir))
    lines.append("위 예시와 충돌하면 원문 무결성, 짧고 자연스러운 한국어 구어체, 사용자 교정 memory 순서로 판단하세요.")
    return "\n".join(lines)


__all__ = ["build_runtime_lora_prompt", "runtime_lora_enabled"]
