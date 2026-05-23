import io

from core.audio.whisperkit_persistent import _write_worker_json_line
from core.native_json import loads_json


class _TextStream(io.StringIO):
    @property
    def encoding(self):
        return "utf-8"


def test_write_worker_json_line_writes_native_bytes_payload():
    stream = io.BytesIO()

    _write_worker_json_line(stream, {"task_id": "t1", "language": "ko", "text": "감사합니다"})

    payload = stream.getvalue()
    assert payload.endswith(b"\n")
    decoded = loads_json(payload)
    assert decoded["task_id"] == "t1"
    assert decoded["text"] == "감사합니다"


def test_write_worker_json_line_preserves_text_stream_compatibility():
    stream = _TextStream()

    _write_worker_json_line(stream, {"task_id": "t2", "language": "ko"})

    payload = stream.getvalue()
    assert payload.endswith("\n")
    decoded = loads_json(payload.encode("utf-8"))
    assert decoded["task_id"] == "t2"
