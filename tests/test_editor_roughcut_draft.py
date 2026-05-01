# Version: 03.02.17
# Phase: PHASE2
import unittest

from core.roughcut import (
    EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
    apply_roughcut_order_to_subtitles,
    build_editor_roughcut_candidate_payload,
    build_editor_roughcut_draft_result,
    editor_roughcut_draft_enabled,
    merge_editor_roughcut_draft_state,
)
from ui.timeline.timeline_analysis import roughcut_major_markers


def _segments(count: int = 7) -> list[dict]:
    out = []
    cursor = 0.0
    for idx in range(count):
        out.append(
            {
                "start": cursor,
                "end": cursor + 1.0,
                "text": f"자막 내용 {idx + 1}입니다",
                "speaker": "00",
            }
        )
        cursor += 1.2
    return out


class EditorRoughcutDraftTests(unittest.TestCase):
    def test_fast_recognition_forces_editor_draft_off(self):
        self.assertFalse(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"}
            )
        )
        self.assertTrue(
            editor_roughcut_draft_enabled(
                {"editor_roughcut_draft_enabled": True, "stt_quality_preset": "balanced"}
            )
        )

    def test_builds_major_segments_with_subtitle_rows_as_minor_groups(self):
        result = build_editor_roughcut_draft_result(
            _segments(7),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        self.assertEqual(len(result.segments), 3)
        self.assertEqual(result.segments[0].major_id, "A")
        self.assertEqual(len(result.segments[0].minor_groups), 3)
        self.assertEqual(result.segments[0].minor_groups[0].subtitle_ids, (0,))
        self.assertEqual(len(result.chapters), 7)
        self.assertEqual(len(result.edl_segments), 3)

    def test_timeline_major_markers_expose_abc_segments(self):
        result = build_editor_roughcut_draft_result(
            _segments(6),
            settings={
                "roughcut_major_min_subtitle_count": 3,
                "editor_roughcut_draft_max_subtitle_count": 3,
            },
        )

        markers = roughcut_major_markers(result)

        self.assertEqual([m["label"] for m in markers], ["A", "B"])
        self.assertEqual(markers[0]["kind"], "roughcut_major")
        self.assertLess(markers[0]["start"], markers[0]["end"])

    def test_merges_editor_draft_candidate_without_dropping_existing_candidates(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state(
            {"candidates": [{"candidate_id": "manual_candidate", "name": "수동 후보"}]},
            candidate,
        )

        self.assertEqual(state["selected_candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidate_count"], 2)
        self.assertEqual(state["candidates"][0]["candidate_id"], EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID)
        self.assertEqual(state["candidates"][1]["candidate_id"], "manual_candidate")

    def test_editor_save_order_requires_explicit_roughcut_flag(self):
        segments = _segments(5)
        result = build_editor_roughcut_draft_result(segments)
        candidate = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            source_path="/tmp/source.mp4",
            media_files=["/tmp/source.mp4"],
        )
        state = merge_editor_roughcut_draft_state({}, candidate)
        self.assertEqual(apply_roughcut_order_to_subtitles(segments, state), segments)

        state["candidates"][0]["editor_save_order_enabled"] = True
        ordered = apply_roughcut_order_to_subtitles(segments, state)
        self.assertEqual(len(ordered), len(segments))
        self.assertEqual(ordered[0]["start"], 0.0)


if __name__ == "__main__":
    unittest.main()
