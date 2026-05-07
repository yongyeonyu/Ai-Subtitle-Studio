from __future__ import annotations

"""User-facing Fast/Auto/High mode policy.

The rest of the app still stores the historical STT quality keys in a few
places (`fast`, `balanced`, `precise`). This module is the compatibility layer:
UI and pipeline code can talk in Mode terms while existing project/settings
files continue to load without a schema break.
"""

from copy import deepcopy
from typing import Any


MODE_POLICY_SCHEMA = "ai_subtitle_studio.mode_policy.v1"
MODE_DASHBOARD_SCHEMA = "ai_subtitle_studio.engine_dashboard.v1"
MODE_PREFLIGHT_SCHEMA = "ai_subtitle_studio.mode_preflight.v1"
MODE_TOOL_STACK_SCHEMA = "ai_subtitle_studio.subtitle_tool_stack.v1"

MODE_ORDER = ("fast", "auto", "high")
MODE_LABELS = {
    "fast": "Fast",
    "auto": "Auto",
    "high": "High",
}
MODE_TO_STT_QUALITY = {
    "fast": "fast",
    "auto": "balanced",
    "high": "precise",
}
STT_QUALITY_TO_MODE = {
    "fast": "fast",
    "balanced": "auto",
    "precise": "high",
}

ENGINE_DASHBOARD_STEPS = (
    ("cut_boundary", "컷 경계"),
    ("preprocessing", "전처리"),
    ("audio_filter", "음성"),
    ("stt1", "STT 1"),
    ("stt2", "STT 2"),
    ("vad", "VAD"),
    ("subtitle_llm", "자막 LLM"),
    ("roughcut_llm", "러프컷 LLM"),
    ("lora", "LoRA"),
    ("deep_learning", "딥러닝"),
)

MODE_TOOL_STACKS = {
    "fast": {
        "label": "LoRA fast path",
        "tools": ["lora"],
        "lora": True,
        "deep_learning": False,
        "llm": False,
        "macro_llm": False,
        "reason": "Fast mode keeps subtitle generation on the LoRA/pattern path and skips Deep/LLM work.",
    },
    "auto": {
        "label": "LoRA + Deep balanced path",
        "tools": ["lora", "deep_learning"],
        "lora": True,
        "deep_learning": True,
        "llm": False,
        "macro_llm": False,
        "reason": "Auto mode lets LoRA settle timing/style first, then Deep handles uncertain STT and split decisions.",
    },
    "high": {
        "label": "LoRA + Deep + LLM quality path",
        "tools": ["lora", "deep_learning", "llm"],
        "lora": True,
        "deep_learning": True,
        "llm": True,
        "macro_llm": True,
        "reason": "High mode adds chunked LLM review after the LoRA/Deep fast pass.",
    },
}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"0", "false", "off", "no", "n", "끔", "아니오"}:
            return False
        if text in {"1", "true", "on", "yes", "y", "켬", "예"}:
            return True
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _short_model_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "사용 안함" in text:
        return "미사용"
    for prefix in ("mlx-community/", "Systran/", "youngouk/", "ghost613/", "o0dimplz0o/"):
        text = text.replace(prefix, "")
    return text.replace("-mlx", "")


def _tool_stack_for_mode(mode: Any) -> dict[str, Any]:
    key = normalize_mode(mode)
    return {
        "schema": MODE_TOOL_STACK_SCHEMA,
        "mode": key,
        **deepcopy(MODE_TOOL_STACKS[key]),
    }


def _disable_subtitle_llm_settings(
    out: dict[str, Any],
    *,
    mode: str,
    configured_model: str = "",
    configured_provider: str = "",
    preserve_configured_model: bool = False,
) -> None:
    has_configured_model = bool(configured_model and "사용 안함" not in configured_model)
    if preserve_configured_model and has_configured_model:
        out["selected_model"] = configured_model
        out["selected_llm_provider"] = configured_provider or "ollama"
        out["subtitle_llm_user_selected"] = True
    else:
        out["selected_model"] = "사용 안함 (Whisper 단독 진행)"
        out["selected_llm_provider"] = "none"
        out["subtitle_llm_user_selected"] = False
    out.update(
        {
            "subtitle_llm_runtime_enabled": False,
            "subtitle_llm_mode_disabled": True,
            "subtitle_llm_effective_model": "사용 안함 (모드 정책)",
            "subtitle_llm_macro_chunk_enabled": False,
            "llm_confidence_gate_enabled": False,
            "llm_candidate_policy_enabled": False,
            "llm_minimize_enabled": False,
            "subtitle_tool_stack_reason": MODE_TOOL_STACKS[mode]["reason"],
        }
    )


