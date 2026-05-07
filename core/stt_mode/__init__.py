# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""UI-independent STT Mode schemas and helpers."""
from __future__ import annotations

from .models import (
    FINAL_SUBTITLE_SOURCE,
    FINAL_SUBTITLE_STATUS,
    RAW_DICTATION_SOURCE,
    RAW_DICTATION_STATUS,
    STT_LORA_BUNDLE_SCHEMA,
    STT_MODE_LEARNING_SCHEMA,
    STT_MODE_STATE_SCHEMA,
    STT_WORK_SEGMENT_SOURCE,
    STT_WORK_STATUS,
    build_frame_range,
    canonical_frame_timing,
)
from .dictation_state import create_raw_dictation_segment, upsert_raw_dictation
from .export_preflight import exportable_stt_segments, run_stt_export_preflight
from .finalizer import resegment_raw_dictation_window
from .project_state import (
    attach_stt_mode_state,
    build_stt_mode_state,
    project_stt_mode_learning,
    project_stt_mode_state,
)
from .rolling_resegment import apply_rolling_resegmentation, build_rolling_window
from .segment_builder import build_stt_work_segments
from .status import format_stt_status
from .vad_ensemble import ensemble_vad_candidates
from .lora_runtime import (
    build_stt_dictation_resegment_policy,
    build_stt_subtitle_style_policy,
    build_stt_vad_segment_model,
    collect_stt_protected_terms,
    export_stt_runtime_bundle,
)

__all__ = [
    "FINAL_SUBTITLE_SOURCE",
    "FINAL_SUBTITLE_STATUS",
    "RAW_DICTATION_SOURCE",
    "RAW_DICTATION_STATUS",
    "STT_LORA_BUNDLE_SCHEMA",
    "STT_MODE_LEARNING_SCHEMA",
    "STT_MODE_STATE_SCHEMA",
    "STT_WORK_SEGMENT_SOURCE",
    "STT_WORK_STATUS",
    "build_frame_range",
    "canonical_frame_timing",
    "apply_rolling_resegmentation",
    "attach_stt_mode_state",
    "build_rolling_window",
    "build_stt_mode_state",
    "build_stt_work_segments",
    "build_stt_dictation_resegment_policy",
    "build_stt_subtitle_style_policy",
    "build_stt_vad_segment_model",
    "collect_stt_protected_terms",
    "create_raw_dictation_segment",
    "ensemble_vad_candidates",
    "exportable_stt_segments",
    "export_stt_runtime_bundle",
    "format_stt_status",
    "project_stt_mode_learning",
    "project_stt_mode_state",
    "resegment_raw_dictation_window",
    "run_stt_export_preflight",
    "upsert_raw_dictation",
]
