from core.engine.subtitle_timing_contracts import (
    COMMON_SPLIT_GUARD_SCHEMA,
    TIMING_FUSION_SCHEMA,
    build_timing_frame_fields,
    build_timing_fusion_policy,
    compact_timing_text,
    segment_scope_key,
    segment_time_bounds,
)


def test_segment_time_bounds_prefers_start_end_and_clamps_reversed_end():
    assert segment_time_bounds({"start": "2.5", "timeline_start": 1.0, "end": "2.0"}) == (2.5, 2.5)


def test_segment_time_bounds_uses_timeline_fields_when_primary_missing():
    assert segment_time_bounds({"timeline_start": 3.25, "timeline_end": 4.5}) == (3.25, 4.5)


def test_segment_scope_key_includes_clip_and_cut_scene_identity():
    assert segment_scope_key(
        {
            "_clip_idx": 7,
            "cut_scene_index": 3,
            "cut_scene_start_frame": 90,
            "cut_scene_end_frame": 150,
        }
    ) == ("cut_scene", ("clip_idx", "7"), "3", "90", "150")


def test_compact_timing_text_normalizes_whitespace_and_case():
    assert compact_timing_text("  Hello \n WORLD  ") == "helloworld"


def test_timing_frame_fields_anchor_safe_rounding_never_starts_earlier():
    fields = build_timing_frame_fields(2.217, 2.95, 30.0, anchor_safe=True)

    assert fields is not None
    assert fields["start"] >= 2.217
    assert fields["end"] > fields["start"]
    assert fields["timeline_start_frame"] == fields["start_frame"]
    assert fields["timeline_end_frame"] == fields["end_frame"]
    assert fields["frame_range"] == {
        "unit": "frame",
        "start": fields["start_frame"],
        "end": fields["end_frame"],
        "timeline_frame_rate": 30.0,
    }


def test_timing_frame_fields_returns_none_without_fps():
    assert build_timing_frame_fields(1.0, 2.0, None) is None


def test_timing_fusion_policy_payload_is_stable_for_native_parity():
    policy = build_timing_fusion_policy(
        old_start=0.1234,
        old_end=2.3456,
        new_start=0.2,
        new_end=2.1,
        evidence=[{"source": "word_timestamp"}],
    )

    assert policy == {
        "schema": TIMING_FUSION_SCHEMA,
        "task": "subtitle_timing_fusion",
        "old_start": 0.123,
        "old_end": 2.346,
        "new_start": 0.2,
        "new_end": 2.1,
        "start_shift": 0.0766,
        "end_shift": -0.2456,
        "evidence": [{"source": "word_timestamp"}],
    }
    assert COMMON_SPLIT_GUARD_SCHEMA == "ai_subtitle_studio.common_subtitle_split_guard.v1"
