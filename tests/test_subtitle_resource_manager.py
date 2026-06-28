from types import SimpleNamespace

import core.runtime.subtitle_resource_manager as subtitle_resource_manager
from core.runtime.subtitle_resource_manager import (
    LIVE_NLE_PROJECTION_BUDGET_SCHEMA,
    active_runtime_labels_from_window,
    apple_m_accelerator_flag_report,
    live_nle_projection_scheduler_budget,
    mixed_accelerator_parallelism_floor,
    normalize_accelerator_name,
)


def test_normalize_accelerator_name_groups_ane_gpu_and_cpu_labels():
    assert normalize_accelerator_name("ANE") == "npu"
    assert normalize_accelerator_name("coreml") == "npu"
    assert normalize_accelerator_name("apple-neural-engine") == "npu"
    assert normalize_accelerator_name("MPS") == "gpu"
    assert normalize_accelerator_name("mlx") == "gpu"
    assert normalize_accelerator_name("") == "cpu"
    assert normalize_accelerator_name("unknown") == "cpu"


def test_mixed_accelerator_parallelism_floor_keeps_stt_quality_window_bounded():
    assert mixed_accelerator_parallelism_floor("stt_window", ["npu", "gpu"], 8) == 3
    assert mixed_accelerator_parallelism_floor("stt_precision", ["coreml", "mps"], 2) == 2
    assert mixed_accelerator_parallelism_floor("stt", ["gpu", "cpu"], 8) == 2


def test_mixed_accelerator_parallelism_floor_ignores_single_work_and_unknown_tasks():
    assert mixed_accelerator_parallelism_floor("stt", ["npu", "gpu"], 1) == 0
    assert mixed_accelerator_parallelism_floor("subtitle_segments", ["npu", "gpu"], 8) == 0
    assert mixed_accelerator_parallelism_floor("subtitle_llm", ["gpu", "cpu"], 8) == 2


def test_apple_m_accelerator_flag_report_parses_false_strings():
    flags = apple_m_accelerator_flag_report(
        {
            "stt_whisperkit_native_allocator_can_raise_workers": "off",
            "audio_torch_gpu_enabled": "0",
            "ffmpeg_videotoolbox_decode_enabled": "false",
            "scan_cut_pioneer_pipe_hwaccel_enabled": "no",
            "lora_gpu_acceleration_enabled": "false",
            "stt_window_ensemble_enabled": "true",
            "apple_m_aggressive_full_parallel_stt_enabled": "yes",
        }
    )

    assert flags["whisperkit_native_allocator_can_raise_workers"] is False
    assert flags["audio_torch_gpu_enabled"] is False
    assert flags["ffmpeg_videotoolbox_decode_enabled"] is False
    assert flags["scan_cut_pioneer_pipe_hwaccel_enabled"] is False
    assert flags["lora_gpu_acceleration_enabled"] is False
    assert flags["stt_window_ensemble"] is True
    assert flags["full_parallel_stt_experiment"] is True


def test_active_runtime_labels_include_vad_and_foreground_actions_without_preview_rows():
    editor = SimpleNamespace(
        _is_ai_processing=True,
        _stt_mode_enabled=True,
        _stt_vad_running=True,
        _last_live_processing_stage="subtitle_optimize subtitle_llm",
        _roughcut_draft_status="idle",
        _roughcut_draft_pending=False,
        _roughcut_draft_thread=None,
        _deferred_project_save_pending=True,
        _deferred_project_save_running=False,
        _auto_export_video_running=True,
        _subtitle_overlay_export_running=False,
        _editor_widget_closing=True,
    )
    window = SimpleNamespace(
        _auto_processing_active=True,
        backend=SimpleNamespace(_active=True),
        backend_fast=SimpleNamespace(_active=False),
        _editor_widget=editor,
    )

    labels = active_runtime_labels_from_window(window)

    assert labels.count("vad") == 1
    assert labels.count("save") == 1
    assert labels.count("export") == 1
    assert labels.count("close") == 1
    assert "pipeline" in labels
    assert "subtitle_optimize" in labels


def test_live_nle_projection_budget_reserves_interactive_core_without_workers(monkeypatch):
    monkeypatch.setattr(
        subtitle_resource_manager,
        "hardware_profile",
        lambda: {"logical_cores": 10, "physical_cores": 10},
    )
    monkeypatch.setattr(
        subtitle_resource_manager,
        "runtime_scheduler_reserve_cores",
        lambda _settings, task="cpu", exiting=False: 1 if not exiting else 0,
    )

    budget = live_nle_projection_scheduler_budget(
        {"runtime_performance_profile": "max"},
        active_labels=["pipeline", "stt", "vad"],
        runtime_resource={"pressure_stage": "normal"},
    )

    assert budget["schema"] == LIVE_NLE_PROJECTION_BUDGET_SCHEMA
    assert budget["projection_allowed"] is True
    assert budget["dedicated_worker_count"] == 0
    assert budget["max_projection_workers"] == 0
    assert budget["shares_subtitle_worker_pool"] is False
    assert budget["uses_existing_row_snapshots"] is True
    assert budget["drops_stale_preview_frames"] is True
    assert budget["interactive_reserve_cores"] == 1
    assert budget["available_worker_budget"] == 9
    assert budget["coalesce_interval_ms"] == 450
    assert budget["quality_policy"] == "final_authority_unchanged"


def test_live_nle_projection_budget_throttles_foreground_and_critical_pressure(monkeypatch):
    monkeypatch.setattr(
        subtitle_resource_manager,
        "hardware_profile",
        lambda: {"logical_cores": 8, "physical_cores": 8},
    )
    monkeypatch.setattr(
        subtitle_resource_manager,
        "runtime_scheduler_reserve_cores",
        lambda _settings, task="cpu", exiting=False: 0,
    )

    warning = live_nle_projection_scheduler_budget(
        {},
        active_labels=["pipeline", "save"],
        runtime_resource={"pressure_stage": "warning"},
    )
    critical = live_nle_projection_scheduler_budget(
        {},
        active_labels=["pipeline", "stt"],
        runtime_resource={"pressure_stage": "critical"},
    )

    assert warning["foreground_action_active"] is True
    assert warning["foreground_action_labels"] == ["save"]
    assert warning["projection_allowed"] is True
    assert warning["dedicated_worker_count"] == 0
    assert warning["coalesce_interval_ms"] == 900
    assert warning["interactive_reserve_cores"] == 1
    assert critical["projection_allowed"] is False
    assert critical["dedicated_worker_count"] == 0
    assert critical["coalesce_interval_ms"] == 900
