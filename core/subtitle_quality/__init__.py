# Version: 03.01.25
# Phase: PHASE2
"""Subtitle quality review helpers.

This package is intentionally separate from the existing STT and subtitle
engines so quality review can stay opt-in and non-destructive.
"""

from .models import (
    ASR_METADATA_FIELDS,
    QualityCandidate,
    QualityPipelineResult,
    SubtitleQualityMetrics,
    SubtitleQualitySummary,
    attach_asr_metadata,
    metrics_from_dict,
    metrics_to_dict,
    normalize_asr_metadata,
    normalize_segment_quality,
)
from .hallucination_detector import annotate_segment_hallucination_risk, estimate_hallucination_risk
from .llm_guarded_corrector import build_conservative_prompt
from .vad_alignment_checker import (
    annotate_segment_vad_alignment,
    annotate_segments_vad_alignment,
    vad_alignment_info,
    vad_overlap_ratio,
)
from .confidence_checker import evaluate_subtitle_confidence
from .quality_pipeline import run_subtitle_quality_pipeline
from .recheck_engine import recheck_low_confidence_segments

__all__ = [
    "ASR_METADATA_FIELDS",
    "QualityCandidate",
    "QualityPipelineResult",
    "SubtitleQualityMetrics",
    "SubtitleQualitySummary",
    "attach_asr_metadata",
    "metrics_from_dict",
    "metrics_to_dict",
    "normalize_asr_metadata",
    "normalize_segment_quality",
    "annotate_segment_hallucination_risk",
    "annotate_segment_vad_alignment",
    "annotate_segments_vad_alignment",
    "build_conservative_prompt",
    "estimate_hallucination_risk",
    "evaluate_subtitle_confidence",
    "run_subtitle_quality_pipeline",
    "recheck_low_confidence_segments",
    "vad_alignment_info",
    "vad_overlap_ratio",
]
