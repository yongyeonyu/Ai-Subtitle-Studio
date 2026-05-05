from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from core.personalization.lora_storage import load_best_settings, save_best_settings, store_paths
from core.personalization.lora_trial_scoring import record_prompt_trial_result, record_setting_trial_result
from core.settings import load_settings


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = low
    return round(max(low, min(high, numeric)), 3)


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        numeric = low
    return max(low, min(high, numeric))


def _percentile(values: list[float], ratio: float) -> float:
    values = sorted(float(v) for v in values if v >= 0.0)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    return round(values[index], 3)


def _truth_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows or [])
    cps_values = [float(row.get("cps", 0.0) or 0.0) for row in rows]
    durations = [float(row.get("duration_sec", 0.0) or 0.0) for row in rows]
    char_counts = [int(row.get("char_count", 0) or 0) for row in rows]
    timeline_rows = sorted(
        [row for row in rows if row.get("start_sec") not in (None, "") and row.get("end_sec") not in (None, "")],
        key=lambda row: float(row.get("start_sec", 0.0) or 0.0),
    )
    gap_values: list[float] = []
    for prev, cur in zip(timeline_rows, timeline_rows[1:]):
        gap = float(cur.get("start_sec", 0.0) or 0.0) - float(prev.get("end_sec", 0.0) or 0.0)
        if 0.0 <= gap <= 12.0:
            gap_values.append(gap)
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
        "gap_p50": _percentile(gap_values, 0.5),
        "gap_p75": _percentile(gap_values, 0.75),
        "multiline_ratio": round((multiline_rows / len(rows)) if rows else 0.0, 3),
        "top_punctuation": punctuation.most_common(1)[0][0] if punctuation else "",
        "top_line_pattern": line_patterns.most_common(1)[0][0] if line_patterns else "",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _multimodal_context_summary(media_id: str, store_dir: str | None = None) -> dict[str, Any]:
    rows = [
        row
        for row in _read_jsonl(store_paths(store_dir)["multimodal_lora_context"])
        if str(row.get("media_id") or "") == str(media_id or "")
        or (not row.get("media_id") and str(media_id or "") == "global")
    ]
    if not rows:
        return {"row_count": 0}

    candidate_disagreements: list[float] = []
    candidate_counts: list[int] = []
    avg_cps_values: list[float] = []
    max_cps_values: list[float] = []
    excluded_ratios: list[float] = []
    has_audio = False
    has_video = False
    audio_sample_rates: list[int] = []
    audio_channels: list[int] = []
    video_fps_values: list[float] = []
    scene_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    focus_counter: Counter[str] = Counter()
    noise_source_counter: Counter[str] = Counter()
    mic_type_counter: Counter[str] = Counter()

    for row in rows:
        candidate_context = dict(row.get("candidate_context") or {})
        if candidate_context:
            candidate_disagreements.append(float(candidate_context.get("candidate_disagreement_ratio", 0.0) or 0.0))
            candidate_counts.append(int(candidate_context.get("candidate_count", 0) or 0))
        media_profile = dict(row.get("media_profile") or {})
        if media_profile:
            has_audio = has_audio or bool(media_profile.get("has_audio"))
            has_video = has_video or bool(media_profile.get("has_video"))
            audio = dict(media_profile.get("audio") or {})
            video = dict(media_profile.get("video") or {})
            if audio.get("sample_rate"):
                audio_sample_rates.append(int(audio.get("sample_rate", 0) or 0))
            if audio.get("channels"):
                audio_channels.append(int(audio.get("channels", 0) or 0))
            if video.get("fps"):
                video_fps_values.append(float(video.get("fps", 0.0) or 0.0))
        subtitle_profile = dict(row.get("subtitle_profile") or {})
        if subtitle_profile:
            excluded_ratios.append(float(subtitle_profile.get("excluded_parenthetical_ratio", 0.0) or 0.0))
            reading_speed = dict(subtitle_profile.get("reading_speed") or {})
            avg_cps_values.append(float(reading_speed.get("avg_cps", 0.0) or 0.0))
            max_cps_values.append(float(reading_speed.get("max_cps", 0.0) or 0.0))
        classification = dict(row.get("context_classification") or {})
        scene = str(dict(classification.get("scene_environment") or {}).get("label") or "")
        topic = str(dict(classification.get("topic") or {}).get("primary") or "")
        microphone = dict(classification.get("microphone_environment") or {})
        mic_type = str(microphone.get("mic_type") or "")
        if scene and scene != "unknown":
            scene_counter[scene] += 1
        if topic and topic != "unknown":
            topic_counter[topic] += 1
        if mic_type and mic_type != "unknown":
            mic_type_counter[mic_type] += 1
        for source in list(microphone.get("noise_sources") or []):
            if str(source or "").strip():
                noise_source_counter[str(source)] += 1
        for focus in list(classification.get("training_focus") or []):
            if str(focus or "").strip():
                focus_counter[str(focus)] += 1

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def top(counter: Counter[str]) -> str:
        return counter.most_common(1)[0][0] if counter else ""

    return {
        "row_count": len(rows),
        "has_audio": has_audio,
        "has_video": has_video,
        "avg_candidate_disagreement": avg(candidate_disagreements),
        "max_candidate_count": max(candidate_counts) if candidate_counts else 0,
        "context_avg_cps": avg(avg_cps_values),
        "context_max_cps": round(max(max_cps_values), 3) if max_cps_values else 0.0,
        "excluded_parenthetical_ratio": avg(excluded_ratios),
        "audio_sample_rate": max(audio_sample_rates) if audio_sample_rates else 0,
        "audio_channels": max(audio_channels) if audio_channels else 0,
        "video_fps": round(max(video_fps_values), 3) if video_fps_values else 0.0,
        "scene_environment": top(scene_counter),
        "topic": top(topic_counter),
        "mic_type": top(mic_type_counter),
        "noise_sources": [name for name, _count in noise_source_counter.most_common(6)],
        "training_focus": [name for name, _count in focus_counter.most_common(10)],
    }


