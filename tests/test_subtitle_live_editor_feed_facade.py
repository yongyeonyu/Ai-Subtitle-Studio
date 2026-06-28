from __future__ import annotations

from core.engine.subtitle_live_editor_feed import (
    SUBTITLE_LIVE_EDITOR_FEED_SCHEMA,
    SUBTITLE_LIVE_EDITOR_RUNTIME_STATUS_SCHEMA,
    SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
    build_subtitle_live_editor_feed,
)


def test_live_editor_feed_sorts_and_counts_rows_without_mutating_inputs():
    confirmed = [{"start": 5.0, "end": 6.0, "text": "final"}]
    subtitle_preview = [{"start": 2.0, "end": 3.0, "text": "draft", "_live_subtitle_preview": True}]
    stt_preview = [{"start": 1.0, "end": 1.5, "text": "stt", "_live_stt_preview": True, "stt_preview_source": "STT1"}]
    vad = [{"start": 0.25, "end": 0.75, "text": "voice", "kind": "speech", "source": "VAD"}]

    feed = build_subtitle_live_editor_feed(
        confirmed_segments=confirmed,
        stt_preview_segments=stt_preview,
        subtitle_preview_segments=subtitle_preview,
        vad_segments=vad,
    )
    confirmed[0]["text"] = "mutated"
    vad[0]["text"] = "mutated"

    payload = feed.to_dict()
    assert payload["schema"] == SUBTITLE_LIVE_EDITOR_FEED_SCHEMA
    assert [row["text"] for row in payload["combined_segments"]] == ["stt", "draft", "final"]
    assert [row["text"] for row in payload["final_surface_segments"]] == ["final"]
    assert [row["text"] for row in payload["preview_lane_segments"]] == ["stt", "draft"]
    assert [row["text"] for row in payload["vad_segments"]] == ["voice"]
    assert payload["surface_contract"] == {
        "final_surface": "confirmed_segments_only",
        "preview_lane": "subtitle_preview_plus_stt_preview",
        "combined_segments": "diagnostic_candidate_lane_only_not_final_overlay_or_save",
    }
    assert payload["runtime_track_contract"] == {
        "final": "only_track_with_save_export_render_authority",
        "STT1": "runtime_reference_only_not_save_export",
        "STT2": "runtime_reference_only_not_save_export",
        "VAD": "runtime_reference_only_not_save_export",
        "subtitle_preview": "runtime_reference_only_not_save_export",
    }
    assert payload["counts"] == {
        "confirmed": 1,
        "stt_preview": 1,
        "subtitle_preview": 1,
        "final_surface": 1,
        "preview_lane": 2,
        "combined": 3,
        "vad": 1,
        "runtime_tracks": {"VAD": 1, "STT1": 1, "STT2": 0, "subtitle_preview": 1, "final": 1},
        "runtime_track_segments": 4,
    }
    assert list(payload["runtime_tracks"]) == ["VAD", "STT1", "STT2", "subtitle_preview", "final"]
    assert payload["runtime_tracks"]["final"]["schema"] == SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA
    assert payload["runtime_track_status"] == {
        "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_STATUS_SCHEMA,
        "tracks": {
            "VAD": {
                "role": "runtime_reference_only",
                "count": 1,
                "active": True,
                "authoritative_for_save_export": False,
            },
            "STT1": {
                "role": "runtime_reference_only",
                "count": 1,
                "active": True,
                "authoritative_for_save_export": False,
            },
            "STT2": {
                "role": "runtime_reference_only",
                "count": 0,
                "active": False,
                "authoritative_for_save_export": False,
            },
            "subtitle_preview": {
                "role": "runtime_reference_only",
                "count": 1,
                "active": True,
                "authoritative_for_save_export": False,
            },
            "final": {
                "role": "save_export_render_authority",
                "count": 1,
                "active": True,
                "authoritative_for_save_export": True,
            },
        },
        "counts": {"VAD": 1, "STT1": 1, "STT2": 0, "subtitle_preview": 1, "final": 1},
        "active_tracks": ["VAD", "STT1", "subtitle_preview", "final"],
        "total_count": 4,
        "final_authority_track": "final",
        "compact_payload": True,
    }
    assert "segments" not in payload["runtime_track_status"]["tracks"]["STT1"]
    assert payload["runtime_tracks"]["final"]["authoritative_for_save_export"] is True
    assert payload["runtime_tracks"]["STT1"]["authoritative_for_save_export"] is False
    assert payload["runtime_tracks"]["VAD"]["authoritative_for_save_export"] is False
    assert payload["runtime_tracks"]["final"]["segments"][0]["_nle_save_export_authority"] is True
    assert payload["runtime_tracks"]["STT1"]["segments"][0]["_nle_runtime_track"] == "STT1"
    assert payload["runtime_tracks"]["VAD"]["segments"][0]["_nle_runtime_role"] == "runtime_reference_only"
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
    assert feed.to_dict()["runtime_tracks"] == {
        "VAD": {
            "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
            "role": "runtime_reference_only",
            "authoritative_for_save_export": False,
            "segments": [],
            "count": 0,
        },
        "STT1": {
            "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
            "role": "runtime_reference_only",
            "authoritative_for_save_export": False,
            "segments": [],
            "count": 0,
        },
        "STT2": {
            "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
            "role": "runtime_reference_only",
            "authoritative_for_save_export": False,
            "segments": [],
            "count": 0,
        },
        "subtitle_preview": {
            "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
            "role": "runtime_reference_only",
            "authoritative_for_save_export": False,
            "segments": [],
            "count": 0,
        },
        "final": {
            "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
            "role": "save_export_render_authority",
            "authoritative_for_save_export": True,
            "segments": [],
            "count": 0,
        },
    }
    assert feed.to_dict()["runtime_track_segments"] == []
    assert feed.total_duration == 0.0


