from __future__ import annotations

from core.engine.subtitle_live_editor_feed import (
    SUBTITLE_LIVE_EDITOR_FEED_SCHEMA,
    build_subtitle_live_editor_feed,
)


def test_live_editor_feed_sorts_and_counts_rows_without_mutating_inputs():
    confirmed = [{"start": 5.0, "end": 6.0, "text": "final"}]
    subtitle_preview = [{"start": 2.0, "end": 3.0, "text": "draft", "_live_subtitle_preview": True}]
    stt_preview = [{"start": 1.0, "end": 1.5, "text": "stt", "_live_stt_preview": True}]

    feed = build_subtitle_live_editor_feed(
        confirmed_segments=confirmed,
        stt_preview_segments=stt_preview,
        subtitle_preview_segments=subtitle_preview,
    )
    confirmed[0]["text"] = "mutated"

    payload = feed.to_dict()
    assert payload["schema"] == SUBTITLE_LIVE_EDITOR_FEED_SCHEMA
    assert [row["text"] for row in payload["combined_segments"]] == ["stt", "draft", "final"]
    assert [row["text"] for row in payload["final_surface_segments"]] == ["final"]
    assert [row["text"] for row in payload["preview_lane_segments"]] == ["stt", "draft"]
    assert payload["surface_contract"] == {
        "final_surface": "confirmed_segments_only",
        "preview_lane": "subtitle_preview_plus_stt_preview",
        "combined_segments": "diagnostic_candidate_lane_only_not_final_overlay_or_save",
    }
    assert payload["counts"] == {
        "confirmed": 1,
        "stt_preview": 1,
        "subtitle_preview": 1,
        "final_surface": 1,
        "preview_lane": 2,
        "combined": 3,
    }
    assert payload["confirmed_segments"][0]["text"] == "final"
    assert payload["total_duration"] == 6.0


def test_live_editor_feed_uses_duration_floor_for_video_timeline():
    feed = build_subtitle_live_editor_feed(
        confirmed_segments=[{"start": 1.0, "end": 2.0, "text": "short"}],
        stt_preview_segments=[],
        subtitle_preview_segments=[],
        total_duration_floor=120.0,
    )

    assert feed.total_duration == 120.0


def test_live_editor_feed_handles_empty_rows():
    feed = build_subtitle_live_editor_feed(
        confirmed_segments=None,
        stt_preview_segments=None,
        subtitle_preview_segments=None,
        total_duration_floor=0.0,
    )

    assert feed.to_dict()["combined_segments"] == []
    assert feed.total_duration == 0.0
