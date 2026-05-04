from __future__ import annotations

from collections import Counter
from typing import Any

from core.personalization.lora_storage import load_best_settings, save_best_settings
from core.personalization.lora_trial_scoring import record_prompt_trial_result, record_setting_trial_result
from core.settings import load_settings


def _truth_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows or [])
    cps_values = [float(row.get("cps", 0.0) or 0.0) for row in rows]
    durations = [float(row.get("duration_sec", 0.0) or 0.0) for row in rows]
    char_counts = [int(row.get("char_count", 0) or 0) for row in rows]
    punctuation = Counter(str(row.get("punctuation_pattern") or "") for row in rows if str(row.get("punctuation_pattern") or ""))
    line_patterns = Counter(str(row.get("line_break_pattern") or "") for row in rows if str(row.get("line_break_pattern") or ""))
    multiline_rows = sum(1 for row in rows if "|" in str(row.get("line_break_pattern") or ""))
    avg_cps = sum(cps_values) / len(cps_values) if cps_values else 0.0
    avg_duration = sum(durations) / len(durations) if durations else 0.0
    avg_chars = sum(char_counts) / len(char_counts) if char_counts else 0.0
    return {
        "row_count": len(rows),
        "avg_cps": round(avg_cps, 3),
        "max_cps": round(max(cps_values), 3) if cps_values else 0.0,
        "avg_duration": round(avg_duration, 3),
        "avg_chars": round(avg_chars, 3),
        "multiline_ratio": round((multiline_rows / len(rows)) if rows else 0.0, 3),
        "top_punctuation": punctuation.most_common(1)[0][0] if punctuation else "",
        "top_line_pattern": line_patterns.most_common(1)[0][0] if line_patterns else "",
    }


