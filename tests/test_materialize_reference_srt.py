from tools.materialize_reference_srt import materialize_rows_from_json, srt_text_from_rows


def test_materialize_rows_from_json_clips_to_relative_window():
    payload = {
        "start": 10.0,
        "end": 20.0,
        "rows": [
            {"start": 9.5, "end": 10.25, "text": "leading"},
            {"start": 11.0, "end": 12.5, "text": "inside"},
            {"start": 20.0, "end": 21.0, "text": "outside"},
        ],
    }

    rows = materialize_rows_from_json(payload)

    assert rows == [
        {"start": 0.0, "end": 0.25, "text": "leading"},
        {"start": 1.0, "end": 2.5, "text": "inside"},
    ]


def test_srt_text_from_rows_uses_millisecond_timestamps():
    text = srt_text_from_rows([{"start": 1.2344, "end": 2.5, "text": "hello"}])

    assert "00:00:01,234 --> 00:00:02,500" in text
    assert text.startswith("1\n")