def normalize_mode(value: Any, *, default: str = "auto") -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "fast": "fast",
        "speed": "fast",
        "quick": "fast",
        "빠름": "fast",
        "빠른": "fast",
        "빠른 인식": "fast",
        "빠른인식": "fast",
        "auto": "auto",
        "automatic": "auto",
        "autopilot": "auto",
        "default": "auto",
        "normal": "auto",
        "balanced": "auto",
        "balance": "auto",
        "보통": "auto",
        "균형": "auto",
        "자동": "auto",
        "high": "high",
        "precise": "high",
        "quality": "high",
        "accuracy": "high",
        "정밀": "high",
        "정확도 우선": "high",
        "정밀 인식": "high",
        "정밀인식": "high",
        "높음": "high",
    }
    if not text:
        return normalize_mode(default, default="auto") if default != "" else "auto"
    return aliases.get(text, normalize_mode(default, default="auto") if text not in MODE_ORDER else text)


def mode_to_stt_quality(mode: Any) -> str:
    return MODE_TO_STT_QUALITY[normalize_mode(mode)]


def stt_quality_to_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in STT_QUALITY_TO_MODE:
        return STT_QUALITY_TO_MODE[text]
    return normalize_mode(text)


def mode_label(mode: Any) -> str:
    key = normalize_mode(mode)
    return MODE_LABELS[key]


def mode_items() -> list[tuple[str, str]]:
    return [(key, MODE_LABELS[key]) for key in MODE_ORDER]


def selected_mode_from_settings(settings: dict[str, Any] | None) -> str:
    data = dict(settings or {})
    for key in ("subtitle_mode", "mode", "user_facing_mode"):
        value = data.get(key)
        if str(value or "").strip():
            return normalize_mode(value)
    legacy_mode = str(data.get("simple_operation_mode") or "").strip()
    quality_value = data.get("stt_quality_preset") or data.get("auto_start_mode")
    quality_mode = stt_quality_to_mode(quality_value) if str(quality_value or "").strip() else ""
    if legacy_mode:
        normalized = normalize_mode(legacy_mode)
        # Older settings often stored simple_operation_mode=auto while the real
        # user quality choice lived in stt_quality_preset. Keep that choice when
        # no new subtitle_mode has been written yet.
        if normalized == "auto" and quality_mode in {"fast", "high"}:
            return quality_mode
        return normalized
    return stt_quality_to_mode(data.get("stt_quality_preset") or data.get("auto_start_mode") or "balanced")


def _llm_enabled(settings: dict[str, Any], *, prefix: str = "subtitle") -> bool:
    if prefix == "roughcut":
        if not _safe_bool(settings.get("roughcut_llm_enabled"), False):
            return False
        model = str(settings.get("roughcut_llm_model", "") or "").strip()
        provider = str(settings.get("roughcut_llm_provider", "") or "").strip().lower()
    else:
        model = str(settings.get("selected_model", "") or "").strip()
        provider = str(settings.get("selected_llm_provider", "ollama") or "ollama").strip().lower()
    if provider == "none":
        return False
    return bool(model and "사용 안함" not in model)


def _audio_value(settings: dict[str, Any], mode: str) -> tuple[str, str, str]:
    selected = str(settings.get("selected_audio_ai", "") or "").strip()
    if selected:
        return selected, "user-selected", f"사용자가 음성 모델 {selected}을 선택했습니다."
    if mode == "fast":
        return "none", "mode-selected", "Fast mode uses the lightest usable audio path."
    if mode == "high":
        return "sample-full", "sampling-selected", "High mode samples longer spans before choosing the audio filter."
    return "sample-short", "sampling-selected", "Auto mode samples representative audio before choosing the filter."


