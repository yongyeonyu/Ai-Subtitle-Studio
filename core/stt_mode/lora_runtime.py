from __future__ import annotations

"""Runtime builders for the dedicated STT-mode LoRA/policy bundle."""

import os
import re
from collections import Counter
from typing import Any

from core.audio.stt_quality_presets import normalize_stt_quality_key, stt_quality_label
from core.runtime import config
from core.stt_mode.lora_bundle import export_stt_lora_bundle
from core.stt_mode.settings import setting_bool, setting_float, setting_int, stt_settings


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_+#./-]{1,31}")


def _safe_text(value: Any) -> str:
    return str(value or "").replace("\u2028", "\n").strip()


def _slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", str(value or "").strip()).strip("._-")
    return text[:80] or "stt_mode"


def _iter_text_rows(*row_groups: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for rows in row_groups:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            text = _safe_text(row.get("text") or row.get("raw_text") or row.get("dictated_text"))
            if text:
                out.append(text)
    return out


def _iterable_count(values: Any) -> int:
    if values is None:
        return 0
    try:
        return len(values)
    except TypeError:
        return sum(1 for _item in values)


def collect_stt_protected_terms(
    *,
    settings: dict[str, Any] | None = None,
    raw_segments: list[dict[str, Any]] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
) -> list[str]:
    base_terms = list(stt_settings(settings).get("stt_lora_protected_terms") or [])
    texts = _iter_text_rows(raw_segments, final_segments)
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(token for token in _TOKEN_RE.findall(text) if len(token) >= 2)

    discovered: list[str] = []
    for token, freq in counts.most_common():
        if len(discovered) >= 96:
            break
        keep = False
        if any(ch.isdigit() for ch in token):
            keep = True
        elif any("A" <= ch <= "Z" for ch in token):
            keep = True
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_+#./-]{1,31}", token):
            keep = True
        elif freq >= 2 and (len(token) >= 3 or re.search(r"[가-힣]", token)):
            keep = True
        if keep:
            discovered.append(token)

    merged: list[str] = []
    seen: set[str] = set()
    for token in [*base_terms, *discovered]:
        text = str(token or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def build_stt_dictation_resegment_policy(
    *,
    settings: dict[str, Any] | None = None,
    raw_segments: list[dict[str, Any]] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
    learning_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = stt_settings(settings)
    protected_terms = collect_stt_protected_terms(
        settings=cfg,
        raw_segments=raw_segments,
        final_segments=final_segments,
    )
    return {
        "mode": "stt",
        "quality_preset": normalize_stt_quality_key(cfg.get("stt_quality_preset") or "stt"),
        "quality_label": stt_quality_label(cfg.get("stt_quality_preset") or "stt"),
        "target_chars_per_line": setting_int(cfg, "stt_mode_target_chars_per_line", 12),
        "max_lines": setting_int(cfg, "stt_mode_max_lines", 2),
        "min_subtitle_duration_sec": setting_float(cfg, "stt_mode_min_subtitle_duration_sec", 0.6),
        "max_subtitle_duration_sec": setting_float(cfg, "stt_mode_max_subtitle_duration_sec", 5.5),
        "rolling_window_size": setting_int(cfg, "stt_mode_rolling_window_size", 2),
        "respect_cut_boundaries": setting_bool(cfg, "stt_mode_respect_cut_boundaries", True),
        "balance_by_text_length": setting_bool(cfg, "stt_mode_balance_by_text_length", True),
        "netflix_style_enabled": setting_bool(cfg, "stt_mode_netflix_style_enabled", True),
        "protected_terms": protected_terms,
        "learning_event_count": _iterable_count(learning_events),
    }


def build_stt_subtitle_style_policy(
    *,
    settings: dict[str, Any] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
    raw_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = stt_settings(settings)
    texts = _iter_text_rows(final_segments, raw_segments)
    line_counts = [max(1, text.count("\n") + 1) for text in texts if text]
    avg_lines = round(sum(line_counts) / len(line_counts), 2) if line_counts else 1.0
    avg_chars = round(
        sum(len(text.replace("\n", "")) for text in texts if text) / max(1, len(texts)),
        2,
    ) if texts else 0.0
    return {
        "target_chars_per_line": setting_int(cfg, "stt_mode_target_chars_per_line", 12),
        "max_lines": setting_int(cfg, "stt_mode_max_lines", 2),
        "netflix_style_enabled": setting_bool(cfg, "stt_mode_netflix_style_enabled", True),
        "observed_average_lines": avg_lines,
        "observed_average_chars": avg_chars,
        "protected_terms": collect_stt_protected_terms(
            settings=cfg,
            raw_segments=raw_segments,
            final_segments=final_segments,
        ),
    }


def build_stt_vad_segment_model(
    *,
    settings: dict[str, Any] | None = None,
    work_segments: list[dict[str, Any]] | None = None,
    learning_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = stt_settings(settings)
    rows = [dict(row) for row in work_segments or [] if isinstance(row, dict)]
    confidence_counts = Counter(
        str(row.get("vad_confidence_label") or "").strip().lower()
        for row in rows
        if row.get("vad_confidence_label")
    )
    return {
        "vad_models": list(cfg.get("stt_mode_vad_models") or ["silero", "ten_vad"]),
        "vad_ensemble_enabled": setting_bool(cfg, "stt_mode_vad_ensemble_enabled", True),
        "merge_gap_sec": setting_float(cfg, "stt_mode_merge_gap_sec", 0.35),
        "min_work_segment_sec": setting_float(cfg, "stt_mode_min_work_segment_sec", 0.45),
        "target_work_segment_sec": setting_float(cfg, "stt_mode_target_work_segment_sec", 4.0),
        "max_work_segment_sec": setting_float(cfg, "stt_mode_max_work_segment_sec", 9.0),
        "work_segment_count": len(rows),
        "confidence_counts": dict(confidence_counts),
        "learning_event_count": _iterable_count(learning_events),
    }


def export_stt_runtime_bundle(
    *,
    project_path: str = "",
    media_path: str = "",
    settings: dict[str, Any] | None = None,
    work_segments: list[dict[str, Any]] | None = None,
    raw_segments: list[dict[str, Any]] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
    learning_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = stt_settings(settings)
    if not setting_bool(cfg, "stt_lora_bundle_auto_export_enabled", True):
        return {}

    bundle_base = os.path.splitext(os.path.basename(project_path or media_path or "stt_mode"))[0]
    bundle_id = f"{_slug(bundle_base)}_stt_lora"
    size_tier = str(cfg.get("stt_lora_bundle_size_tier") or "300MB")
    runtime_bundle = build_stt_runtime_policy_bundle(
        settings=cfg,
        work_segments=work_segments,
        raw_segments=raw_segments,
        final_segments=final_segments,
        learning_events=learning_events,
        bundle_id=bundle_id,
    )
    bundle = export_stt_lora_bundle(
        output_dir=os.path.join(config.OUTPUT_DIR, "stt_lora_bundles"),
        bundle_id=bundle_id,
        size_tier=size_tier,
        stt_dictation_resegment_policy=runtime_bundle["stt_dictation_resegment_policy"],
        stt_vad_segment_model=runtime_bundle["stt_vad_segment_model"],
        subtitle_style_policy=runtime_bundle["subtitle_style_policy"],
        protected_terms=list(runtime_bundle["stt_dictation_resegment_policy"].get("protected_terms") or []),
        zip_output=False,
    )
    runtime_bundle.update(bundle)
    return runtime_bundle


def build_stt_runtime_policy_bundle(
    *,
    settings: dict[str, Any] | None = None,
    work_segments: list[dict[str, Any]] | None = None,
    raw_segments: list[dict[str, Any]] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
    learning_events: list[dict[str, Any]] | None = None,
    bundle_id: str = "stt_lora_runtime",
) -> dict[str, Any]:
    cfg = stt_settings(settings)
    dictation_policy = build_stt_dictation_resegment_policy(
        settings=cfg,
        raw_segments=raw_segments,
        final_segments=final_segments,
        learning_events=learning_events,
    )
    style_policy = build_stt_subtitle_style_policy(
        settings=cfg,
        final_segments=final_segments,
        raw_segments=raw_segments,
    )
    vad_model = build_stt_vad_segment_model(
        settings=cfg,
        work_segments=work_segments,
        learning_events=learning_events,
    )
    return {
        "bundle_id": bundle_id,
        "adapter_refs": {
            "stt_lora_bundle": bundle_id,
            "stt_vad_segment_model": f"{bundle_id}:stt_vad_segment_model",
            "stt_dictation_resegment": f"{bundle_id}:stt_dictation_resegment",
            "subtitle_style_policy": f"{bundle_id}:subtitle_style_policy",
        },
        "stt_dictation_resegment_policy": dictation_policy,
        "stt_vad_segment_model": vad_model,
        "subtitle_style_policy": style_policy,
    }


__all__ = [
    "build_stt_dictation_resegment_policy",
    "build_stt_subtitle_style_policy",
    "build_stt_vad_segment_model",
    "build_stt_runtime_policy_bundle",
    "collect_stt_protected_terms",
    "export_stt_runtime_bundle",
]
