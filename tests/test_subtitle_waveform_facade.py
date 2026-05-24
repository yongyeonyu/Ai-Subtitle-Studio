from unittest.mock import patch

import numpy as np

from core.engine.subtitle_waveform import (
    SUBTITLE_WAVEFORM_FACADE_SCHEMA,
    build_waveform_columns,
    python_waveform_columns,
    waveform_speech_ranges,
)


def test_waveform_speech_ranges_maps_vad_to_waveform_indices():
    ranges = waveform_speech_ranges(
        100,
        10.0,
        [
            {"start": 1.0, "end": 2.0},
            {"start": "bad", "end": 3.0},
            {"start": 8.0, "end": 20.0},
        ],
    )

    assert ranges == [(10, 21), (80, 100)]


def test_python_waveform_columns_match_global_canvas_fallback_shape():
    columns = python_waveform_columns(
        np.array([0.0, 0.5, 1.0, 0.25], dtype=np.float32),
        width=4,
        total_duration=4.0,
        vad_segments=[{"start": 1.0, "end": 2.0}],
    )

    assert columns == [(1, False), (7, True), (14, True), (3, False)]


def test_build_waveform_columns_uses_native_when_valid_width_matches():
    with patch(
        "core.native_swift_timeline.build_waveform_columns_via_swift",
        return_value=[(1, False), (2, True)],
    ):
        columns = build_waveform_columns(
            np.array([0.0, 1.0], dtype=np.float32),
            width=2,
            total_duration=2.0,
            vad_segments=[],
        )

    assert columns == [(1, False), (2, True)]


def test_build_waveform_columns_falls_back_when_native_shape_is_invalid():
    with patch("core.native_swift_timeline.build_waveform_columns_via_swift", return_value=[(1, False)]):
        columns = build_waveform_columns(
            np.array([0.0, 1.0], dtype=np.float32),
            width=2,
            total_duration=2.0,
            vad_segments=[],
        )

    assert SUBTITLE_WAVEFORM_FACADE_SCHEMA.endswith(".v1")
    assert columns == [(1, False), (14, False)]