def test_live_editor_feed_splits_runtime_stt_tracks_without_promoting_to_final_surface():
    feed = build_subtitle_live_editor_feed(
        confirmed_segments=[{"start": 10.0, "end": 11.0, "text": "final"}],
        stt_preview_segments=[
            {"start": 1.0, "end": 2.0, "text": "primary", "_live_stt_preview": True, "stt_preview_source": "STT1"},
            {"start": 2.0, "end": 3.0, "text": "secondary", "_live_stt_preview": True, "stt_preview_source": "STT2"},
        ],
        subtitle_preview_segments=[],
        vad_segments=[{"start": 0.0, "end": 0.5, "text": "speech", "kind": "speech"}],
    )

    payload = feed.to_dict()
    assert [row["text"] for row in payload["final_surface_segments"]] == ["final"]
    assert [row["text"] for row in payload["runtime_tracks"]["STT1"]["segments"]] == ["primary"]
    assert [row["text"] for row in payload["runtime_tracks"]["STT2"]["segments"]] == ["secondary"]
    assert [row["text"] for row in payload["runtime_tracks"]["VAD"]["segments"]] == ["speech"]
    assert all(
        row["_nle_save_export_authority"] is False
        for track in ("STT1", "STT2", "VAD")
        for row in payload["runtime_tracks"][track]["segments"]
    )


def test_live_editor_feed_counts_stt2_source_preview_rows_as_runtime_stt2_track():
    feed = build_subtitle_live_editor_feed(
        confirmed_segments=[],
        stt_preview_segments=[],
        subtitle_preview_segments=[
            {
                "start": 1.0,
                "end": 2.0,
                "text": "selected by stt2",
                "_live_subtitle_preview": True,
                "stt_selected_source": "STT2",
                "stt_ensemble_source": "STT2_SELECTIVE_RECHECK",
            }
        ],
    )

    payload = feed.to_dict()
    status = payload["runtime_track_status"]

    assert status["counts"]["subtitle_preview"] == 1
    assert status["counts"]["STT2"] == 1
    assert status["active_tracks"] == ["STT2", "subtitle_preview"]
    assert payload["runtime_tracks"]["STT2"]["segments"][0]["_nle_save_export_authority"] is False
    assert payload["final_surface_segments"] == []
