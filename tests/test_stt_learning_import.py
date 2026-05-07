from core.stt_mode.learning_events import create_learning_event, import_learning_events_from_project


def test_import_learning_events_from_project_dedupes(tmp_path):
    event = create_learning_event("segment_played", {}, event_id="same")
    project = {"stt_mode_learning": {"events": [event, event]}}

    result = import_learning_events_from_project(project, dataset_dir=str(tmp_path))

    assert result["written"] == 1
    assert result["skipped"] == 0
    assert (tmp_path / "stt_mode_events.jsonl").exists()
