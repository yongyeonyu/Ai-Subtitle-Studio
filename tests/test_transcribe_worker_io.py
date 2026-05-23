from __future__ import annotations

from core.audio.transcribe_worker_io import parse_worker_json_line


def test_parse_worker_json_line_accepts_valid_payload():
    payload = parse_worker_json_line(
        '{"task_id":"task-1","index":2,"result":{"text":"안녕하세요","segments":[]}}'
    )

    assert payload is not None
    assert payload["task_id"] == "task-1"
    assert payload["index"] == 2
    assert payload["result"]["text"] == "안녕하세요"


def test_parse_worker_json_line_accepts_binary_payload():
    payload = parse_worker_json_line(
        '{"task_id":"task-bin","index":1,"result":{"text":"바이트","segments":[]}}'.encode("utf-8")
    )

    assert payload is not None
    assert payload["task_id"] == "task-bin"
    assert payload["result"]["text"] == "바이트"


def test_parse_worker_json_line_ignores_non_json_or_invalid_lines():
    assert parse_worker_json_line("") is None
    assert parse_worker_json_line(b"") is None
    assert parse_worker_json_line("progress: loading") is None
    assert parse_worker_json_line(b"progress: loading") is None
    assert parse_worker_json_line('{"task_id":') is None
