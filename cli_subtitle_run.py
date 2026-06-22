#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless CLI Subtitle Generator Entrypoint.

Provides a 0-margin GUI bypassed backend STT console mode.
"""
import sys
import os
import json
import argparse
import threading
from pathlib import Path

# Insert project base path to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtCore import QCoreApplication, QTimer
from core.runtime import config
from core.runtime.logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.project.project_assets import write_srt_track


def print_jsonl(stage: str, progress: float, details: dict = None) -> None:
    payload = {
        "stage": stage,
        "progress": round(progress, 2),
        "timestamp_ms": int(threading.get_ident()),
    }
    if details:
        payload.update(details)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def run_headless_pipeline(args):
    # 1. Load configuration settings
    settings = {}
    if args.settings_json:
        try:
            if os.path.exists(args.settings_json):
                with open(args.settings_json, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            else:
                settings = json.loads(args.settings_json)
        except Exception as exc:
            print_jsonl("CONFIG_ERROR", 0.0, {"error": f"Failed to parse settings: {exc}"})
            QCoreApplication.exit(1)
            return

    # User settings profile merge
    from core.settings_profiles import materialize_user_settings
    from core.accuracy_policy import apply_accuracy_first_runtime_settings

    s = materialize_user_settings({})
    s.update(settings)
    s = apply_accuracy_first_runtime_settings(s)

    if args.model:
        s["selected_whisper_model"] = args.model
    if args.locale:
        s["stt_apple_speech_locale"] = args.locale

    # Enable Apple challenger if requested in settings
    from core.audio.apple_speech_native import apple_speech_challenger_enabled
    challenger_active = apple_speech_challenger_enabled(s)
    print_jsonl("STARTING_PIPELINE", 0.0, {
        "input_video": args.input_video,
        "output_srt": args.output_srt,
        "model": s.get("selected_whisper_model"),
        "apple_challenger": challenger_active
    })

    # 2. Setup 30s TCC Guarddog Watchdog timer
    tcc_guarddog = QTimer()
    tcc_guarddog.setSingleShot(True)
    tcc_guarddog.setInterval(30000)  # 30 seconds

    def on_tcc_timeout():
        print_jsonl("FATAL_TIMEOUT", 0.0, {"error": "TCC authorization lock or ASR hang detected (30s watchdog threshold exceeded)"})
        QCoreApplication.exit(1)

    tcc_guarddog.timeout.connect(on_tcc_timeout)
    tcc_guarddog.start()

    # 3. Instantiate VideoProcessor & execute
    processor = VideoProcessor()
    processor._fast_mode_overrides = s

    # Safe hook stage callbacks to capture internal stages
    def internal_stage_callback(msg: str):
        print_jsonl("PREPROCESSING_STAGE", 15.0, {"log": msg})

    processor.stage_callback = internal_stage_callback

    all_segments = []
    try:
        # Stop watchdog during Whisper execution loop as it has internal timers,
        # but keep TCC guard active specifically around primary API queries.
        print_jsonl("EXTRACTING_AUDIO", 10.0)

        # Audio preprocessing & VAD slicing
        chunk_dir, vad_segments = processor.extract_audio(
            args.input_video,
            target_start_sec=0.0,
            target_end_sec=None,
            is_single_segment=False
        )

        print_jsonl("TRANSCRIBING", 30.0, {"chunks_path": chunk_dir, "vad_count": len(vad_segments)})

        # Core ASR loop (with batch & dynamic warmup improvements)
        for chunk_segs, idx, total in processor.transcribe(
            chunk_dir,
            is_fast_mode=False,
            target_end_sec=None,
            is_single=False
        ):
            # Feed watchdog to prevent false timeouts during long transcribe passes
            tcc_guarddog.start()

            pct = 30.0 + (float(idx) / max(1.0, float(total))) * 60.0
            print_jsonl("TRANSCRIBING_PROGRESS", pct, {"chunk": idx, "total": total})
            all_segments.extend(chunk_segs)

        # 4. Finalize track & write SRT
        tcc_guarddog.stop()
        if not all_segments:
            print_jsonl("EMPTY_RESULT", 100.0, {"warning": "No subtitles were detected"})
            write_srt_track([], args.output_srt)
            QCoreApplication.exit(0)
            return

        print_jsonl("WRITING_SRT", 95.0)
        srt_info = write_srt_track(
            all_segments,
            args.output_srt,
            metadata_source="cli_server_mode",
            metadata_default_fps=30.0
        )

        print_jsonl("SUCCESS", 100.0, {
            "srt_path": args.output_srt,
            "subtitle_count": srt_info.get("count", 0),
            "size_bytes": srt_info.get("size_bytes", 0)
        })
        QCoreApplication.exit(0)

    except Exception as e:
        tcc_guarddog.stop()
        print_jsonl("FATAL_ERROR", 0.0, {"error": str(e)})
        QCoreApplication.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Headless Console Subtitle Studio Runner")
    parser.add_argument("--input-video", required=True, help="Path to input video or audio file")
    parser.add_argument("--output-srt", required=True, help="Path to write the resulting SRT file")
    parser.add_argument("--settings-json", help="Settings overrides dictionary as inline JSON string or path to JSON file")
    parser.add_argument("--model", help="Override default STT model")
    parser.add_argument("--locale", help="Override default Apple speech locale")

    args = parser.parse_args()

    # 1. Initialize Headless QCoreApplication
    app = QCoreApplication(sys.argv)

    # 2. Trigger pipeline on event loop start
    QTimer.singleShot(0, lambda: run_headless_pipeline(args))

    # 3. Enter core event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