def build_setting_candidate_bundles(rows: list[dict[str, Any]], base_settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    summary = _truth_summary(rows)
    base = dict(base_settings or load_settings() or {})
    target_chars = max(12, min(24, int(round(summary["avg_chars"] or 18.0)) or 18))
    target_cps = max(10, min(18, int(round(summary["max_cps"] or 12.0)) or 12))
    return [
        {
            "bundle_id": "baseline_precise",
            "reason_hint": "현재 정확도 우선 기본값",
            "settings": {
                "selected_audio_ai": base.get("selected_audio_ai", "deepfilter"),
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                "split_length_threshold": target_chars,
                "sub_max_cps": target_cps,
                "sub_gap_break_sec": max(0.8, min(2.0, float(base.get("sub_gap_break_sec", 1.5) or 1.5))),
            },
        },
        {
            "bundle_id": "clearvoice_dense",
            "reason_hint": "빠른 발화/밀집 구간 우선",
            "settings": {
                "selected_audio_ai": "clearvoice",
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                "split_length_threshold": max(12, target_chars - 2),
                "sub_max_cps": max(12, target_cps),
                "sub_gap_break_sec": 1.0,
            },
        },
        {
            "bundle_id": "deepfilter_balanced",
            "reason_hint": "줄바꿈 안정성과 보수적 분리",
            "settings": {
                "selected_audio_ai": "deepfilter",
                "stt_quality_preset": "balanced",
                "subtitle_quality_enabled": True,
                "split_length_threshold": min(24, target_chars + 1),
                "sub_max_cps": max(11, target_cps - 1),
                "sub_gap_break_sec": 1.3,
            },
        },
        {
            "bundle_id": "clean_raw_conservative",
            "reason_hint": "오디오 정제 최소화 + 보수적 CPS",
            "settings": {
                "selected_audio_ai": "none",
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                "split_length_threshold": target_chars,
                "sub_max_cps": max(10, target_cps - 2),
                "sub_gap_break_sec": 1.6,
            },
        },
    ]


def _score_bundle(summary: dict[str, Any], bundle: dict[str, Any]) -> tuple[float, dict[str, Any], str]:
    settings = dict(bundle.get("settings") or {})
    score = 74.0
    target_chars = max(12.0, min(24.0, float(summary.get("avg_chars", 18.0) or 18.0)))
    target_cps = max(10.0, min(18.0, float(summary.get("max_cps", 12.0) or 12.0)))
    multiline_ratio = float(summary.get("multiline_ratio", 0.0) or 0.0)
    split_length = float(settings.get("split_length_threshold", target_chars) or target_chars)
    sub_max_cps = float(settings.get("sub_max_cps", target_cps) or target_cps)
    audio_ai = str(settings.get("selected_audio_ai", "") or "")
    quality_preset = str(settings.get("stt_quality_preset", "") or "")

    score -= abs(split_length - target_chars) * 1.4
    score -= abs(sub_max_cps - target_cps) * 2.1
    if quality_preset == "precise":
        score += 8.0
    elif quality_preset == "balanced":
        score += 4.0
    if audio_ai in {"clearvoice", "deepfilter"}:
        score += 5.5
    elif audio_ai == "none":
        score += 1.5
    if multiline_ratio >= 0.35 and bool(settings.get("subtitle_quality_enabled")):
        score += 4.0
    if summary.get("top_punctuation") == "." and split_length <= target_chars + 1:
        score += 2.0
    score = max(0.0, min(99.5, score))
    metrics = {
        "final_score": round(score, 2),
        "target_avg_chars": round(target_chars, 2),
        "target_max_cps": round(target_cps, 2),
        "multiline_ratio": round(multiline_ratio, 4),
        "bundle_alignment_penalty": round(abs(split_length - target_chars) + abs(sub_max_cps - target_cps), 4),
    }
    reason = (
        f"{bundle.get('reason_hint', 'ground-truth 적합도')} · "
        f"split={int(round(split_length))} / target={int(round(target_chars))}, "
        f"cps={int(round(sub_max_cps))} / target={int(round(target_cps))}, "
        f"audio={audio_ai}, quality={quality_preset}"
    )
    return score, metrics, reason


def optimize_settings_for_media(
    media_id: str,
    rows: list[dict[str, Any]],
    *,
    media_path: str = "",
    subtitle_path: str = "",
    store_dir: str | None = None,
    base_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = _truth_summary(rows)
    bundles = build_setting_candidate_bundles(rows, base_settings=base_settings)
    results = []
    best_score = -1.0
    best_config: dict[str, Any] = {}
    best_reason = ""
    for bundle in bundles:
        score, metrics, reason = _score_bundle(summary, bundle)
        result = record_setting_trial_result(
            media_id=media_id,
            media_path=media_path,
            subtitle_path=subtitle_path,
            config=dict(bundle.get("settings") or {}),
            metrics=metrics,
            reason=reason,
            store_dir=store_dir,
        )
        results.append(result["trial"])
        if score > best_score:
            best_score = score
            best_config = dict(bundle.get("settings") or {})
            best_reason = reason

    best_settings = load_best_settings(store_dir)
    defaults = dict(best_settings.get("global_recommended_defaults") or {})
    defaults.update(best_config)
    best_settings["global_recommended_defaults"] = defaults
    save_best_settings(best_settings, store_dir)
    return {
        "summary": summary,
        "trial_count": len(results),
        "best_score": round(best_score, 2),
        "best_config": best_config,
        "best_reason": best_reason,
    }


def build_prompt_candidate_bundles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = _truth_summary(rows)
    tone = "구어체 유지" if summary.get("multiline_ratio", 0.0) >= 0.3 else "짧은 자막 우선"
    return [
        {
            "prompt_template_id": "subtitle_qa_conservative_v1",
            "prompt_text": f"원문 무결성과 {tone}를 최우선으로 두고 없는 말을 추가하지 마세요.",
            "config": {"provider": "inherit", "model": "inherit"},
        },
        {
            "prompt_template_id": "subtitle_qa_linebreak_v1",
            "prompt_text": "줄바꿈과 호흡을 우선 맞추되 고유명사와 숫자는 추측하지 마세요.",
            "config": {"provider": "inherit", "model": "inherit"},
        },
        {
            "prompt_template_id": "subtitle_qa_propernoun_v1",
            "prompt_text": "고유명사, 브랜드명, 숫자를 보수적으로 유지하고 STT 환각 문구를 제거하세요.",
            "config": {"provider": "inherit", "model": "inherit"},
        },
    ]


def _score_prompt_bundle(summary: dict[str, Any], bundle: dict[str, Any]) -> tuple[float, dict[str, Any], str]:
    prompt_text = str(bundle.get("prompt_text") or "")
    score = 78.0
    if "없는 말을 추가하지" in prompt_text:
        score += 7.0
    if float(summary.get("multiline_ratio", 0.0) or 0.0) >= 0.3 and "줄바꿈" in prompt_text:
        score += 6.0
    if str(summary.get("top_punctuation") or "") in {".", "!"} and "고유명사" in prompt_text:
        score += 4.0
    score = max(0.0, min(99.5, score))
    metrics = {
        "final_score": round(score, 2),
        "multiline_ratio": round(float(summary.get("multiline_ratio", 0.0) or 0.0), 4),
        "top_punctuation": str(summary.get("top_punctuation") or ""),
    }
    reason = f"ground-truth 스타일 적합도 · prompt={bundle.get('prompt_template_id')}"
    return score, metrics, reason


def optimize_prompts_for_media(
    media_id: str,
    rows: list[dict[str, Any]],
    *,
    media_path: str = "",
    subtitle_path: str = "",
    store_dir: str | None = None,
) -> dict[str, Any]:
    summary = _truth_summary(rows)
    bundles = build_prompt_candidate_bundles(rows)
    results = []
    best_score = -1.0
    best_prompt_id = ""
    best_prompt_text = ""
    for bundle in bundles:
        score, metrics, reason = _score_prompt_bundle(summary, bundle)
        result = record_prompt_trial_result(
            media_id=media_id,
            media_path=media_path,
            subtitle_path=subtitle_path,
            config=dict(bundle.get("config") or {}),
            prompt_template_id=str(bundle.get("prompt_template_id") or ""),
            prompt_text=str(bundle.get("prompt_text") or ""),
            metrics=metrics,
            reason=reason,
            store_dir=store_dir,
        )
        results.append(result["trial"])
        if score > best_score:
            best_score = score
            best_prompt_id = str(bundle.get("prompt_template_id") or "")
            best_prompt_text = str(bundle.get("prompt_text") or "")
    return {
        "summary": summary,
        "trial_count": len(results),
        "best_score": round(best_score, 2),
        "best_prompt_id": best_prompt_id,
        "best_prompt_text": best_prompt_text,
    }


__all__ = [
    "build_prompt_candidate_bundles",
    "build_setting_candidate_bundles",
    "optimize_prompts_for_media",
    "optimize_settings_for_media",
]
