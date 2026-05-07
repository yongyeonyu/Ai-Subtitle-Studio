from core.stt_mode.learning_events import create_learning_event, dedupe_events


def test_learning_event_has_required_metadata_and_strips_audio_by_default():
    event = create_learning_event("segment_played", {"audio_path": "/tmp/a.wav", "count": 1})

    assert event["schema"] == "ai_subtitle_studio.stt_learning_event.v1"
    assert event["event_id"]
    assert event["platform"] == "desktop"
    assert "audio_path" not in event["payload"]


def test_duplicate_event_ids_are_filtered():
    one = create_learning_event("segment_played", {}, event_id="same")
    two = create_learning_event("segment_repeated", {}, event_id="same")

    assert len(dedupe_events([one, two])) == 1