def _vad_value(settings: dict[str, Any], mode: str) -> tuple[str, str, str]:
    selected = str(settings.get("selected_vad", "") or "").strip()
    if selected:
        return selected, "user-selected", f"사용자가 VAD 모델 {selected}을 선택했습니다."
    if mode == "fast":
        return "silero-lite", "mode-selected", "Fast mode uses one lightweight VAD model."
    if mode == "high":
        return "dual-vad", "mode-selected", "High mode compares two VAD models where available."
    return "sampled-vad", "sampling-selected", "Auto mode compares VAD candidates on short sample spans."


def resolve_mode_policy(
    settings: dict[str, Any] | None = None,
    *,
    media_metadata: dict[str, Any] | None = None,
    resource_snapshot: dict[str, Any] | None = None,
    user_selected_models: dict[str, Any] | None = None,
    lora_available: bool | None = None,
    idle_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    mode = selected_mode_from_settings(settings)
    quality_key = mode_to_stt_quality(mode)
    label = mode_label(mode)
    tool_stack = _tool_stack_for_mode(mode)
    audio_value, audio_state, audio_reason = _audio_value(settings, mode)
    vad_value, vad_state, vad_reason = _vad_value(settings, mode)
    subtitle_llm_enabled = bool(tool_stack.get("llm")) and _llm_enabled(settings, prefix="subtitle")
    roughcut_llm_enabled = _llm_enabled(settings, prefix="roughcut")
    lora_ok = _safe_bool(lora_available, True)

    if mode == "fast":
        policy = {
            "cut_boundary": {
                "enabled": False,
                "audio_provisional_enabled": False,
                "level": "off",
                "state": "skipped",
                "value": "미사용",
                "reason": "Fast mode disables cut boundary detection.",
            },
            "preprocessing": {
                "sampling": "none",
                "state": "mode-selected",
                "value": "light",
                "reason": "Fast mode avoids expensive preflight sampling.",
            },
            "audio_filter": {"selected": audio_value, "state": audio_state, "reason": audio_reason},
            "vad": {"selected": vad_value, "state": vad_state, "dual": False, "reason": vad_reason},
            "stt": {
                "stt1_profile": "fast",
                "stt2_enabled": False,
                "speaker_diarization": False,
                "decoder": "safe-fast",
                "reason": "Fast mode forces STT2 off and uses safe fast decoder settings.",
            },
            "llm": {
                "subtitle_enabled": False,
                "subtitle_default": False,
                "lightweight_only": True,
                "roughcut_enabled": bool(roughcut_llm_enabled),
                "state": "skipped",
                "reason": "Fast mode is LoRA-only for subtitle post-processing; subtitle LLM is disabled.",
            },
            "lora": {
                "enabled": lora_ok,
                "buckets": ["high"],
                "min_score": 88.0,
                "state": "mode-selected" if lora_ok else "skipped",
                "reason": "Fast mode uses only high-confidence LoRA evidence.",
            },
            "deep_learning": {
                "enabled": False,
                "state": "skipped",
                "reason": "Fast mode disables heavy deep-learning validation.",
            },
            "scheduler": {
                "resource_start": "lite",
                "ramp_up": True,
                "ramp_down_on_input": True,
                "reason": "Fast mode starts with the smallest safe worker set.",
            },
            "cleanup": {
                "immediate": True,
                "cancel_prefetch": True,
                "release_models": True,
                "reason": "Fast mode returns UI control before deferred learning starts.",
            },
        }
    elif mode == "high":
        policy = {
            "cut_boundary": {
                "enabled": True,
                "audio_provisional_enabled": True,
                "level": "medium",
                "state": "mode-selected",
                "value": "중간",
                "reason": "High mode enables visual and provisional audio cut boundaries.",
            },
            "preprocessing": {
                "sampling": "long",
                "state": "sampling-selected",
                "value": "long/full",
                "reason": "High mode uses long sampling or full-media analysis.",
            },
            "audio_filter": {"selected": audio_value, "state": audio_state, "reason": audio_reason},
            "vad": {"selected": vad_value, "state": vad_state, "dual": True, "reason": vad_reason},
            "stt": {
                "stt1_profile": "high",
                "stt2_enabled": True,
                "speaker_diarization": True,
                "decoder": "precise",
                "reason": "High mode enables STT2, diarization, and precise decoder settings.",
            },
            "llm": {
                "subtitle_enabled": bool(subtitle_llm_enabled),
                "subtitle_default": True,
                "lightweight_only": False,
                "roughcut_enabled": bool(roughcut_llm_enabled),
                "state": "mode-selected" if subtitle_llm_enabled else "skipped",
                "reason": "High mode verifies uncertain output with LLM when available.",
            },
            "lora": {
                "enabled": lora_ok,
                "buckets": ["high", "medium", "low"],
                "min_score": 0.0,
                "state": "mode-selected" if lora_ok else "skipped",
                "reason": "High mode allows all LoRA quality buckets.",
            },
            "deep_learning": {
                "enabled": True,
                "state": "mode-selected",
                "reason": "High mode enables full deep-learning validation.",
            },
            "scheduler": {
                "resource_start": "full",
                "ramp_up": False,
                "ramp_down_on_input": True,
                "reason": "High mode starts with full usable resources.",
            },
            "cleanup": {
                "immediate": True,
                "cancel_prefetch": True,
                "release_models": True,
                "reason": "High mode releases heavy resources as soon as generation completes.",
            },
        }
    else:
        policy = {
            "cut_boundary": {
                "enabled": True,
                "audio_provisional_enabled": False,
                "level": "low",
                "state": "mode-selected",
                "value": "낮음",
                "reason": "Auto mode enables cut boundary detection with a lightweight first pass.",
            },
            "preprocessing": {
                "sampling": "short",
                "state": "sampling-selected",
                "value": "short sample",
                "reason": "Auto mode samples representative spans before escalating.",
            },
            "audio_filter": {"selected": audio_value, "state": audio_state, "reason": audio_reason},
            "vad": {"selected": vad_value, "state": vad_state, "dual": False, "reason": vad_reason},
            "stt": {
                "stt1_profile": "auto",
                "stt2_enabled": False,
                "speaker_diarization": False,
                "decoder": "adaptive",
                "reason": "Auto mode starts with STT1 and escalates uncertain spans only.",
            },
            "llm": {
                "subtitle_enabled": False,
                "subtitle_default": False,
                "lightweight_only": False,
                "roughcut_enabled": bool(roughcut_llm_enabled),
                "state": "skipped",
                "reason": "Auto mode stops at LoRA + Deep; subtitle LLM is reserved for High mode.",
            },
            "lora": {
                "enabled": lora_ok,
                "buckets": ["high", "medium"],
                "min_score": 58.0,
                "state": "sampling-selected" if lora_ok else "skipped",
                "reason": "Auto mode uses high/medium LoRA only when confidence gates find value.",
            },
            "deep_learning": {
                "enabled": True,
                "state": "sampling-selected",
                "reason": "Auto mode applies Deep after LoRA for uncertain STT, split, and timing decisions.",
            },
            "scheduler": {
                "resource_start": "lite",
                "ramp_up": True,
                "ramp_down_on_input": True,
                "reason": "Auto mode ramps resources gradually.",
            },
            "cleanup": {
                "immediate": True,
                "cancel_prefetch": True,
                "release_models": True,
                "reason": "Auto mode cleans up before Home-idle learning starts.",
            },
        }

    snapshot = {
        "schema": MODE_POLICY_SCHEMA,
        "mode": mode,
        "label": label,
        "stt_quality_preset": quality_key,
        "media": deepcopy(media_metadata or {}),
        "resource": deepcopy(resource_snapshot or {}),
        "user_selected_models": deepcopy(user_selected_models or {}),
        "idle_state": deepcopy(idle_state or {}),
        "subtitle_tool_stack": tool_stack,
        **policy,
    }
    snapshot["dashboard"] = build_engine_dashboard(snapshot)
    return snapshot


def build_engine_dashboard(
    policy: dict[str, Any] | None,
    *,
    active_stages: set[str] | list[str] | tuple[str, ...] | None = None,
    completed_stages: set[str] | list[str] | tuple[str, ...] | None = None,
    review_stages: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    policy = dict(policy or {})
    active = {str(item) for item in (active_stages or set())}
    completed = {str(item) for item in (completed_stages or set())}
    needs_review = {str(item) for item in (review_stages or set())}
    rows: list[dict[str, Any]] = []

    def section_for(step_key: str) -> dict[str, Any]:
        if step_key in {"stt1", "stt2"}:
            stt = dict(policy.get("stt") or {})
            if step_key == "stt2":
                enabled = _safe_bool(stt.get("stt2_enabled"), False)
                return {
                    "enabled": enabled,
                    "state": "mode-selected" if enabled else "skipped",
                    "value": "사용" if enabled else "미사용",
                    "reason": stt.get("reason", ""),
                }
            return {
                "enabled": True,
                "state": "mode-selected",
                "value": str(stt.get("stt1_profile") or policy.get("stt_quality_preset") or "auto"),
                "reason": stt.get("reason", ""),
            }
        if step_key == "subtitle_llm":
            llm = dict(policy.get("llm") or {})
            enabled = _safe_bool(llm.get("subtitle_enabled"), False)
            return {
                "enabled": enabled,
                "state": str(llm.get("state") or ("mode-selected" if enabled else "skipped")),
                "value": "사용" if enabled else "미사용",
                "reason": llm.get("reason", ""),
            }
        if step_key == "roughcut_llm":
            llm = dict(policy.get("llm") or {})
            enabled = _safe_bool(llm.get("roughcut_enabled"), False)
            return {
                "enabled": enabled,
                "state": "user-selected" if enabled else "skipped",
                "value": "사용" if enabled else "미사용",
                "reason": "러프컷 LLM은 사용자가 켠 경우에만 실행됩니다." if enabled else "러프컷 LLM is off.",
            }
        return dict(policy.get(step_key) or {})

    for index, (key, label) in enumerate(ENGINE_DASHBOARD_STEPS, start=1):
        section = section_for(key)
        state = str(section.get("state") or ("mode-selected" if section.get("enabled", True) else "skipped"))
        if key in completed:
            state = "complete"
        if key in active:
            state = "running"
        if key in needs_review:
            state = "needs-review"
        value = section.get("value", section.get("selected", section.get("level", "")))
        rows.append(
            {
                "index": index,
                "key": key,
                "label": label,
                "state": state,
                "value": str(value or ""),
                "reason": str(section.get("reason") or ""),
            }
        )
    return {
        "schema": MODE_DASHBOARD_SCHEMA,
        "mode": str(policy.get("mode") or "auto"),
        "label": str(policy.get("label") or mode_label(policy.get("mode"))),
        "steps": rows,
    }


def apply_mode_runtime_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    from core.audio.stt_quality_presets import apply_stt_quality_preset

    base = dict(settings or {})
    mode = selected_mode_from_settings(base)
    quality_key = mode_to_stt_quality(mode)
    base_model = str(base.get("selected_model", "") or "").strip()
    base_provider = str(base.get("selected_llm_provider", "") or "").strip()
    base_has_subtitle_llm = bool(base_model and "사용 안함" not in base_model)
    base_explicit_model = "selected_model" in base and base_has_subtitle_llm
    explicit_subtitle_llm = _safe_bool(base.get("subtitle_llm_user_selected"), False) or (
        base_has_subtitle_llm and "selected_llm_provider" not in base
    )
    out = apply_stt_quality_preset(base, quality_key)
    out["subtitle_mode"] = mode
    out["simple_operation_mode"] = mode
    out["stt_quality_preset"] = quality_key
    out["auto_start_mode"] = quality_key
    if mode == "high" and explicit_subtitle_llm and base_has_subtitle_llm:
        out["selected_model"] = base_model
        out["selected_llm_provider"] = base_provider or "ollama"
        out["subtitle_llm_user_selected"] = True

    if mode == "fast":
        out.update(
            {
                "editor_lora_runtime_enabled": True,
                "lora_pattern_first_enabled": True,
                "lora_pattern_query_compact_enabled": True,
                "cut_boundary_detection_enabled": False,
                "cut_boundary_enabled": False,
                "scan_cut_enabled": False,
                "scan_cut_auto_enabled": False,
                "cut_boundary_level": "off",
                "scan_cut_level": "off",
                "scan_cut_boundary_level": "off",
                "scan_cut_audio_gain_enabled": False,
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": False,
                "stt_low_score_recheck_enabled": True,
                "stt_low_score_recheck_threshold": 54,
                "stt_low_score_recheck_padding_sec": 0.35,
                "stt_low_score_recheck_max_segments": 16,
                "stt_selective_secondary_recheck_enabled": True,
                "stt_selective_secondary_recheck_reason": "Fast mode runs STT2 only on low-score STT1 spans.",
                "runtime_quality_self_review_enabled": False,
                "fast_hallucination_guard_enabled": True,
                "deep_subtitle_policy_enabled": False,
                "deep_segment_setting_policy_enabled": False,
                "deep_stt_candidate_selector_enabled": False,
                "deep_timing_adjustment_enabled": False,
                "subtitle_lora_quality_buckets": ["high"],
                "runtime_scheduler_ramp_up_enabled": True,
                "runtime_scheduler_ramp_initial_sec": 90.0,
                "background_prefetch_lora_enabled": False,
                "background_prefetch_candidates_enabled": False,
            }
        )
        _disable_subtitle_llm_settings(
            out,
            mode=mode,
            configured_model=base_model,
            configured_provider=base_provider,
            preserve_configured_model=base_explicit_model,
        )
    elif mode == "high":
        out.update(
            {
                "editor_lora_runtime_enabled": True,
                "lora_pattern_first_enabled": True,
                "lora_pattern_query_compact_enabled": True,
                "cut_boundary_detection_enabled": True,
                "cut_boundary_enabled": True,
                "scan_cut_enabled": True,
                "scan_cut_auto_enabled": True,
                "cut_boundary_level": "medium",
                "scan_cut_level": "medium",
                "scan_cut_boundary_level": "medium",
                "scan_cut_audio_gain_enabled": True,
                "stt_ensemble_enabled": True,
                "stt_ensemble_llm_judge_enabled": True,
                "runtime_quality_self_review_enabled": True,
                "fast_hallucination_guard_enabled": True,
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": True,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": True,
                "subtitle_llm_macro_chunk_enabled": True,
                "subtitle_llm_mode_disabled": False,
                "llm_confidence_gate_enabled": True,
                "llm_candidate_policy_enabled": True,
                "llm_minimize_enabled": True,
                "speaker_diarization_auto_enabled": True,
                "vad_dual_model_enabled": True,
                "subtitle_lora_quality_buckets": ["high", "medium", "low"],
                "runtime_scheduler_ramp_up_enabled": False,
            }
        )
        out["subtitle_llm_effective_model"] = str(out.get("selected_model", "") or "")
        out["subtitle_llm_runtime_enabled"] = bool(
            out["subtitle_llm_effective_model"] and "사용 안함" not in out["subtitle_llm_effective_model"]
        )
    else:
        out.update(
            {
                "editor_lora_runtime_enabled": True,
                "lora_pattern_first_enabled": True,
                "lora_pattern_query_compact_enabled": True,
                "cut_boundary_detection_enabled": True,
                "cut_boundary_enabled": True,
                "scan_cut_enabled": True,
                "scan_cut_auto_enabled": True,
                "cut_boundary_level": "low",
                "scan_cut_level": "low",
                "scan_cut_boundary_level": "low",
                "scan_cut_audio_gain_enabled": False,
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": True,
                "speaker_diarization_auto_enabled": False,
                "vad_dual_model_enabled": False,
                "runtime_quality_self_review_enabled": True,
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": True,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": True,
                "subtitle_lora_quality_buckets": ["high", "medium"],
                "runtime_scheduler_ramp_up_enabled": True,
                "runtime_scheduler_ramp_initial_sec": 45.0,
                "runtime_scheduler_ramp_step_sec": 60.0,
            }
        )
        _disable_subtitle_llm_settings(
            out,
            mode=mode,
            configured_model=base_model,
            configured_provider=base_provider,
            preserve_configured_model=base_explicit_model,
        )

    out["subtitle_tool_stack"] = _tool_stack_for_mode(mode)
    out["subtitle_tool_stack_label"] = out["subtitle_tool_stack"]["label"]
    out["subtitle_tool_stack_tools"] = list(out["subtitle_tool_stack"]["tools"])

    policy = resolve_mode_policy(out)
    out["mode_policy_snapshot"] = {
        key: deepcopy(value)
        for key, value in policy.items()
        if key not in {"media", "resource", "user_selected_models", "idle_state"}
    }
    out["engine_dashboard_snapshot"] = deepcopy(policy["dashboard"])
    return out


def preflight_mode_decision(
    features: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = dict(features or {})
    mode = selected_mode_from_settings(settings or {})
    noise = _safe_float(features.get("noise_level"), 0.0)
    speech_density = _safe_float(features.get("speech_density"), 0.5)
    silence_ratio = _safe_float(features.get("silence_ratio"), 0.5)
    cut_density = _safe_float(features.get("cut_density"), 0.0)
    stt_confidence = _safe_float(features.get("stt_confidence"), 0.0)
    lora_score = _safe_float(features.get("lora_match_confidence", features.get("lora_score")), 0.0)
    expected_cost = _safe_float(features.get("expected_model_cost"), 0.0)

    reasons: list[str] = []
    if stt_confidence >= 88.0 and noise <= 0.25 and cut_density <= 0.2:
        route = "fast_path"
        reasons.append("easy_media_high_stt_confidence")
    elif stt_confidence < 62.0 or noise >= 0.68 or cut_density >= 0.75:
        route = "high_validation"
        reasons.append("difficult_media_escalate")
    else:
        route = "selective_escalation"
        reasons.append("uncertain_media_sample_first")
    if mode == "fast":
        route = "fast_path" if route != "high_validation" else "fast_with_review_guard"
        reasons.append("user_mode_fast")
    elif mode == "high":
        route = "high_validation"
        reasons.append("user_mode_high")

    return {
        "schema": MODE_PREFLIGHT_SCHEMA,
        "mode": mode,
        "route": route,
        "reasons": reasons,
        "features": {
            "noise_level": round(noise, 4),
            "speech_density": round(speech_density, 4),
            "silence_ratio": round(silence_ratio, 4),
            "cut_density": round(cut_density, 4),
            "stt_confidence": round(stt_confidence, 4),
            "lora_match_confidence": round(lora_score, 4),
            "expected_model_cost": round(expected_cost, 4),
        },
    }


def dashboard_plain_lines(dashboard: dict[str, Any] | None) -> list[str]:
    rows = []
    for step in list((dashboard or {}).get("steps") or []):
        if not isinstance(step, dict):
            continue
        value = str(step.get("value") or "").strip()
        suffix = f" {value}" if value else ""
        rows.append(f"{int(step.get('index', 0) or 0)}. [{step.get('label', '')}] {step.get('state', '')}{suffix}".strip())
    return rows


__all__ = [
    "ENGINE_DASHBOARD_STEPS",
    "MODE_DASHBOARD_SCHEMA",
    "MODE_LABELS",
    "MODE_ORDER",
    "MODE_POLICY_SCHEMA",
    "MODE_TOOL_STACK_SCHEMA",
    "MODE_TOOL_STACKS",
    "MODE_PREFLIGHT_SCHEMA",
    "MODE_TO_STT_QUALITY",
    "apply_mode_runtime_settings",
    "build_engine_dashboard",
    "dashboard_plain_lines",
    "mode_items",
    "mode_label",
    "mode_to_stt_quality",
    "normalize_mode",
    "preflight_mode_decision",
    "resolve_mode_policy",
    "selected_mode_from_settings",
    "stt_quality_to_mode",
]
