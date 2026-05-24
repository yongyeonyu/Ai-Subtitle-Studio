from __future__ import annotations

from core.audio.diarize import get_speaker_for_segment
from core.engine.subtitle_speaker_diarization import (
    SUBTITLE_SPEAKER_DIARIZATION_SCHEMA,
    apply_runtime_speaker_diarization,
    build_inline_dialogue_speaker_split,
    dialogue_turn_speaker_pair,
    inline_dialogue_turns,
    normalize_runtime_speaker_id,
    speaker_for_segment,
    speaker_sequence_for_range,
)
from core.pipeline.pipeline_helpers import PipelineHelpersMixin


class _SpeakerRuntimeHarness(PipelineHelpersMixin):
    def __init__(self):
        self._speaker_auto_enabled = True
        self._effective_min_speakers = 1
        self._effective_max_speakers = 2
        self._speaker_map = []


def test_speaker_id_and_dialogue_turn_helpers_match_runtime_conventions():
    assert normalize_runtime_speaker_id("SPEAKER_01") == "01"
    assert normalize_runtime_speaker_id("") == "00"
    assert dialogue_turn_speaker_pair({"spk1_id": "02", "spk2_id": "02"}) == ("02", "01")
    assert inline_dialogue_turns("- 먼저요 - 네") == ["먼저요", "네"]


def test_speaker_for_segment_prefers_longest_overlap_and_keeps_audio_facade_parity():
    speaker_map = [
        {"start": 0.0, "end": 0.6, "speaker": "SPEAKER_00"},
        {"start": 0.6, "end": 2.0, "speaker": "SPEAKER_01"},
    ]

    assert speaker_for_segment(0.0, 1.5, speaker_map) == "SPEAKER_01"
    assert get_speaker_for_segment(0.0, 1.5, speaker_map) == "SPEAKER_01"
    assert speaker_sequence_for_range(0.0, 2.0, speaker_map) == ["00", "01"]


def test_inline_dialogue_split_uses_map_sequence_without_mutating_input():
    row = {"start": 0.0, "end": 2.0, "text": "카페라떼요 - 네", "_stt_speaker_marker_preserved": True}
    speaker_map = [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
        {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
    ]

    updated = build_inline_dialogue_speaker_split(row, speaker_map, fallback_speakers=("02", "03"))

    assert row["text"] == "카페라떼요 - 네"
    assert updated["text"] == "- 카페라떼요\n- 네"
    assert updated["speaker_list"] == ["00", "01"]


def test_runtime_diarization_groups_adjacent_single_speaker_turns():
    result = apply_runtime_speaker_diarization(
        [
            {"start": 0.0, "end": 0.9, "text": "아이스로 드릴까요?"},
            {"start": 1.0, "end": 1.3, "text": "네네"},
        ],
        speaker_map=[
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        ],
    )

    payload = result.to_dict()
    assert payload["schema"] == SUBTITLE_SPEAKER_DIARIZATION_SCHEMA
    assert payload["counts"] == {"rows": 1, "inline_splits": 0, "speaker_map": 2}
    assert payload["rows"][0]["text"] == "- 아이스로 드릴까요?\n- 네네"
    assert payload["rows"][0]["speaker_list"] == ["00", "01"]


def test_pipeline_helper_delegates_to_speaker_diarization_facade():
    harness = _SpeakerRuntimeHarness()
    harness._speaker_map = [
        {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
        {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
    ]

    rows = harness._apply_runtime_speaker_diarization(
        [
            {"start": 0.0, "end": 0.9, "text": "아이스로 드릴까요?"},
            {"start": 1.0, "end": 1.3, "text": "네네"},
        ]
    )

    assert rows == [
        {
            "start": 0.0,
            "end": 1.3,
            "text": "- 아이스로 드릴까요?\n- 네네",
            "speaker": "00",
            "speaker_list": ["00", "01"],
        }
    ]
