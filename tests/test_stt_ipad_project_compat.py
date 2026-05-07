from core.stt_mode.project_state import attach_stt_mode_state, build_stt_mode_state, default_stt_mode_learning


def test_ipad_compat_project_contains_portable_stt_sections():
    work = [{
        "id": "stt_segment_0001",
        "start_frame": 0,
        "end_frame": 30,
        "timeline_start_frame": 0,
        "timeline_end_frame": 30,
        "frame_rate": 30.0,
        "timeline_frame_rate": 30.0,
        "frame_range": {"unit": "frame", "start": 0, "end": 30, "timeline_frame_rate": 30.0},
    }]
    raw = [{**work[0], "id": "dictation_raw_0001", "stt_segment_id": "stt_segment_0001", "text": "안녕"}]
    final = [{**work[0], "id": "stt_final_0001", "text": "안녕", "parent_dictation_ids": ["dictation_raw_0001"]}]
    project = {
        "editor_state": {"rendering": {"subtitle_canvas": {"schema": "subtitle_canvas.vector.v2", "segments": []}}},
    }

    attach_stt_mode_state(
        project,
        state=build_stt_mode_state(work_segments=work, raw_dictation_segments=raw, final_segments=final),
        learning=default_stt_mode_learning(),
    )

    state = project["stt_mode_state"]
    assert state["schema"] == "ai_subtitle_studio.stt_mode_state.v1"
    assert state["cross_device"] is True
    assert state["adapter_refs"]["stt_lora_bundle"]
    assert state["raw_dictation_segments"][0]["text"] == "안녕"
    assert state["final_segments"][0]["frame_range"]["unit"] == "frame"
