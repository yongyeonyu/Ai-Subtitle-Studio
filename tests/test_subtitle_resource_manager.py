from core.runtime.subtitle_resource_manager import (
    apple_m_accelerator_flag_report,
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
