# Version: 03.09.14
# Phase: PHASE2
import os
import struct
import sys
import tempfile
import threading
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

    def test_transcribe_progress_log_includes_stt_label(self):
        progress = self.processor._format_transcribe_progress("STT2", 125.0, 600.0, 20)

        self.assertEqual(progress, "  ▶ [STT2] 진행 상황: 02분 05초 / 10분 00초 (20%)")

    def test_ensemble_preview_callback_receives_stt2_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, preview_callback=None, **_kwargs):
                seg = {
                    "start": 0.0 if label == "STT1" else 1.0,
                    "end": 0.8 if label == "STT1" else 1.8,
                    "text": label,
                }
                if callable(preview_callback):
                    preview_callback([dict(seg)], label)
                return [seg]

            self.processor._collect_transcribe_result = fake_collect

            result = list(self.processor.transcribe_ensemble(
                tmp,
                preview_callback=lambda segs, label: calls.append((label, list(segs))),
            ))

            self.assertEqual({label for label, _ in calls}, {"STT1", "STT2"})
            stt2_call = next(segs for label, segs in calls if label == "STT2")
            self.assertEqual(stt2_call[0]["text"], "STT2")
            self.assertEqual(result[0][1:], (1, 1))

    def test_ensemble_runs_stt1_and_stt2_on_parallel_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            barrier = threading.Barrier(2)
            thread_names = {}
            preview_calls = []

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, preview_callback=None, **_kwargs):
                thread_names[label] = threading.current_thread().name
                barrier.wait(timeout=2.0)
                seg = {"start": 0.0, "end": 0.8, "text": label}
                if callable(preview_callback):
                    preview_callback([seg], label)
                    seg["text"] = "mutated-after-preview"
                return [{"start": 0.0, "end": 0.8, "text": label}]

            self.processor._collect_transcribe_result = fake_collect

            result = list(self.processor.transcribe_ensemble(
                tmp,
                preview_callback=lambda segs, label: preview_calls.append((label, list(segs))),
            ))

            self.assertEqual(set(thread_names), {"STT1", "STT2"})
            self.assertNotEqual(thread_names["STT1"], thread_names["STT2"])
            self.assertEqual({label for label, _ in preview_calls}, {"STT1", "STT2"})
            self.assertNotIn("mutated-after-preview", [segs[0]["text"] for _, segs in preview_calls])
            self.assertEqual(result[0][1:], (1, 1))

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

    def test_internal_ffmpeg_preprocess_uses_single_pass_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "large.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"video")

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x01\x00" * frames)

                calls = []

                def fake_run(cmd, *, label, timeout=None, env=None):
                    calls.append((label, list(cmd)))
                    write_active_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                    "reuse_preprocessed_audio_cache": True,
                    "ffmpeg_filter_threads": 4,
                }
                self.processor._run_media_command = fake_run
                self.processor._write_grouped_chunks_parallel = lambda *_args, **_kwargs: None

                self.processor.extract_audio(video_path)
                self.processor.extract_audio(video_path)

                self.assertEqual([label for label, _cmd in calls], ["ffmpeg 음량 평탄화"])
                cmd = calls[0][1]
                self.assertIn("-filter_threads", cmd)
                self.assertIn("-threads", cmd)
                self.assertIn("-map", cmd)
                self.assertIn("0:a:0", cmd)
                self.assertIn("-vn", cmd)
                self.assertIn("-sn", cmd)
                self.assertIn("-dn", cmd)
                self.assertIn("-ar", cmd)
                self.assertIn("16000", cmd)
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_ffmpeg_progress_pipe_emits_percent_stage_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            with wave.open(source, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 10)

            class FakeProcess:
                def __init__(self):
                    self.stdout = iter([
                        "out_time_ms=0\n",
                        "out_time_ms=5000000\n",
                        "out_time_ms=10000000\n",
                    ])
                    self.returncode = 0

                def communicate(self, timeout=None):
                    return "", ""

                def wait(self, timeout=None):
                    return self.returncode

            popen_calls = []

            def fake_popen(cmd, **kwargs):
                popen_calls.append((cmd, kwargs))
                return FakeProcess()

            stages = []
            self.processor.stage_callback = stages.append

            with patch("core.audio.media_processor.subprocess.Popen", side_effect=fake_popen):
                ok = self.processor._run_media_command(
                    ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", source, "-acodec", "pcm_s16le", target],
                    label="ffmpeg 음량 평탄화",
                )

            self.assertTrue(ok)
            self.assertIn("-progress", popen_calls[0][0])
            self.assertIn("pipe:1", popen_calls[0][0])
            self.assertTrue(any("0%" in stage for stage in stages))
            self.assertTrue(any("50%" in stage for stage in stages))
            self.assertTrue(any("100%" in stage for stage in stages))

    def test_ffmpeg_progress_suppresses_duplicate_percent_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            with wave.open(source, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 10)

            class FakeProcess:
                def __init__(self):
                    self.stdout = iter([
                        "out_time_ms=0\n",
                        "out_time_ms=100000\n",
                        "out_time_ms=150000\n",
                        "out_time_ms=190000\n",
                        "out_time_ms=200000\n",
                        "out_time_ms=250000\n",
                        "out_time_ms=10000000\n",
                    ])
                    self.returncode = 0

                def wait(self, timeout=None):
                    return self.returncode

            stages = []
            self.processor.stage_callback = stages.append

            with patch("core.audio.media_processor.subprocess.Popen", return_value=FakeProcess()):
                ok = self.processor._run_media_command(
                    ["ffmpeg", "-y", "-i", source, "-acodec", "pcm_s16le", target],
                    label="ffmpeg 오디오 추출",
                )

            self.assertTrue(ok)
            progress = [
                stage.rsplit(" ", 1)[-1]
                for stage in stages
                if "ffmpeg 오디오 추출 진행 중" in stage
            ]
            self.assertEqual(progress, ["0%", "1%", "2%", "99%", "100%"])
            self.assertEqual(len(progress), len(set(progress)))

    def test_vad_progress_suppresses_duplicate_bucket_updates(self):
        stages = []
        self.processor.stage_callback = stages.append

        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 0, force=True)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 1, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 9, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 10, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 19, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 20, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 100, force=True)

        progress = [
            stage.rsplit(" ", 1)[-1]
            for stage in stages
            if "TEN_VAD 오디오 스캔" in stage
        ]
        self.assertEqual(progress, ["0%", "10%", "20%", "100%"])

    def test_audio_heartbeat_emits_elapsed_status(self):
        logs = []
        stages = []

        class FakeStopEvent:
            def __init__(self):
                self.calls = 0
                self.stopped = False

            def wait(self, _interval):
                self.calls += 1
                return self.calls > 1

            def set(self):
                self.stopped = True

        class FakeThread:
            def __init__(self, target, **_kwargs):
                self._target = target

            def start(self):
                self._target()

            def join(self, timeout=None):
                pass

        ticks = iter([100.0, 107.0])
        self.processor.stage_callback = stages.append
        with patch("core.audio.media_processor.threading.Event", FakeStopEvent), \
             patch("core.audio.media_processor.threading.Thread", FakeThread), \
             patch("core.audio.media_processor.time.monotonic", side_effect=lambda: next(ticks)), \
             patch("core.audio.media_processor.get_logger", return_value=SimpleNamespace(log=logs.append)):
            handle = self.processor._start_audio_heartbeat("ClearVoice", "음성 향상", interval_sec=5.0)
            self.processor._stop_audio_heartbeat(handle)

        self.assertIn("⏳ [음성] ClearVoice 음성 향상 중... 7초", stages)
        self.assertIn("  └ [음성] ClearVoice 음성 향상 진행 중... 7초", logs)

    def test_resemble_enhance_wraps_model_run_with_audio_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            open(source, "wb").close()
            calls = []

            def fake_copy(_out_dir, out_wav):
                open(out_wav, "wb").close()
                return True

            self.processor._resolve_python_cli = lambda *_args, **_kwargs: sys.executable
            self.processor._resemble_enhance_device = lambda: "cpu"
            self.processor._run_media_command = lambda *args, **kwargs: calls.append(("run", kwargs.get("label"))) or True
            self.processor._copy_first_wav_from_dir = fake_copy
            self.processor._huggingface_env = lambda: {}
            self.processor._start_audio_heartbeat = lambda label, phase, **_kwargs: calls.append(("start", label, phase)) or ("stop", "thread")
            self.processor._stop_audio_heartbeat = lambda handle: calls.append(("stop", handle))

            self.assertTrue(self.processor._apply_resemble_enhance(source, target))

            self.assertIn(("start", "Resemble Enhance", "음성 향상"), calls)
            self.assertIn(("run", "Resemble Enhance 음성 향상"), calls)
            self.assertIn(("stop", ("stop", "thread")), calls)

    def test_long_no_vad_preprocess_extracts_stt_chunks_directly_from_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "long.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"video")

                calls = []

                def write_silent_wav(path: str, seconds: float = 1.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * frames)

                def fake_no_progress(cmd, *, label, timeout=None, env=None):
                    calls.append((label, list(cmd)))
                    write_silent_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "max_speakers": 1,
                    "ff_chunk": 30,
                    "whisper_chunk_overlap_sec": 0.0,
                    "direct_ffmpeg_chunk_extract": True,
                    "direct_ffmpeg_chunk_min_sec": 10,
                }
                self.processor._media_duration_for_progress = lambda _path: 65.0
                self.processor._run_media_command_no_progress = fake_no_progress
                self.processor._run_media_command = (
                    lambda *_args, **_kwargs: self.fail("direct chunk path must not build full cleaned wav")
                )

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                chunks = sorted(f for f in os.listdir(chunk_dir) if f.endswith(".wav"))
                self.assertEqual(len(chunks), 3)
                self.assertFalse(os.path.exists(os.path.join(tmp, "long_cleaned.wav")))
                self.assertEqual([label for label, _cmd in calls], ["ffmpeg 직접 청크 추출"] * 3)
                first_cmd = calls[0][1]
                self.assertIn("-ss", first_cmd)
                self.assertIn("-t", first_cmd)
                self.assertIn(video_path, first_cmd)
                self.assertIn("-map", first_cmd)
                self.assertIn("0:a:0", first_cmd)
                self.assertIn("-ar", first_cmd)
                self.assertIn("16000", first_cmd)
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
