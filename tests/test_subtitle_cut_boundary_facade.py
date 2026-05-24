from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core.engine.subtitle_cut_boundary import (
    SUBTITLE_CUT_BOUNDARY_FACADE_SCHEMA,
    subtitle_cut_boundary_cache_payload,
    subtitle_cut_boundary_settings_payload,
    summarize_subtitle_cut_boundary_cache_plan,
    truthy_setting,
)
from core.pipeline.cut_boundary_cache import (
    cut_boundary_cache_base_payload,
    cut_boundary_cache_settings_payload,
)


def test_subtitle_cut_boundary_settings_payload_keeps_cache_contract():
    settings = {
        "cut_boundary_media_duration_sec": 701.0,
        "cut_boundary_level": "high",
        "scan_cut_threshold": 31.5,
        "scan_cut_realtime_preview_enabled": "auto",
        "scan_cut_audio_gain_enabled": False,
    }

    payload = subtitle_cut_boundary_settings_payload(settings)

    assert payload["cut_boundary_media_duration_bucket_sec"] == 600
    assert payload["scan_cut_boundary_level"] == "high"
    assert payload["scan_cut_auto_threshold"] == 31.5
    assert payload["scan_cut_realtime_preview_enabled"] is True
    assert payload["scan_cut_audio_gain_enabled"] is False
    assert settings["cut_boundary_media_duration_sec"] == 701.0


def test_subtitle_cut_boundary_cache_payload_is_copy_safe():
    file_entry = {"path": "/tmp/a.mp4", "size": 10}
    settings_payload = {"scan_cut_threshold": 24.0}

    payload = subtitle_cut_boundary_cache_payload(
        file_entries=[file_entry],
        settings_payload=settings_payload,
    )
    file_entry["size"] = 99
    settings_payload["scan_cut_threshold"] = 12.0

    assert payload["version"] == 7
    assert payload["files"][0]["size"] == 10
    assert payload["settings"]["scan_cut_threshold"] == 24.0


def test_subtitle_cut_boundary_summary_counts_plan_inputs():
    summary = summarize_subtitle_cut_boundary_cache_plan(
        file_entries=[{"path": "/tmp/a.mp4"}, {"path": "/tmp/b.mp4"}],
        settings_payload={"a": 1, "b": 2},
    ).to_dict()

    assert summary["schema"] == SUBTITLE_CUT_BOUNDARY_FACADE_SCHEMA
    assert summary["file_count"] == 2
    assert summary["settings_key_count"] == 2
    assert summary["algorithm_id"]


def test_pipeline_cut_boundary_cache_uses_facade_fallback(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    settings = {"cut_boundary_media_duration_sec": 301.0, "scan_cut_realtime_preview_enabled": "off"}

    with patch("core.pipeline.cut_boundary_cache.cut_boundary_cache_settings_payload_via_swift", return_value=None), patch(
        "core.pipeline.cut_boundary_cache.cut_boundary_cache_plan_via_swift",
        return_value=None,
    ):
        settings_payload = cut_boundary_cache_settings_payload(settings)
        payload = cut_boundary_cache_base_payload([str(media)], settings)

    assert settings_payload == subtitle_cut_boundary_settings_payload(settings)
    assert payload["settings"] == settings_payload
    assert payload["files"][0]["path"] == str(media)


def test_truthy_setting_matches_legacy_text_values():
    assert truthy_setting("auto", True) is True
    assert truthy_setting("미사용", True) is False
    assert truthy_setting("enabled", False) is True
