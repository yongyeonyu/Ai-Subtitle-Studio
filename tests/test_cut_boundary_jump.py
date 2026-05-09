from core.cut_boundary_jump import boundary_second, nearest_boundary_second, normalize_boundary_seconds


def test_boundary_second_accepts_common_project_rows():
    assert boundary_second({"timeline_sec": 12.34}) == 12.34
    assert boundary_second({"time": 7.5}) == 7.5
    assert boundary_second({"frame": 90}, primary_fps=30.0) == 3.0


def test_boundary_second_skips_rejected_rows():
    assert boundary_second({"timeline_sec": 10.0, "status": "rejected"}) is None
    assert boundary_second({"timeline_sec": 10.0, "status": "deleted"}) is None


def test_normalize_boundary_seconds_sorts_and_dedupes():
    rows = [8.0, {"time": 2.0}, {"timeline_sec": 2.03}, {"frame": 300, "fps": 30.0}]
    assert normalize_boundary_seconds(rows, dedupe_epsilon_sec=0.055) == [2.0, 8.0, 10.0]


def test_nearest_boundary_second_uses_gap_to_avoid_same_cut():
    rows = [1.0, 5.0, 10.0]
    assert nearest_boundary_second(rows, current_sec=5.0, direction=1, min_gap_sec=0.08) == 10.0
    assert nearest_boundary_second(rows, current_sec=5.0, direction=-1, min_gap_sec=0.08) == 1.0


def test_nearest_boundary_second_returns_none_at_edges():
    rows = [1.0, 5.0, 10.0]
    assert nearest_boundary_second(rows, current_sec=10.0, direction=1) is None
    assert nearest_boundary_second(rows, current_sec=1.0, direction=-1) is None
