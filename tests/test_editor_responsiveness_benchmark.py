from pathlib import Path

from tools.benchmark_editor_responsiveness import (
    build_benchmark_steps,
    render_markdown,
    summarize_results,
)


def test_editor_responsiveness_steps_include_required_editor_actions(tmp_path):
    steps = build_benchmark_steps(tmp_path, Path("/tmp/project.aissproj"))
    by_name = {step["name"]: step for step in steps}

    for name in (
        "open_project",
        "capture_before",
        "set_playhead",
        "timeline_zoom_in",
        "timeline_time_window",
        "timeline_max",
        "zoom_max",
        "global_menu_status",
        "global_menu_save",
        "status_probe",
        "guided_status_probe",
        "capture_after",
    ):
        assert name in by_name

    assert by_name["open_project"]["command"] == ["open-project", "/tmp/project.aissproj"]
    assert by_name["capture_before"]["wait_for_path"].endswith("snapshots/before.png")
    assert by_name["capture_after"]["wait_for_path"].endswith("snapshots/after.png")


def test_editor_responsiveness_summary_keeps_threshold_failures_visible(tmp_path):
    runs = [
        {
            "run_index": 1,
            "ok": True,
            "total_elapsed_sec": 2.0,
            "steps": [
                {"run_index": 1, "name": "status_probe", "ok": True, "command_elapsed_sec": 0.04},
                {"run_index": 1, "name": "timeline_zoom_in", "ok": True, "command_elapsed_sec": 0.12},
            ],
        },
        {
            "run_index": 2,
            "ok": True,
            "total_elapsed_sec": 4.0,
            "steps": [
                {"run_index": 2, "name": "status_probe", "ok": True, "command_elapsed_sec": 0.30},
                {"run_index": 2, "name": "timeline_zoom_in", "ok": True, "command_elapsed_sec": 0.14},
            ],
        },
    ]

    summary = summarize_results(runs)
    markdown = render_markdown(summary, tmp_path)

    assert summary["run_count"] == 2
    assert summary["ok"] is False
    assert summary["threshold_failure_count"] == 1
    assert summary["threshold_failures"][0]["name"] == "status_probe"
    assert summary["steps"]["timeline_zoom_in"]["threshold"]["p95"] == 0.20
    assert "status_probe" in markdown
    assert "Threshold Failures" in markdown


def test_editor_responsiveness_summary_passes_when_thresholds_are_met(tmp_path):
    runs = [
        {
            "run_index": 1,
            "ok": True,
            "total_elapsed_sec": 1.0,
            "steps": [
                {"run_index": 1, "name": "status_probe", "ok": True, "command_elapsed_sec": 0.02},
                {"run_index": 1, "name": "guided_status_probe", "ok": True, "command_elapsed_sec": 0.03},
                {"run_index": 1, "name": "global_menu_status", "ok": True, "command_elapsed_sec": 0.05},
            ],
        }
    ]

    summary = summarize_results(runs)

    assert summary["ok"] is True
    assert summary["failed_run_count"] == 0
    assert summary["threshold_failure_count"] == 0
    assert summary["run_elapsed_sec"]["max"] == 1.0
