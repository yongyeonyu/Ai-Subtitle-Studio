import os
from pathlib import Path

import pytest

from core.cut_boundary import split_segments_by_cut_boundaries
from tools.verify_cut_boundary_source_fps_scout import verify_source_fps_scout
import tools.verify_cut_boundary_source_fps_scout as scout_tool


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
    assert all(row["visual_candidate_status"] == "metadata_only" for row in manifest["pairs"])
    summary = manifest["visual_detection_summary"]
    assert summary["visual_evidence_available"] is False
    assert summary["strict_visual_detection_passed"] is False
    assert summary["frame_grid_preservation_passed"] is True
    assert summary["acceptance_claim"] == "metadata_frame_grid_only"
    assert (tmp_path / "report" / "source_fps_scout.json").is_file()
    assert (tmp_path / "report" / "source_fps_scout.md").is_file()


def _patch_probe_and_frames(monkeypatch, frame_map):
    def fake_probe(path, *, timeout_sec=120.0, fps_override=0.0):
        return {
            "width": 320,
            "height": 180,
            "frame_count": 100,
            "duration_sec": 100 / (60000 / 1001),
            "fps": 60000 / 1001,
            "fps_num": 60000,
            "fps_den": 1001,
            "r_frame_rate": "60000/1001",
            "probe_source": "test_probe",
        }

    def fake_read(path, frames, *, width, height, timeout_sec=180.0):
        return {int(key): value for key, value in frame_map.items()}

    monkeypatch.setattr(scout_tool, "_probe_video", fake_probe)
    monkeypatch.setattr(scout_tool, "_read_gray_frames", fake_read)


def test_source_fps_scout_visual_summary_flags_preserved_only_candidate(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    dark = np.zeros((180, 320), dtype=np.uint8)
    _patch_probe_and_frames(
        monkeypatch,
        {
            2765: dark,
            2766: dark.copy(),
            2676: dark.copy(),
            2677: dark.copy(),
        },
    )

    manifest = verify_source_fps_scout(
        tmp_path / "fake.mp4",
        pairs=[(2765, 2766), (2676, 2677)],
        width=320,
        height=180,
        output_dir=tmp_path / "report",
        pipe_max_fps=60.0,
    )

    assert manifest["passed"] is True
    assert [row["visual_candidate_status"] for row in manifest["pairs"]] == ["preserved_only", "preserved_only"]
    summary = manifest["visual_detection_summary"]
    assert summary["visual_evidence_available"] is True
    assert summary["visual_evidence_pair_count"] == 2
    assert summary["candidate_detected_count"] == 0
    assert summary["visual_candidate_missing_count"] == 2
    assert summary["frame_grid_preservation_passed"] is True
    assert summary["strict_visual_detection_passed"] is False
    assert summary["acceptance_claim"] == "frame_grid_preservation_with_visual_candidate_gap"


def test_source_fps_scout_require_visual_detection_fails_preserved_only_candidate(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    dark = np.zeros((180, 320), dtype=np.uint8)
    _patch_probe_and_frames(monkeypatch, {1: dark, 2: dark.copy()})

    manifest = verify_source_fps_scout(
        tmp_path / "fake.mp4",
        pairs=[(1, 2)],
        width=320,
        height=180,
        output_dir=tmp_path / "report",
        pipe_max_fps=60.0,
        require_visual_detection=True,
    )

    assert manifest["passed"] is False
    assert manifest["visual_detection_summary"]["strict_visual_detection_required"] is True
    assert manifest["visual_detection_summary"]["frame_grid_preservation_passed"] is True
    assert manifest["visual_detection_summary"]["strict_visual_detection_passed"] is False


def test_source_fps_scout_visual_summary_detects_strong_candidate(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    _patch_probe_and_frames(
        monkeypatch,
        {
            1: np.zeros((180, 320), dtype=np.uint8),
            2: np.full((180, 320), 255, dtype=np.uint8),
        },
    )

    manifest = verify_source_fps_scout(
        tmp_path / "fake.mp4",
        pairs=[(1, 2)],
        width=320,
        height=180,
        output_dir=tmp_path / "report",
        pipe_max_fps=60.0,
        require_visual_detection=True,
    )

    assert manifest["passed"] is True
    assert manifest["pairs"][0]["visual_candidate_status"] == "detected"
    assert manifest["pairs"][0]["candidate_detected"] is True
    summary = manifest["visual_detection_summary"]
    assert summary["candidate_detected_count"] == 1
    assert summary["visual_candidate_missing_count"] == 0
    assert summary["strict_visual_detection_passed"] is True
    assert summary["acceptance_claim"] == "visual_detection"


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
