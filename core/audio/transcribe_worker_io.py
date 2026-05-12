"""Worker I/O helpers for transcription pipelines."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any

from core.runtime.logger import get_logger


def parse_worker_json_line(line: str) -> dict[str, Any] | None:
    line = (line or "").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except Exception as exc:
        get_logger().log(f"  ⚠️ JSON 파싱 오류: {exc}")
        get_logger().log(f"  ⚠️ raw line: {line[:200] if line else 'empty'}")
        return None


def clone_ensemble_chunk_dir(chunk_dir: str, label: str) -> str:
    source = os.path.abspath(str(chunk_dir or ""))
    parent = os.path.dirname(source) or None
    prefix = f".ensemble_{str(label or 'stt').lower()}_"
    target = tempfile.mkdtemp(prefix=prefix, dir=parent)

    def _ignored(name: str) -> bool:
        text = str(name or "")
        return text in {"_stt_recheck", "_fast_stt2_recheck"} or text.startswith(".ensemble_")

    def _link_or_copy(src: str, dst: str) -> None:
        try:
            os.link(src, dst)
        except Exception:
            shutil.copy2(src, dst)

    try:
        shutil.rmtree(target, ignore_errors=True)
        os.makedirs(target, exist_ok=True)
        for root, dirs, files in os.walk(source):
            dirs[:] = [name for name in dirs if not _ignored(name)]
            rel_root = os.path.relpath(root, source)
            out_root = target if rel_root == "." else os.path.join(target, rel_root)
            os.makedirs(out_root, exist_ok=True)
            for name in files:
                if _ignored(name):
                    continue
                _link_or_copy(os.path.join(root, name), os.path.join(out_root, name))
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def whisper_worker_options(settings: dict) -> dict:
    if not bool((settings or {}).get("stt_rescue_whisper_mode", False)):
        return {}
    return {
        "beam_size": 7,
        "best_of": 7,
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 2.2,
        "log_prob_threshold": -0.85,
        "no_speech_threshold": 0.48,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": 0.35,
            "min_speech_duration_ms": 80,
            "min_silence_duration_ms": 180,
            "speech_pad_ms": 220,
        },
        "hallucination_silence_threshold": 0.6,
    }
