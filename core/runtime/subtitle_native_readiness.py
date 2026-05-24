from __future__ import annotations

"""Native subtitle helper readiness contracts.

This module is intentionally metadata-only: it does not enable native helpers.
It records which stable compute helpers are allowed, which feature flag gates
them, and what Python fallback must remain available.
"""

from dataclasses import asdict, dataclass


SUBTITLE_NATIVE_READINESS_SCHEMA = "ai_subtitle_studio.subtitle_native_readiness.v1"


@dataclass(frozen=True)
class SubtitleNativeHelperContract:
    helper: str
    domain: str
    module: str
    env_flag: str
    build_flag: str
    accelerator: str
    fallback: str
    parity_guard: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


_HELPERS: tuple[SubtitleNativeHelperContract, ...] = (
    SubtitleNativeHelperContract(
        helper="subtitle_segments_summary",
        domain="subtitle_segments",
        module="core.native_subtitle_segments",
        env_flag="AI_SUBTITLE_NATIVE_SEGMENTS",
        build_flag="AI_SUBTITLE_NATIVE_SEGMENTS_BUILD",
        accelerator="cpp_cpu",
        fallback="python_segment_summary",
        parity_guard="tests/test_native_subtitle_segments.py",
    ),
    SubtitleNativeHelperContract(
        helper="subtitle_stt_segments_summary",
        domain="subtitle_stt_segments",
        module="core.native_subtitle_stt_segments",
        env_flag="AI_SUBTITLE_NATIVE_STT_SEGMENTS",
        build_flag="AI_SUBTITLE_NATIVE_STT_SEGMENTS_BUILD",
        accelerator="cpp_cpu",
        fallback="python_stt_segments_summary",
        parity_guard="tests/test_native_subtitle_stt_segments.py",
    ),
    SubtitleNativeHelperContract(
        helper="subtitle_timing_metrics",
        domain="subtitle_timing",
        module="core.native_subtitle_timing",
        env_flag="AI_SUBTITLE_NATIVE_TIMING_METRICS",
        build_flag="AI_SUBTITLE_NATIVE_TIMING_METRICS_BUILD",
        accelerator="cpp_cpu",
        fallback="python_benchmark_metrics",
        parity_guard="tests/test_native_subtitle_timing.py",
    ),
    SubtitleNativeHelperContract(
        helper="subtitle_global_canvas_summary",
        domain="subtitle_global_canvas",
        module="core.native_subtitle_global_canvas",
        env_flag="AI_SUBTITLE_NATIVE_GLOBAL_CANVAS",
        build_flag="AI_SUBTITLE_NATIVE_GLOBAL_CANVAS_BUILD",
        accelerator="cpp_cpu",
        fallback="python_global_canvas_summary",
        parity_guard="tests/test_native_subtitle_global_canvas.py",
    ),
    SubtitleNativeHelperContract(
        helper="subtitle_waveform_summary",
        domain="subtitle_waveform",
        module="core.native_subtitle_waveform",
        env_flag="AI_SUBTITLE_NATIVE_WAVEFORM",
        build_flag="AI_SUBTITLE_NATIVE_WAVEFORM_BUILD",
        accelerator="cpp_cpu",
        fallback="python_waveform_path",
        parity_guard="tests/test_native_subtitle_waveform.py",
    ),
    SubtitleNativeHelperContract(
        helper="subtitle_resource_summary",
        domain="subtitle_resource_manager",
        module="core.native_subtitle_resource",
        env_flag="AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY",
        build_flag="AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY_BUILD",
        accelerator="cpp_cpu",
        fallback="python_resource_plan",
        parity_guard="tests/test_native_subtitle_resource.py",
    ),
)


def subtitle_native_helper_manifest() -> dict[str, object]:
    return {
        "schema": SUBTITLE_NATIVE_READINESS_SCHEMA,
        "helpers": [helper.as_dict() for helper in _HELPERS],
    }


def subtitle_native_helper_by_domain() -> dict[str, list[dict[str, str]]]:
    by_domain: dict[str, list[dict[str, str]]] = {}
    for helper in _HELPERS:
        by_domain.setdefault(helper.domain, []).append(helper.as_dict())
    return by_domain


def subtitle_native_readiness_summary() -> dict[str, object]:
    helpers = [helper.as_dict() for helper in _HELPERS]
    return {
        "schema": SUBTITLE_NATIVE_READINESS_SCHEMA,
        "helper_count": len(helpers),
        "domains": sorted({helper["domain"] for helper in helpers}),
        "feature_flags": sorted({helper["env_flag"] for helper in helpers}),
        "accelerators": sorted({helper["accelerator"] for helper in helpers}),
        "helpers": helpers,
    }


__all__ = [
    "SUBTITLE_NATIVE_READINESS_SCHEMA",
    "SubtitleNativeHelperContract",
    "subtitle_native_helper_by_domain",
    "subtitle_native_helper_manifest",
    "subtitle_native_readiness_summary",
]
