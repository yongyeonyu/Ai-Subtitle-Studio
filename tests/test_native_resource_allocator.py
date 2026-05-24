from __future__ import annotations

from unittest.mock import patch

from core.native_resource_allocator import clear_native_resource_allocation_cache, native_resource_allocation, native_task_allocation


def test_native_resource_allocation_uses_swift_core_worker_and_caches():
    clear_native_resource_allocation_cache()
    payload = {
        "ok": True,
        "allocations": {
            "stt": {"task": "stt", "workers": 1},
        },
    }
    with patch("core.native_resource_allocator.IS_MAC", True), \
         patch("core.native_resource_allocator.native_swift_runtime_enabled", return_value=True), \
         patch("core.native_resource_allocator.request_native_core_task", return_value=payload) as request:
        first = native_resource_allocation({}, active_labels=["pipeline"], max_age_sec=10)
        second = native_resource_allocation({}, active_labels=["pipeline"], max_age_sec=10)

    assert first == payload
    assert second == payload
    assert request.call_count == 1
    assert request.call_args.args[0] == "native_resource_allocation"


def test_native_task_allocation_returns_named_task_plan():
    clear_native_resource_allocation_cache()
    payload = {
        "ok": True,
        "allocations": {
            "subtitle_llm": {"task": "subtitle_llm", "workers": 2, "model_slots": 1},
        },
    }
    with patch("core.native_resource_allocator.IS_MAC", True), \
         patch("core.native_resource_allocator.native_swift_runtime_enabled", return_value=True), \
         patch("core.native_resource_allocator.request_native_core_task", return_value=payload):
        allocation = native_task_allocation(
            "subtitle_llm",
            settings={},
            workload=4,
            requested_workers=4,
            active_labels=["pipeline"],
        )

    assert allocation == {"task": "subtitle_llm", "workers": 2, "model_slots": 1}


def test_native_resource_allocation_attaches_default_task_priorities():
    clear_native_resource_allocation_cache()
    payload = {"ok": True, "allocations": {}}
    with patch("core.native_resource_allocator.IS_MAC", True), \
         patch("core.native_resource_allocator.native_swift_runtime_enabled", return_value=True), \
         patch("core.native_resource_allocator.request_native_core_task", return_value=payload) as request:
        native_resource_allocation(
            {},
            requests=[
                {"task": "roughcut_llm", "workload": 1},
                {"task": "vad", "workload": 1},
                {"task": "audio_extract", "workload": 1},
                {"task": "cut_pioneer", "workload": 1},
                {"task": "stt_precision", "workload": 1},
                {"task": "stt2", "workload": 1},
                {"task": "subtitle_llm", "workload": 1},
                {"task": "subtitle_optimize", "workload": 1},
            ],
            max_age_sec=0,
        )

    sent = request.call_args.args[1]
    priorities = {item["task"]: item["priority"] for item in sent["requests"]}
    assert priorities["cut_pioneer"] > priorities["stt_precision"]
    assert priorities["stt_precision"] > priorities["stt2"]
    assert priorities["stt_precision"] > priorities["subtitle_llm"]
    assert priorities["subtitle_llm"] > priorities["subtitle_optimize"]
    assert priorities["subtitle_optimize"] > priorities["audio_extract"]
    assert priorities["audio_extract"] > priorities["vad"]
    assert priorities["vad"] > priorities["roughcut_llm"]
    assert priorities["subtitle_llm"] > priorities["roughcut_llm"]


def test_native_resource_allocation_sends_previous_plan_for_fast_reclaim_delta():
    clear_native_resource_allocation_cache()
    payload = {
        "ok": True,
        "dynamic": {"mode": "immediate_reclaim"},
        "allocations": {
            "roughcut_llm": {"task": "roughcut_llm", "workers": 0, "action": "pause"},
        },
    }
    previous = {
        "allocations": {
            "roughcut_llm": {"task": "roughcut_llm", "workers": 1},
        }
    }
    with patch("core.native_resource_allocator.IS_MAC", True), \
         patch("core.native_resource_allocator.native_swift_runtime_enabled", return_value=True), \
         patch("core.native_resource_allocator.request_native_core_task", return_value=payload) as request:
        result = native_resource_allocation(
            {},
            active_labels=["pipeline"],
            previous_allocation=previous,
            max_age_sec=0,
        )

    assert result == payload
    sent = request.call_args.args[1]
    assert sent["previous_allocation"] == previous


def test_native_resource_allocation_fills_topology_from_hardware_profile_for_swift_gpu_lanes():
    clear_native_resource_allocation_cache()
    payload = {"ok": True, "allocations": {}}
    hardware = {
        "logical_cores": 10,
        "physical_cores": 10,
        "performance_cores": 4,
        "efficiency_cores": 6,
        "gpu_cores": 10,
        "neural_engine_cores": 16,
        "memory_bytes": 16 * 1024 ** 3,
    }
    with patch("core.native_resource_allocator.IS_MAC", True), \
         patch("core.native_resource_allocator.hardware_profile", return_value=hardware), \
         patch("core.native_resource_allocator.native_swift_runtime_enabled", return_value=True), \
         patch("core.native_resource_allocator.request_native_core_task", return_value=payload) as request:
        native_resource_allocation({}, active_labels=["pipeline"], max_age_sec=0)

    sent = request.call_args.args[1]
    assert sent["topology"]["gpu_cores"] == 10
    assert sent["topology"]["neural_engine_cores"] == 16
