import inspect

from core.audio.media_processor import VideoProcessor
from core.audio.media_processor_transcribe import VideoProcessorTranscribeMixin
from core.audio.media_processor_transcribe_policy import VideoProcessorTranscribePolicyMixin
from core.audio.media_processor_transcribe_recheck import VideoProcessorTranscribeRecheckMixin
from core.audio.media_processor_transcribe_run import VideoProcessorTranscribeRunMixin
from core.audio.media_processor_transcribe_windowed import VideoProcessorTranscribeWindowedMixin


def test_transcribe_split_mixins_are_preserved_in_mro():
    mro = VideoProcessorTranscribeMixin.__mro__

    assert VideoProcessorTranscribeRunMixin in mro
    assert VideoProcessorTranscribePolicyMixin in mro
    assert VideoProcessorTranscribeRecheckMixin in mro
    assert VideoProcessorTranscribeWindowedMixin in mro


def test_runtime_entrypoints_remain_bound_instance_methods():
    processor = VideoProcessor()

    selective_params = list(inspect.signature(processor._transcribe_selective_ensemble).parameters)
    parse_params = list(inspect.signature(processor._parse_whisper_payload).parameters)
    windowed_params = list(inspect.signature(processor._windowed_float).parameters)
    progress_params = list(inspect.signature(processor._format_transcribe_progress).parameters)
    profile_params = list(inspect.signature(processor._whisperkit_compute_profile_from_native_units).parameters)

    assert selective_params[0] == "chunk_dir"
    assert parse_params[0] == "data"
    assert windowed_params == ["settings", "key", "default", "minimum", "maximum"]
    assert progress_params == ["log_label", "current_sec", "total_sec", "pct"]
    assert profile_params[0] == "compute_units"


def test_windowed_static_helpers_keep_original_binding():
    processor = VideoProcessor()

    assert processor._windowed_float({"ratio": "2.5"}, "ratio", 1.0, 0.0, 5.0) == 2.5
    assert processor._window_items_for_range(
        [{"ov_start_offset": 1.0, "duration": 2.0}, {"ov_start_offset": 5.0, "duration": 1.0}],
        0.0,
        4.0,
    ) == [{"ov_start_offset": 1.0, "duration": 2.0}]


def test_parse_whisper_payload_keeps_text_and_absolute_timing():
    processor = VideoProcessor()
    payload = {
        "backend": "unit",
        "word_timestamps": True,
        "segments": [
            {
                "start": 0.25,
                "end": 1.25,
                "text": " 안녕하세요 ",
                "words": [
                    {"word": " 안녕", "start": 0.25, "end": 0.7, "probability": 0.9},
                    {"word": "하세요 ", "start": 0.7, "end": 1.25, "probability": 0.9},
                ],
            }
        ],
    }
    item = {"ov_start_offset": 10.0, "duration": 3.0, "input_path": "/tmp/chunk.wav"}

    segments = processor._parse_whisper_payload(payload, item, [], target_end_sec=None, is_single=False)

    assert len(segments) == 1
    assert segments[0]["text"] == "안녕 하세요"
    assert segments[0]["start"] == 10.25
    assert segments[0]["end"] == 11.25
    assert segments[0]["asr_metadata"]["word_timestamps_available"] is True
