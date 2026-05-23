"""User-facing Fast/Auto/High/STT mode policy.

The rest of the app still stores the historical STT quality keys in a few
places (`fast`, `balanced`, `precise`). This module is the compatibility layer:
UI and pipeline code can talk in Mode terms while existing project/settings
files continue to load without a schema break.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.mode_manager import (
    MODE_LABELS,
    MODE_ORDER,
    MODE_TO_STT_QUALITY,
    USER_SELECTABLE_MODEL_KEYS,
    apply_mode_scope_quality,
    mode_items,
    mode_label,
    mode_to_stt_quality,
    normalize_mode,
    selected_mode_from_settings,
    stt_quality_to_mode,
)
from core.native_macos_acceleration import mac_native_runtime_overrides
from core.audio.stt_quality_presets import mode_benchmark_locked_settings


MODE_POLICY_SCHEMA = "ai_subtitle_studio.mode_policy.v1"
MODE_DASHBOARD_SCHEMA = "ai_subtitle_studio.engine_dashboard.v1"
MODE_PREFLIGHT_SCHEMA = "ai_subtitle_studio.mode_preflight.v1"
MODE_TOOL_STACK_SCHEMA = "ai_subtitle_studio.subtitle_tool_stack.v1"

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
    "stt": {
        "label": "Human-input STT path",
        "tools": ["vad", "human_input", "lora", "deep_learning", "rules"],
        "lora": True,
        "deep_learning": True,
        "llm": False,
        "macro_llm": False,
        "reason": "STT mode uses VAD work segments plus human dictation, then LoRA/Deep/rules resegment without Whisper or LLM requirements.",
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


def mode_stt_support_flags(mode: Any) -> dict[str, bool]:
    """Return STT2/candidate-judge switches owned by the user-facing Mode."""
    key = normalize_mode(mode)
    ensemble_enabled = key in {"fast", "auto", "high"}
    llm_judge_enabled = key == "high"
    return {
        "stt_ensemble_enabled": ensemble_enabled,
        "stt_ensemble_llm_judge_enabled": llm_judge_enabled,
        "stt_ensemble_user_selected": False,
    }


def _apply_mode_stt_support_flags(out: dict[str, Any], mode: Any) -> None:
    out.update(mode_stt_support_flags(mode))


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
    allow_runtime: bool = False,
) -> None:
    has_configured_model = bool(configured_model and "사용 안함" not in configured_model)
    if preserve_configured_model and has_configured_model:
        out["selected_model"] = configured_model
        out["selected_llm_provider"] = configured_provider or "ollama"
        out["subtitle_llm_user_selected"] = True
        if allow_runtime:
            out.update(
                {
                    "subtitle_llm_runtime_enabled": True,
                    "subtitle_llm_mode_disabled": False,
                    "subtitle_llm_effective_model": configured_model,
                    "subtitle_llm_macro_chunk_enabled": False,
                    "llm_confidence_gate_enabled": False,
                    "llm_candidate_policy_enabled": False,
                    "llm_minimize_enabled": False,
                    "subtitle_tool_stack_reason": (
                        f"{mode_label(mode)} mode keeps the default lightweight route, "
                        "but a user-selected subtitle LLM override is enabled."
                    ),
                }
            )
            return
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


def _subtitle_llm_user_override_active(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    model = str(settings.get("selected_model", "") or "").strip()
    provider = str(settings.get("selected_llm_provider", "") or "").strip().lower()
    if not model or "사용 안함" in model or provider == "none":
        return False
    return _safe_bool(settings.get("subtitle_llm_user_selected"), False)


def _resolve_subtitle_llm_enabled(settings: dict[str, Any], tool_stack: dict[str, Any]) -> bool:
    runtime_enabled = settings.get("subtitle_llm_runtime_enabled", None)
    enabled = (
        bool(tool_stack.get("llm")) and _llm_enabled(settings, prefix="subtitle")
        if runtime_enabled is None
        else _safe_bool(runtime_enabled, False) and _llm_enabled(settings, prefix="subtitle")
    )
    if enabled and not bool(tool_stack.get("llm")):
        tool_stack["llm"] = True
        tool_stack["macro_llm"] = True
        if "llm" not in list(tool_stack.get("tools") or []):
            tool_stack["tools"] = [*list(tool_stack.get("tools") or []), "llm"]
    return enabled


def _fast_auto_llm_policy(mode: str, subtitle_enabled: bool, roughcut_enabled: bool) -> dict[str, Any]:
    fast = mode == "fast"
    default_reason = (
        "Fast mode is LoRA-only for subtitle post-processing; subtitle LLM is disabled."
        if fast
        else "Auto mode stops at LoRA + Deep; subtitle LLM is reserved for High mode."
    )
    override_reason = (
        "Fast mode keeps the default subtitle path on LoRA only, but the user-selected subtitle LLM override is active."
        if fast
        else "Auto mode keeps the default LoRA + Deep path, but the user-selected subtitle LLM override is active."
    )
    return {
        "subtitle_enabled": bool(subtitle_enabled),
        "subtitle_default": False,
        "lightweight_only": bool(fast),
        "roughcut_enabled": bool(roughcut_enabled),
        "state": "user-selected" if subtitle_enabled else "skipped",
        "reason": override_reason if subtitle_enabled else default_reason,
    }


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
        return selected, "mode-selected", f"{mode_label(mode)} mode applies benchmarked audio filter {selected}."
    if mode == "fast":
        return "none", "mode-selected", "Fast mode uses the lightest usable audio path."
    if mode == "stt":
        return "none", "mode-selected", "STT mode defaults to human/OS dictation input and does not require audio restoration."
    if mode == "high":
        return "sample-full", "sampling-selected", "High mode samples longer spans before choosing the audio filter."
    return "sample-short", "sampling-selected", "Auto mode samples representative audio before choosing the filter."


def _vad_value(settings: dict[str, Any], mode: str) -> tuple[str, str, str]:
    selected = str(settings.get("selected_vad", "") or "").strip()
    if selected:
        return selected, "mode-selected", f"{mode_label(mode)} mode applies benchmarked VAD model {selected}."
    if mode == "fast":
        return "silero-lite", "mode-selected", "Fast mode uses one lightweight VAD model."
    if mode == "stt":
        return "dual-vad", "mode-selected", "STT mode builds work segments from Silero + TEN VAD ensemble metadata."
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
    subtitle_llm_enabled = _resolve_subtitle_llm_enabled(settings, tool_stack)
    roughcut_llm_enabled = _llm_enabled(settings, prefix="roughcut")
    lora_ok = _safe_bool(lora_available, True)

    if mode == "stt":
        policy = {
            "stt_mode": {
                "enabled": True,
                "workflow": "human_input",
                "whisper_required": False,
                "vad_primary": True,
                "lora_resegment": True,
                "llm_used": False,
                "state": "mode-selected",
                "reason": "STT mode is a human-assisted subtitle input workflow.",
            },
            "cut_boundary": {
                "enabled": True,
                "audio_provisional_enabled": False,
                "level": "low",
                "state": "mode-selected",
                "value": "낮음",
                "reason": "STT mode respects cut boundaries while building human input work segments.",
            },
            "preprocessing": {
                "sampling": "vad-only",
                "state": "mode-selected",
                "value": "VAD",
                "reason": "STT mode prepares listenable work segments instead of automatic Whisper transcription.",
            },
            "audio_filter": {"selected": audio_value, "state": audio_state, "reason": audio_reason},
            "vad": {
                "selected": "dual-vad",
                "state": "mode-selected",
                "dual": True,
                "models": ["silero", "ten_vad"],
                "reason": vad_reason,
            },
            "stt": {
                "automatic_whisper_pipeline": False,
                "human_input_provider": "manual",
                "optional_mic_provider": True,
                "stt1_profile": "human_input",
                "stt2_enabled": False,
                "speaker_diarization": False,
                "decoder": "manual_dictation",
                "reason": "STT mode preserves raw human dictation and does not require Whisper.",
            },
            "llm": {
                "subtitle_enabled": False,
                "subtitle_default": False,
                "lightweight_only": False,
                "roughcut_enabled": False,
                "state": "skipped",
                "reason": "STT mode does not use LLM for text transformation.",
            },
            "lora": {
                "enabled": lora_ok,
                "stt_lora_enabled": True,
                "buckets": ["high", "medium"],
                "min_score": 58.0,
                "state": "mode-selected" if lora_ok else "skipped",
                "reason": "STT mode uses LoRA for raw dictation resegmentation, not speech recognition.",
            },
            "deep_learning": {
                "enabled": True,
                "state": "mode-selected",
                "reason": "STT mode uses Deep policy for subtitle split/timing patterns only.",
            },
            "scheduler": {
                "resource_start": "lite",
                "ramp_up": False,
                "ramp_down_on_input": True,
                "reason": "STT mode prioritizes immediate keyboard/dictation responsiveness.",
            },
            "cleanup": {
                "immediate": True,
                "cancel_prefetch": True,
                "release_models": True,
                "reason": "STT mode should keep heavy speech/LLM models unloaded by default.",
            },
        }
    elif mode == "fast":
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
                "stt2_enabled": True,
                "speaker_diarization": False,
                "decoder": "adaptive-fast",
                "reason": "Fast mode keeps Komix STT1 as the main route while checking short low-confidence spans with STT2.",
            },
            "llm": _fast_auto_llm_policy("fast", subtitle_llm_enabled, roughcut_llm_enabled),
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
                "reason": "Fast mode skips the heavy Deep selector stack and keeps only lightweight timing correction.",
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
                "speaker_diarization": False,
                "decoder": "precise",
                "reason": "High mode checks low-confidence, missing, and borderline spans with a wider STT2 budget.",
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
                "buckets": ["high"],
                "min_score": 88.0,
                "state": "mode-selected" if lora_ok else "skipped",
                "reason": "High mode keeps only the high-confidence LoRA bucket from the Tiniping benchmark winners.",
            },
            "deep_learning": {
                "enabled": True,
                "state": "mode-selected",
                "reason": "High mode enables selector-focused Deep validation before LLM review.",
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
                "stt2_enabled": True,
                "speaker_diarization": False,
                "decoder": "adaptive",
                "reason": "Auto mode uses STT1 first, then applies broader selective STT2 rescue and Deep output selection on uncertain spans.",
            },
            "llm": _fast_auto_llm_policy("auto", subtitle_llm_enabled, roughcut_llm_enabled),
            "lora": {
                "enabled": lora_ok,
                "buckets": ["high"],
                "min_score": 88.0,
                "state": "sampling-selected" if lora_ok else "skipped",
                "reason": "Auto mode keeps only the high-confidence LoRA bucket that survived the Tiniping benchmark sweep.",
            },
            "deep_learning": {
                "enabled": True,
                "state": "sampling-selected",
                "reason": "Auto mode applies selector-focused Deep after LoRA for uncertain STT, split, and timing decisions.",
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

    stt_vad_model_enabled = _safe_bool(settings.get("stt_vad_segment_model_enabled"), True)
    apply_key = f"stt_vad_segment_model_apply_{mode}_mode"
    stt_vad_model_applies = (
        mode in {"fast", "auto", "high"}
        and stt_vad_model_enabled
        and _safe_bool(settings.get(apply_key), True)
    )
    policy["stt_vad_segment_model"] = {
        "enabled": stt_vad_model_enabled,
        "apply_to_current_mode": bool(stt_vad_model_applies),
        "allowed_scope": "vad_boundary_selection",
        "state": "optional-enabled" if stt_vad_model_applies else "skipped",
        "reason": "STT-learned VAD boundary model may be shared with automatic modes, but only for boundary selection.",
    }
    policy["stt_dictation_lora"] = {
        "apply_to_auto_modes": _safe_bool(settings.get("stt_dictation_lora_apply_to_auto_modes"), False),
        "active": bool(mode == "stt"),
        "reason": "Human dictation resegmentation LoRA is reserved for STT Mode by default.",
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
            if _safe_bool(policy.get("stt_mode", {}).get("enabled"), False) and not _safe_bool(stt.get("automatic_whisper_pipeline"), True):
                return {
                    "enabled": False,
                    "state": "skipped",
                    "value": "수동 입력" if step_key == "stt1" else "미사용",
                    "reason": stt.get("reason", "STT mode does not require Whisper."),
                }
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
    explicit_subtitle_llm = _subtitle_llm_user_override_active(base)
    use_saved_quality_preset = not _safe_bool(base.get("_ignore_saved_quality_preset_once"), False)
    out = (
        dict(base)
        if mode == "stt"
        else apply_stt_quality_preset(
            base,
            quality_key,
            use_saved_user_preset=use_saved_quality_preset,
            preserve_user_routes=True,
        )
    )
    out.pop("_ignore_saved_quality_preset_once", None)
    out = apply_mode_scope_quality(out, mode)
    out.update(mode_benchmark_locked_settings(quality_key if mode != "stt" else "stt"))
    for route_key in USER_SELECTABLE_MODEL_KEYS:
        if route_key in base and base.get(route_key) not in (None, ""):
            out[route_key] = deepcopy(base[route_key])
    if mode == "high" and explicit_subtitle_llm and base_has_subtitle_llm:
        out["selected_model"] = base_model
        out["selected_llm_provider"] = base_provider or "ollama"
        out["subtitle_llm_user_selected"] = True

    if mode == "stt":
        out.update(
            {
                "stt_mode_enabled": True,
                "stt_mode_text_input_provider": str(base.get("stt_mode_text_input_provider") or "manual"),
                "stt_mode_allow_os_dictation": True,
                "stt_mode_allow_desktop_mic_optional": True,
                "stt_mode_require_whisper": False,
                "stt_mode_use_whisper_for_dictation": False,
                "stt_mode_use_llm": False,
                "stt_mode_vad_models": ["silero", "ten_vad"],
                "stt_mode_vad_ensemble_enabled": True,
                "stt_mode_lora_resegment_enabled": True,
                "stt_mode_rolling_window_size": 2,
                "stt_mode_project_compat_enabled": True,
                "automatic_whisper_pipeline": False,
                "selected_model": "사용 안함 (STT 모드)",
                "selected_llm_provider": "none",
                "selected_audio_ai": "none",
                "subtitle_llm_user_selected": False,
                "subtitle_llm_runtime_enabled": False,
                "subtitle_llm_mode_disabled": True,
                "subtitle_llm_effective_model": "사용 안함 (STT 모드)",
                "subtitle_llm_macro_chunk_enabled": False,
                "llm_confidence_gate_enabled": False,
                "llm_candidate_policy_enabled": False,
                "llm_minimize_enabled": False,
                "roughcut_llm_enabled": False,
                "roughcut_llm_use_override": False,
                "roughcut_llm_provider": "none",
                "roughcut_llm_model": "사용 안함",
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": False,
                "stt_ensemble_llm_judge_require_risk": True,
                "stt_ensemble_llm_judge_local_only": True,
                "stt_ensemble_llm_judge_low_score_threshold": 78.0,
                "stt_ensemble_llm_judge_min_score_delta": 10.0,
                "stt_ensemble_llm_judge_max_similarity": 0.94,
                "speaker_diarization_auto_enabled": True,
                "vad_dual_model_enabled": True,
                "editor_lora_runtime_enabled": True,
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": True,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": True,
                "subtitle_lora_quality_buckets": ["high", "medium"],
                "runtime_scheduler_ramp_up_enabled": False,
                "background_prefetch_lora_enabled": False,
                "background_prefetch_candidates_enabled": False,
            }
        )
    elif mode == "fast":
        out.update(
            {
                "scan_cut_audio_gain_enabled": False,
                "stt_recheck_native_fast_audio_filter_enabled": True,
                "stt_persistent_runtime_reuse_enabled": True,
                "stt_missing_voice_min_duration_sec": 0.55,
                "stt_selective_secondary_recheck_reason": "Fast mode checks short low-confidence spans with STT2 while keeping STT1 as the main route.",
            }
        )
        _disable_subtitle_llm_settings(
            out,
            mode=mode,
            configured_model=base_model,
            configured_provider=base_provider,
            preserve_configured_model=base_explicit_model,
            allow_runtime=explicit_subtitle_llm,
        )
    elif mode == "high":
        out.update(
            {
                "scan_cut_audio_gain_enabled": True,
                "stt_recheck_native_fast_audio_filter_enabled": True,
                "stt_persistent_runtime_reuse_enabled": True,
                "stt_missing_voice_min_duration_sec": 0.55,
                "runtime_scheduler_ramp_up_enabled": False,
            }
        )
        _apply_mode_stt_support_flags(out, mode)
        out["subtitle_llm_effective_model"] = str(out.get("selected_model", "") or "")
        out["subtitle_llm_runtime_enabled"] = bool(
            out["subtitle_llm_effective_model"] and "사용 안함" not in out["subtitle_llm_effective_model"]
        )
    else:
        out.update(
            {
                "scan_cut_audio_gain_enabled": False,
                "stt_recheck_native_fast_audio_filter_enabled": True,
                "stt_persistent_runtime_reuse_enabled": True,
                "runtime_scheduler_ramp_up_enabled": True,
            }
        )
        _apply_mode_stt_support_flags(out, mode)
        _disable_subtitle_llm_settings(
            out,
            mode=mode,
            configured_model=base_model,
            configured_provider=base_provider,
            preserve_configured_model=base_explicit_model,
            allow_runtime=explicit_subtitle_llm,
        )

    out["subtitle_tool_stack"] = _tool_stack_for_mode(mode)
    out["subtitle_tool_stack_label"] = out["subtitle_tool_stack"]["label"]
    out["subtitle_tool_stack_tools"] = list(out["subtitle_tool_stack"]["tools"])
    out.update(
        {
            "stt_backend_policy": "native",
            "audio_extract_backend_policy": "native",
            "cut_boundary_backend_policy": "native",
            "editor_render_backend_policy": "native",
            "whisperkit_native_auto_enabled": True,
            "macos_native_fast_audio_flatten_enabled": True,
            "macos_native_fast_audio_flatten_hp": 150,
            "macos_native_fast_audio_flatten_lp": 4600,
            "macos_native_fast_audio_flatten_comp_th": -24,
            "macos_native_fast_audio_flatten_volume": 3.2,
            "macos_native_fast_audio_flatten_limiter": 0.93,
            "macos_native_app_store_target_enabled": True,
            "macos_native_require_xcode_tools": True,
            "direct_ffmpeg_chunk_min_sec": 1.0,
            "clearvoice_native_ffmpeg_enabled": True,
        }
    )
    out.update(mac_native_runtime_overrides(out))
    _apply_mode_stt_support_flags(out, mode)

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
    elif mode == "stt":
        route = "stt_human_input"
        reasons.append("user_mode_stt")

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
    "mode_stt_support_flags",
    "mode_to_stt_quality",
    "normalize_mode",
    "preflight_mode_decision",
    "resolve_mode_policy",
    "selected_mode_from_settings",
    "stt_quality_to_mode",
]
