import os
from pathlib import Path

import pytest

from core.cut_boundary import split_segments_by_cut_boundaries
from tools.verify_cut_boundary_source_fps_scout import verify_source_fps_scout


FIXTURE_ENV = "AI_SUBTITLE_STUDIO_CUT_BOUNDARY_FIXTURE"
EXPECT_ENV = "AI_SUBTITLE_STUDIO_CUT_BOUNDARY_EXPECT"
PIPE_MAX_FPS_ENV = "AI_SUBTITLE_STUDIO_CUT_BOUNDARY_PIPE_MAX_FPS"


def _expected_frames() -> list[int]:
    raw = os.environ.get(EXPECT_ENV, "2766,2677")
    frames: list[int] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if text:
            frames.append(int(text))
    return frames


def _fixture_path() -> Path:
    raw = os.environ.get(FIXTURE_ENV, "").strip()
    if not raw:
        pytest.skip(f"{FIXTURE_ENV} is not set")
    path = Path(raw).expanduser()
    if not path.is_file():
        pytest.skip(f"{FIXTURE_ENV} does not point to a readable file: {path}")
    return path


def test_source_fps_scout_metadata_only_fallback_preserves_frame_grid(tmp_path):
    media = tmp_path / "placeholder.mp4"
    media.write_bytes(b"not a real mp4")

    manifest = verify_source_fps_scout(
        media,
        pairs=[(2765, 2766), (2676, 2677)],
        width=320,
        height=180,
        output_dir=tmp_path / "report",
        pipe_max_fps=60.0,
        probe_timeout_sec=1.0,
        fps_override=60000 / 1001,
        allow_metadata_only=True,
    )

    assert manifest["passed"] is True
    assert manifest["media"]["probe_source"] == "spotlight_fps_override"
    assert manifest["pipe_fps_num"] == 60000
    assert manifest["pipe_fps_den"] == 1001
    assert [row["candidate_frame"] for row in manifest["pairs"]] == [2766, 2677]
    assert all(row["acceptance_basis"] == "metadata_frame_grid_preserved" for row in manifest["pairs"])
    assert (tmp_path / "report" / "source_fps_scout.json").is_file()
    assert (tmp_path / "report" / "source_fps_scout.md").is_file()


def test_fixed_fixture_source_fps_scout_preserves_expected_cut_frames(tmp_path):
    fixture = _fixture_path()
    expected = _expected_frames()
    pairs = [(frame - 1, frame) for frame in expected]
    pipe_max_fps = float(os.environ.get(PIPE_MAX_FPS_ENV, "60") or 60.0)

    manifest = verify_source_fps_scout(
        fixture,
        pairs=pairs,
        width=320,
        height=180,
        output_dir=tmp_path,
        pipe_max_fps=pipe_max_fps,
        probe_timeout_sec=5.0,
        frame_extract_timeout_sec=30.0,
        fps_override=60000 / 1001,
        allow_metadata_only=True,
    )

    assert manifest["passed"] is True
    assert manifest["allow_metadata_only"] is True
    assert manifest["pipe_fps_num"] == 60000
    assert manifest["pipe_fps_den"] == 1001
    assert [row["candidate_frame"] for row in manifest["pairs"]] == expected
    assert all(row["frame_preserved"] for row in manifest["pairs"])
    assert (tmp_path / "source_fps_scout.md").is_file()


def test_confirmed_fixture_cut_frames_split_snap_without_crossing_rows():
    fps = 60000 / 1001
    expected = _expected_frames()
    boundaries = [
        {"timeline_frame": frame, "fps": fps, "status": "confirmed", "source": "visual"}
        for frame in expected
    ]
    rows = split_segments_by_cut_boundaries(
        [
            {
                "id": "cross-2766",
                "segment_id": "stt-cross-2766",
                "start_frame": 2760,
                "end_frame": 2772,
                "start": 2760 / fps,
                "end": 2772 / fps,
                "text": "before after cut",
            },
            {
                "id": "snap-2677",
                "segment_id": "stt-snap-2677",
                "start_frame": 2676,
                "end_frame": 2690,
                "start": 2676 / fps,
                "end": 2690 / fps,
                "text": "one frame early",
            },
        ],
        boundaries,
        primary_fps=fps,
    )

    assert any(row.get("cut_boundary_forced_split") and row.get("start_frame") == 2766 for row in rows)
    assert any(row.get("cut_boundary_edge_snapped") and row.get("start_frame") == 2677 for row in rows)
    for frame in expected:
        assert all(not (row["start_frame"] < frame < row["end_frame"]) for row in rows)
