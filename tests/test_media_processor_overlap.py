# Version: 03.01.22
# Phase: PHASE2
import os
import struct
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

import config
from core.audio.media_processor import VideoProcessor
from core.audio.stt_quality_presets import apply_stt_quality_preset


class MediaProcessorOverlapTests(unittest.TestCase):
    def setUp(self):
        self.processor = VideoProcessor()

    def test_split_range_uses_real_overlap_between_chunks(self):
        chunks = self.processor._split_range_with_overlap(0.0, 80.0, max_chunk_dur=30.0, overlap_sec=3.0)

        self.assertEqual(chunks, [
            {"start": 0.0, "end": 30.0},
            {"start": 27.0, "end": 57.0},
            {"start": 54.0, "end": 80.0},
        ])

    def test_build_grouped_chunks_applies_overlap_to_long_vad_sector(self):
        chunks = self.processor._build_grouped_chunks(
            [{"start": 10.0, "end": 80.0}],
            total_dur=100.0,
            max_chunk_dur=30.0,
            margin=0.0,
            gap_merge_limit=0.0,
            settings={"whisper_chunk_overlap_sec": 2.0},
        )

        self.assertEqual(chunks[0], {"start": 10.0, "end": 40.0})
        self.assertEqual(chunks[1], {"start": 38.0, "end": 68.0})
        self.assertEqual(chunks[2], {"start": 66.0, "end": 80.0})

    def test_dedupe_overlapping_segments_uses_word_timestamps(self):
        chunk = [
            {
                "start": 27.0,
                "end": 32.0,
                "text": "중복 앞부분 새 단어",
                "words": [
                    {"word": "중복", "start": 27.0, "end": 28.0},
                    {"word": "앞부분", "start": 28.0, "end": 29.8},
                    {"word": "새", "start": 30.2, "end": 31.0},
                    {"word": "단어", "start": 31.0, "end": 32.0},
                ],
            }
        ]

        deduped = self.processor._dedupe_overlapping_segments(chunk, previous_end=30.0, dedup_window=0.5)

        self.assertEqual(len(deduped), 1)
        self.assertAlmostEqual(deduped[0]["start"], 30.2)
        self.assertEqual(deduped[0]["text"], "새 단어")
        self.assertEqual([w["word"] for w in deduped[0]["words"]], ["새", "단어"])
        self.assertEqual([w["word"] for w in deduped[0]["asr_metadata"]["words"]], ["새", "단어"])

    def test_parse_whisper_payload_attaches_asr_metadata(self):
        payload = {
            "backend": "unit-test",
            "language_probability": 0.93,
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "테스트",
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.1,
                    "no_speech_prob": 0.03,
                    "temperature": 0.0,
                    "words": [
                        {"word": "테스트", "start": 0.1, "end": 0.9, "confidence": 0.88},
                    ],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 10.0, "end": 11.0, "review_vad": True}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["start"], 10.1)
        self.assertEqual(parsed[0]["end"], 10.9)
        self.assertEqual(parsed[0]["asr_metadata"]["backend"], "unit-test")
        self.assertEqual(parsed[0]["asr_metadata"]["language_probability"], 0.93)
        self.assertEqual(parsed[0]["asr_metadata"]["words"][0]["start"], 10.1)
        self.assertEqual(parsed[0]["asr_metadata"]["vad_alignment"]["vad_aligned"], True)
        self.assertEqual(parsed[0]["quality"]["vad_alignment_score"], 100.0)

    def test_post_stt_vad_does_not_filter_words_before_alignment(self):
        payload = {
            "backend": "unit-test",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "테스트",
                    "words": [{"word": "테스트", "start": 0.1, "end": 0.9}],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 30.0, "end": 31.0, "post_stt_align": True, "vad_word_filter": False}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["text"], "테스트")

    def test_quality_presets_set_overlap_per_mode(self):
        fast = apply_stt_quality_preset({}, "fast")
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertEqual(fast["whisper_chunk_overlap_sec"], 0.5)
        self.assertLess(fast["whisper_chunk_overlap_sec"], balanced["whisper_chunk_overlap_sec"])
        self.assertLess(balanced["whisper_chunk_overlap_sec"], precise["whisper_chunk_overlap_sec"])
        self.assertEqual(precise["whisper_chunk_overlap_sec"], 3.0)

    def test_quality_review_forces_precise_overlap(self):
        overlap = self.processor._chunk_overlap_sec({
            "whisper_chunk_overlap_sec": 0.5,
            "subtitle_quality_auto_check_after_generate": True,
        })

        self.assertEqual(overlap, 3.0)

    def test_vad_empty_does_not_force_split_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "silent.mp4")
                open(video_path, "wb").close()

                def write_silent_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * frames)

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_silent_wav(cmd[-1])
                    elif label == "ffmpeg 음량 평탄화":
                        write_silent_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_pre_split_enabled": True,
                    "use_basic_filter": False,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = lambda *args, **kwargs: (False, [])
                self.processor._write_grouped_chunks_parallel = (
                    lambda *args, **kwargs: self.fail("VAD empty must not force-split by default")
                )

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual([f for f in os.listdir(chunk_dir) if f.endswith(".wav")], [])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_vad_empty_with_audio_activity_uses_force_split_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "active.mp4")
                open(video_path, "wb").close()

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    samples = [
                        int(9000 * (1 if i % 2 == 0 else -1))
                        for i in range(frames)
                    ]
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_active_wav(cmd[-1])
                    elif label == "ffmpeg 음량 평탄화":
                        write_active_wav(cmd[-1])
                    return True

                written = []
                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_pre_split_enabled": True,
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = lambda *args, **kwargs: (False, [])
                self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual(written, [{"start": 0.0, "end": 4.0}])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_selected_vad_does_not_pre_split_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "active.mp4")
                open(video_path, "wb").close()

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    samples = [
                        int(9000 * (1 if i % 2 == 0 else -1))
                        for i in range(frames)
                    ]
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_active_wav(cmd[-1])
                    elif label == "ffmpeg 음량 평탄화":
                        write_active_wav(cmd[-1])
                    return True

                written = []
                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = (
                    lambda *args, **kwargs: self.fail("VAD must not pre-split STT unless opted in")
                )
                self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual(written, [{"start": 0.0, "end": 4.0}])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_wav_activity_stats_detects_audio_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "voice.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(12000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            stats = self.processor._wav_activity_stats(wav_path)

            self.assertAlmostEqual(stats["duration"], 1.0, places=2)
            self.assertGreater(stats["peak"], 0.3)
            self.assertGreater(stats["rms"], 0.3)

    def test_force_split_activity_threshold_matches_reported_audio(self):
        self.assertFalse(self.processor._has_force_split_activity({"peak": 0.0, "rms": 0.0}, {}))
        self.assertTrue(self.processor._has_force_split_activity({"peak": 0.8515, "rms": 0.1843}, {}))

    def test_vad_retries_with_more_sensitive_threshold_when_audio_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "active.wav")
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(9000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000 * 4)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            calls = []

            def fake_get_speech_timestamps(
                audio_data,
                model,
                *,
                sampling_rate,
                threshold,
                min_speech_duration_ms,
                min_silence_duration_ms,
                speech_pad_ms,
                window_size_samples,
            ):
                calls.append(
                    {
                        "threshold": threshold,
                        "min_speech": min_speech_duration_ms,
                        "min_silence": min_silence_duration_ms,
                        "pad": speech_pad_ms,
                        "window": window_size_samples,
                    }
                )
                if len(calls) < 4:
                    return []
                return [{"start": 1600, "end": 32000}]

            self.processor._vad_loaded = True
            self.processor._vad_model = object()
            self.processor._vad_utils = (
                fake_get_speech_timestamps,
                None,
                lambda _path: [0.0],
                None,
                None,
            )
            written = []
            self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

            with patch.dict("sys.modules", {"torch": SimpleNamespace()}):
                success, timestamps = self.processor._split_with_vad(
                    wav_path,
                    chunk_dir,
                    "silero",
                    {
                        "vad_threshold": 0.55,
                        "vad_min_speech": 0.28,
                        "vad_min_silence": 1.2,
                        "vad_speech_pad": 0.1,
                        "vad_window_size": 512,
                        "review_vad_before_stt_enabled": False,
                    },
                )

            self.assertTrue(success)
            self.assertEqual(len(calls), 4)
            self.assertLess(calls[1]["threshold"], calls[0]["threshold"])
            self.assertLess(calls[2]["threshold"], calls[1]["threshold"])
            self.assertLess(calls[3]["threshold"], calls[2]["threshold"])
            self.assertLessEqual(calls[3]["min_speech"], calls[1]["min_speech"])
            self.assertLessEqual(calls[3]["min_silence"], calls[1]["min_silence"])
            self.assertEqual(timestamps[0]["start"], 0.0)
            self.assertTrue(written)

    def test_vad_retry_rejects_noisy_micro_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "noisy.wav")
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(9000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000 * 4)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            calls = []

            def fake_get_speech_timestamps(
                audio_data,
                model,
                *,
                sampling_rate,
                threshold,
                min_speech_duration_ms,
                min_silence_duration_ms,
                speech_pad_ms,
                window_size_samples,
            ):
                calls.append(threshold)
                if len(calls) == 1:
                    return []
                return [
                    {"start": i * 1600, "end": i * 1600 + 800}
                    for i in range(16)
                ]

            self.processor._vad_loaded = True
            self.processor._vad_model = object()
            self.processor._vad_utils = (
                fake_get_speech_timestamps,
                None,
                lambda _path: [0.0],
                None,
                None,
            )
            self.processor._write_grouped_chunks_parallel = (
                lambda *_args, **_kwargs: self.fail("Noisy micro VAD segments must be rejected")
            )

            with patch.dict("sys.modules", {"torch": SimpleNamespace()}):
                success, timestamps = self.processor._split_with_vad(
                    wav_path,
                    chunk_dir,
                    "silero",
                    {
                        "vad_threshold": 0.55,
                        "vad_min_speech": 0.28,
                        "vad_min_silence": 1.2,
                        "vad_speech_pad": 0.1,
                        "vad_window_size": 512,
                        "review_vad_before_stt_enabled": False,
                    },
                )

            self.assertFalse(success)
            self.assertEqual(timestamps, [])
            self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
