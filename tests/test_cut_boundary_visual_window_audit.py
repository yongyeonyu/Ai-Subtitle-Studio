from __future__ import annotations

from pathlib import Path

import pytest

import tools.audit_cut_boundary_visual_window as window_audit
from tools.audit_cut_boundary_visual_window import audit_visual_windows


def _patch_probe_and_frames(monkeypatch, frame_map):
    def fake_probe(path, *, timeout_sec=120.0, fps_override=0.0):
        return {
            "width": 320,
            "height": 180,
            "frame_count": 120,
            "duration_sec": 120 / (60000 / 1001),
            "fps": 60000 / 1001,
            "fps_num": 60000,
            "fps_den": 1001,
            "r_frame_rate": "60000/1001",
            "probe_source": "test_probe",
        }

    def fake_read(path, frames, *, width, height, timeout_sec=180.0):
        return {int(frame): frame_map[int(frame)] for frame in frames if int(frame) in frame_map}

    monkeypatch.setattr(window_audit, "_probe_video", fake_probe)
    monkeypatch.setattr(window_audit, "_read_gray_frames", fake_read)


def test_visual_window_audit_ranks_detected_target_as_best(tmp_path: Path, monkeypatch) -> None:
    np = pytest.importorskip("numpy")
    dark = np.zeros((180, 320), dtype=np.uint8)
    bright = np.full((180, 320), 255, dtype=np.uint8)
    frame_map = {frame: dark.copy() for frame in range(6, 14)}
    for frame in range(10, 14):
        frame_map[frame] = bright.copy()
    _patch_probe_and_frames(monkeypatch, frame_map)

    audit = audit_visual_windows(
        tmp_path / "fake.mp4",
        target_frames=[10],
        radius=3,
        width=320,
        height=180,
        output_dir=tmp_path / "out",
        pipe_max_fps=60.0,
    )
    window = audit["windows"][0]

    assert audit["strict_targets_detected"] is True
    assert audit["target_best_count"] == 1
    assert window["target_detected"] is True
    assert window["target_is_best"] is True
    assert window["target_rank_by_score"] == 1
    assert window["best_frame"] == 10
    assert window["target_score"] >= 40.0
    assert (tmp_path / "out" / "cut_boundary_visual_window_audit.json").is_file()
    assert (tmp_path / "out" / "cut_boundary_visual_window_audit.md").is_file()


def test_visual_window_audit_keeps_preserved_only_target_blocked(tmp_path: Path, monkeypatch) -> None:
    np = pytest.importorskip("numpy")
    dark = np.zeros((180, 320), dtype=np.uint8)
    frame_map = {frame: dark.copy() for frame in range(6, 14)}
    _patch_probe_and_frames(monkeypatch, frame_map)

    audit = audit_visual_windows(
        tmp_path / "fake.mp4",
        target_frames=[10],
        radius=3,
        width=320,
        height=180,
        output_dir=tmp_path / "out",
        pipe_max_fps=60.0,
    )
    window = audit["windows"][0]

    assert audit["strict_targets_detected"] is False
    assert audit["target_best_count"] == 0
    assert audit["runtime_change_allowed"] is False
    assert "threshold_relaxation" in audit["blocked_runtime_changes"]
    assert window["target_detected"] is False
    assert window["target_rank_by_score"] > 0
    assert window["target_score"] == 0.0


def test_visual_window_markdown_keeps_guardrails(tmp_path: Path, monkeypatch) -> None:
    np = pytest.importorskip("numpy")
    dark = np.zeros((180, 320), dtype=np.uint8)
    frame_map = {frame: dark.copy() for frame in range(6, 14)}
    _patch_probe_and_frames(monkeypatch, frame_map)

    audit_visual_windows(
        tmp_path / "fake.mp4",
        target_frames=[10],
        radius=3,
        width=320,
        height=180,
        output_dir=tmp_path / "out",
        pipe_max_fps=60.0,
    )

    markdown = (tmp_path / "out" / "cut_boundary_visual_window_audit.md").read_text(encoding="utf-8")
    assert "Cut Boundary Visual Window Audit" in markdown
    assert "Strict targets detected: `False`" in markdown
    assert "Do not apply `threshold_relaxation`" in markdown
    assert "Do not apply `ui_or_qml_change`" in markdown
