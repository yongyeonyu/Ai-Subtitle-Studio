from unittest.mock import patch

from core.native_subtitle_global_canvas import global_canvas_summary
from core.native_subtitle_segments import segment_summary
from core.native_subtitle_stt_segments import stt_segments_summary
from core.native_subtitle_timing import subtitle_timing_backend, timing_metrics
from core.native_subtitle_waveform import downsample_f32le
from core.runtime.subtitle_native_readiness import (
    SUBTITLE_NATIVE_READINESS_SCHEMA,
    subtitle_native_helper_by_domain,
    subtitle_native_readiness_summary,
)


def test_native_readiness_manifest_lists_feature_flagged_cpu_helpers_only():
    summary = subtitle_native_readiness_summary()

    assert summary["schema"] == SUBTITLE_NATIVE_READINESS_SCHEMA
    assert summary["helper_count"] >= 6
    assert "cpp_cpu" in summary["accelerators"]
    assert not any("ane" in accelerator.lower() for accelerator in summary["accelerators"])
    assert {
        "AI_SUBTITLE_NATIVE_SEGMENTS",
        "AI_SUBTITLE_NATIVE_STT_SEGMENTS",
        "AI_SUBTITLE_NATIVE_TIMING_METRICS",
        "AI_SUBTITLE_NATIVE_GLOBAL_CANVAS",
        "AI_SUBTITLE_NATIVE_WAVEFORM",
        "AI_SUBTITLE_NATIVE_RESOURCE_SUMMARY",
    }.issubset(set(summary["feature_flags"]))


def test_native_readiness_manifest_covers_extracted_facade_domains():
    by_domain = subtitle_native_helper_by_domain()

    for domain in (
        "subtitle_segments",
        "subtitle_stt_segments",
        "subtitle_timing",
        "subtitle_global_canvas",
        "subtitle_waveform",
        "subtitle_resource_manager",
    ):
        assert domain in by_domain
        assert by_domain[domain][0]["fallback"].startswith("python_")
        assert by_domain[domain][0]["parity_guard"].startswith("tests/test_native_")


def test_native_feature_flags_off_keep_python_fallbacks_available():
    env_off = {
        "AI_SUBTITLE_NATIVE_SEGMENTS": "0",
        "AI_SUBTITLE_NATIVE_STT_SEGMENTS": "0",
        "AI_SUBTITLE_NATIVE_TIMING_METRICS": "0",
        "AI_SUBTITLE_NATIVE_GLOBAL_CANVAS": "0",
        "AI_SUBTITLE_NATIVE_WAVEFORM": "0",
    }
    rows = [
        {"start": 0.0, "end": 1.0, "text": "첫 자막", "stt_preview_source": "STT1"},
        {"start": 1.2, "end": 2.0, "text": "둘째 자막", "stt_preview_source": "STT2"},
    ]

    with patch.dict("os.environ", env_off, clear=False):
        segment = segment_summary(rows)
        stt = stt_segments_summary(rows)
        canvas = global_canvas_summary(rows, duration=2.0, bin_count=4)

        assert segment["native_backend"] == "python"
        assert segment["stable_for_save_reopen"]
        assert stt["native_backend"] == "python"
        assert stt["stable_for_timeline_feed"]
        assert canvas["native_backend"] == "python"
        assert canvas["stable_for_global_canvas"]
        assert subtitle_timing_backend() == "python"
        assert timing_metrics(rows, rows) is None
        assert downsample_f32le(b"\0" * 16, sample_rate=4, points_per_second=2, duration=1.0) is None