def _derived_gap_settings(summary: dict[str, Any], base: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    avg_duration = float(summary.get("avg_duration", 0.0) or 0.0)
    gap_p50 = float(summary.get("gap_p50", 0.0) or 0.0)
    gap_p75 = float(summary.get("gap_p75", 0.0) or 0.0)
    multiline_ratio = float(summary.get("multiline_ratio", 0.0) or 0.0)
    scene = str(context.get("scene_environment") or "")
    noisy_sources = set(str(item) for item in list(context.get("noise_sources") or []))
    noisy = scene in {"car", "outdoor"} or bool(noisy_sources.intersection({"engine", "traffic", "wind", "crowd", "music"}))

    base_gap_break = float(base.get("sub_gap_break_sec", 1.5) or 1.5)
    gap_break = _clamp_float(gap_p75 or base_gap_break, 0.8, 2.2)
    continuous = _clamp_float(max(float(base.get("continuous_threshold", 2.0) or 2.0), gap_break * 1.35), 0.8, 4.0)
    min_duration = _clamp_float(avg_duration * 0.18 if avg_duration else base.get("sub_min_duration", 0.2), 0.1, 0.8)
    max_duration = _clamp_float(max(avg_duration * 2.2, gap_break * 2.8, float(base.get("sub_max_duration", 6.0) or 6.0)), 3.0, 9.0)
    dedup = _clamp_float(max(0.25, min(gap_p50 * 0.5, 1.0)) if gap_p50 else base.get("sub_dedup_window", 0.5), 0.2, 1.2)
    single_end = _clamp_float(max(0.1, min(gap_p50 * 0.25, 0.7)) if gap_p50 else base.get("single_subtitle_end", 0.2), 0.0, 0.8)
    push_rate = _clamp_float(base.get("gap_push_rate", 0.7), 0.45, 0.9)
    if noisy:
        push_rate = max(push_rate, 0.76)
    elif multiline_ratio >= 0.35:
        push_rate = max(push_rate, 0.72)

    return {
        "continuous_threshold": continuous,
        "gap_push_rate": push_rate,
        "single_subtitle_end": single_end,
        "sub_min_duration": min_duration,
        "sub_max_duration": max_duration,
        "sub_dedup_window": dedup,
        "sub_gap_break_sec": gap_break,
    }


def build_setting_candidate_bundles(
    rows: list[dict[str, Any]],
    base_settings: dict[str, Any] | None = None,
    multimodal_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    summary = _truth_summary(rows)
    context = dict(multimodal_context or {})
    base = dict(base_settings or load_settings() or {})
    gap_settings = _derived_gap_settings(summary, base, context)
    target_chars = _clamp_int(summary["avg_chars"] or 18.0, 12, 24)
    context_max_cps = float(context.get("context_max_cps", 0.0) or 0.0)
    target_cps = _clamp_int(max(summary["max_cps"] or 12.0, context_max_cps), 10, 18)
    preferred_audio_ai = base.get("selected_audio_ai", "deepfilter")
    if context.get("row_count"):
        scene = str(context.get("scene_environment") or "")
        noise_sources = set(str(item) for item in list(context.get("noise_sources") or []))
        if not bool(context.get("has_audio", True)):
            preferred_audio_ai = "none"
        elif scene == "car" or noise_sources.intersection({"engine", "traffic", "wind", "crowd", "music"}):
            preferred_audio_ai = "clearvoice"
        elif float(context.get("avg_candidate_disagreement", 0.0) or 0.0) >= 0.12 or target_cps >= 15:
            preferred_audio_ai = "clearvoice"
        else:
            preferred_audio_ai = "deepfilter"
    return [
        {
            "bundle_id": "baseline_precise",
            "reason_hint": "영상/음성/자막 context 반영 정확도 우선",
            "settings": {
                "selected_audio_ai": preferred_audio_ai,
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                **gap_settings,
                "split_length_threshold": target_chars,
                "sub_max_cps": target_cps,
            },
        },
        {
            "bundle_id": "clearvoice_dense",
            "reason_hint": "빠른 발화/밀집 구간 우선",
            "settings": {
                "selected_audio_ai": "clearvoice",
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                **gap_settings,
                "split_length_threshold": max(12, target_chars - 2),
                "sub_max_cps": max(12, target_cps),
                "continuous_threshold": _clamp_float(float(gap_settings["continuous_threshold"]) * 0.9, 0.8, 4.0),
                "sub_gap_break_sec": _clamp_float(min(float(gap_settings["sub_gap_break_sec"]), 1.0), 0.8, 2.2),
            },
        },
        {
            "bundle_id": "deepfilter_balanced",
            "reason_hint": "줄바꿈 안정성과 보수적 분리",
            "settings": {
                "selected_audio_ai": "deepfilter",
                "stt_quality_preset": "balanced",
                "subtitle_quality_enabled": True,
                **gap_settings,
                "split_length_threshold": min(24, target_chars + 1),
                "sub_max_cps": max(11, target_cps - 1),
                "sub_gap_break_sec": _clamp_float(max(float(gap_settings["sub_gap_break_sec"]), 1.3), 0.8, 2.2),
            },
        },
        {
            "bundle_id": "clean_raw_conservative",
            "reason_hint": "오디오 정제 최소화 + 보수적 CPS",
            "settings": {
                "selected_audio_ai": "none",
                "stt_quality_preset": "precise",
                "subtitle_quality_enabled": True,
                **gap_settings,
                "split_length_threshold": target_chars,
                "sub_max_cps": max(10, target_cps - 2),
                "sub_gap_break_sec": _clamp_float(max(float(gap_settings["sub_gap_break_sec"]), 1.6), 0.8, 2.2),
            },
        },
    ]


def _score_bundle(summary: dict[str, Any], bundle: dict[str, Any]) -> tuple[float, dict[str, Any], str]:
    settings = dict(bundle.get("settings") or {})
    context = dict(summary.get("multimodal_context") or {})
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
    if context.get("row_count"):
        scene = str(context.get("scene_environment") or "")
        topic = str(context.get("topic") or "")
        noise_sources = set(str(item) for item in list(context.get("noise_sources") or []))
        if not bool(context.get("has_audio", True)) and audio_ai == "none":
            score += 8.0
        if bool(context.get("has_audio")) and audio_ai in {"clearvoice", "deepfilter"}:
            score += 3.0
        if scene in {"car", "outdoor"} and audio_ai == "clearvoice":
            score += 4.0
        if scene == "indoor" and audio_ai == "deepfilter":
            score += 2.0
        if noise_sources.intersection({"engine", "traffic", "wind", "crowd", "music"}) and audio_ai == "clearvoice":
            score += 3.5
        if topic == "vehicle_review" and quality_preset == "precise":
            score += 2.5
        if float(context.get("avg_candidate_disagreement", 0.0) or 0.0) >= 0.12 and quality_preset == "precise":
            score += 5.0
        if float(context.get("excluded_parenthetical_ratio", 0.0) or 0.0) >= 0.15 and bool(settings.get("subtitle_quality_enabled")):
            score += 2.5
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
        "multimodal_context_rows": int(context.get("row_count", 0) or 0),
        "avg_candidate_disagreement": round(float(context.get("avg_candidate_disagreement", 0.0) or 0.0), 4),
        "excluded_parenthetical_ratio": round(float(context.get("excluded_parenthetical_ratio", 0.0) or 0.0), 4),
        "scene_environment": str(context.get("scene_environment") or ""),
        "topic": str(context.get("topic") or ""),
        "noise_sources": list(context.get("noise_sources") or []),
        "bundle_alignment_penalty": round(abs(split_length - target_chars) + abs(sub_max_cps - target_cps), 4),
    }
    reason = (
        f"{bundle.get('reason_hint', 'ground-truth 적합도')} · "
        f"split={int(round(split_length))} / target={int(round(target_chars))}, "
        f"cps={int(round(sub_max_cps))} / target={int(round(target_cps))}, "
        f"audio={audio_ai}, quality={quality_preset}, scene={context.get('scene_environment', '')}, "
        f"topic={context.get('topic', '')}, context_rows={int(context.get('row_count', 0) or 0)}"
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
    context_summary = _multimodal_context_summary(media_id, store_dir)
    summary = {**_truth_summary(rows), "multimodal_context": context_summary}
    bundles = build_setting_candidate_bundles(rows, base_settings=base_settings, multimodal_context=context_summary)
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

    if str(media_id or "").strip().lower() == "global":
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


def build_prompt_candidate_bundles(
    rows: list[dict[str, Any]],
    multimodal_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    summary = _truth_summary(rows)
    context = dict(multimodal_context or {})
    tone = "구어체 유지" if summary.get("multiline_ratio", 0.0) >= 0.3 else "짧은 자막 우선"
    bundles = [
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
    if context.get("row_count"):
        scene = str(context.get("scene_environment") or "unknown")
        topic = str(context.get("topic") or "unknown")
        noise_sources = ", ".join(str(item) for item in list(context.get("noise_sources") or [])[:4]) or "none"
        bundles.insert(
            1,
            {
                "prompt_template_id": "subtitle_qa_multimodal_context_v1",
                "prompt_text": (
                    f"분류된 환경(scene={scene}, topic={topic}, noise={noise_sources})과 "
                    "영상/음성 타이밍, STT 후보 차이, 자막 CPS와 줄바꿈 패턴을 함께 참고하되 "
                    "괄호/대괄호/중괄호 안 설명은 발화로 학습하거나 생성하지 마세요."
                ),
                "config": {"provider": "inherit", "model": "inherit"},
            },
        )
    return bundles


def _score_prompt_bundle(summary: dict[str, Any], bundle: dict[str, Any]) -> tuple[float, dict[str, Any], str]:
    prompt_text = str(bundle.get("prompt_text") or "")
    context = dict(summary.get("multimodal_context") or {})
    score = 78.0
    if "없는 말을 추가하지" in prompt_text:
        score += 7.0
    if float(summary.get("multiline_ratio", 0.0) or 0.0) >= 0.3 and "줄바꿈" in prompt_text:
        score += 6.0
    if str(summary.get("top_punctuation") or "") in {".", "!"} and "고유명사" in prompt_text:
        score += 4.0
    if context.get("row_count") and "영상/음성" in prompt_text:
        score += 6.0
    topic_label = str(context.get("topic") or "")
    if context.get("row_count") and topic_label and topic_label in prompt_text:
        score += 3.0
    if float(context.get("excluded_parenthetical_ratio", 0.0) or 0.0) >= 0.15 and "괄호" in prompt_text:
        score += 5.0
    score = max(0.0, min(99.5, score))
    metrics = {
        "final_score": round(score, 2),
        "multiline_ratio": round(float(summary.get("multiline_ratio", 0.0) or 0.0), 4),
        "top_punctuation": str(summary.get("top_punctuation") or ""),
        "multimodal_context_rows": int(context.get("row_count", 0) or 0),
        "excluded_parenthetical_ratio": round(float(context.get("excluded_parenthetical_ratio", 0.0) or 0.0), 4),
        "scene_environment": str(context.get("scene_environment") or ""),
        "topic": str(context.get("topic") or ""),
        "noise_sources": list(context.get("noise_sources") or []),
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
    context_summary = _multimodal_context_summary(media_id, store_dir)
    summary = {**_truth_summary(rows), "multimodal_context": context_summary}
    bundles = build_prompt_candidate_bundles(rows, multimodal_context=context_summary)
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
