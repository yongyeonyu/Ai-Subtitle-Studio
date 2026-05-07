import json

from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import write_project_file
from core.project.project_manager import load_project, save_project
from core.stt_mode.project_state import attach_stt_mode_state, build_stt_mode_state, project_stt_mode_state


def test_attach_and_read_stt_mode_state_preserves_unknown_fields():
    project = {"stt_mode_state": {"custom": "keep"}}
    state = build_stt_mode_state(work_segments=[{"id": "stt_segment_0001"}])

    attach_stt_mode_state(project, state=state)

    assert project_stt_mode_state(project)["schema"] == "ai_subtitle_studio.stt_mode_state.v1"
    assert project_stt_mode_state(project)["custom"] == "keep"
    assert project_stt_mode_state(project)["work_segments"][0]["id"] == "stt_segment_0001"


def test_build_stt_mode_state_allows_explicit_empty_replacement():
    state = build_stt_mode_state(
        work_segments=[],
        previous_state={"work_segments": [{"id": "old"}]},
    )

    assert state["work_segments"] == []


def test_save_project_updates_stt_mode_state_without_breaking_editor_segments(tmp_path):
    project_path = tmp_path / "sample.json"
    project = {
        "app": "AI Subtitle Studio",
        "version": "test",
        "phase": "PHASE2",
        "project_name": "sample",
        "timeline": {"total_duration": 1.0, "tracks": [{"clips": []}]},
        "subtitles": {"storage": "editor_state.rendering.subtitle_canvas"},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[{"start": 0.0, "end": 1.0, "text": "기존"}],
            primary_fps=30,
        ),
        "workspace": {},
        "user_settings": {},
    }
    write_project_file(str(project_path), project)

    save_project(
        str(project_path),
        segments=[{"start": 0.0, "end": 1.0, "text": "최종"}],
        stt_mode_state=build_stt_mode_state(final_segments=[{"start": 0.0, "end": 1.0, "text": "최종"}]),
    )
    loaded = load_project(str(project_path))

    assert project_stt_mode_state(loaded)["final_segments"][0]["text"] == "최종"
    assert project_segments_to_editor(loaded)[0]["text"] == "최종"
    assert json.loads(project_path.read_text(encoding="utf-8"))["stt_mode_state"]["schema"]
