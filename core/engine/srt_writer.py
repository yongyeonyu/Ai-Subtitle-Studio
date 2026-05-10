# Version: 02.07.00
# Phase: PHASE1-D
"""
SRT 저장 / 화자 컬러 SRT / 자막백업 생성.
"""
import json
import os
from datetime import datetime

from core.frame_time import normalize_fps, normalize_segments_to_frame_grid
from core.runtime import config
from core.utils import seconds_to_srt_time
from core.runtime.logger import get_logger
from core.project.project_srt import strip_whisper_control_tokens


def _normalize_saved_subtitle_text(text: str) -> str:
    text = strip_whisper_control_tokens(str(text or "")).replace(".", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _infer_save_fps(segments: list[dict], fps: float | int | str | None = None) -> float | None:
    try:
        if fps is not None and float(fps) > 0.0:
            return normalize_fps(fps)
    except (TypeError, ValueError):
        pass
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        frame_range = seg.get("frame_range")
        if isinstance(frame_range, dict):
            value = frame_range.get("timeline_frame_rate")
            try:
                if value is not None and float(value) > 0.0:
                    return normalize_fps(value)
            except (TypeError, ValueError):
                pass
        for key in ("timeline_frame_rate", "frame_rate"):
            value = seg.get(key)
            try:
                if value is not None and float(value) > 0.0:
                    return normalize_fps(value)
            except (TypeError, ValueError):
                continue
    return None


def save_srt(
    segments: list[dict],
    srt_path: str,
    apply_offset: bool = True,
    adjust_timing_func=None,
    fps: float | int | str | None = None,
    write_backup: bool = True,
):
    if apply_offset and callable(adjust_timing_func):
        segments = adjust_timing_func(segments)

    effective_fps = _infer_save_fps(segments, fps)
    prepared_segments = (
        normalize_segments_to_frame_grid(segments, effective_fps, min_frames=1, preserve_order=True)
        if effective_fps is not None
        else [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    )

    settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
    s = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            pass

    max_speakers = int(s.get("max_speakers", 1))
    unique_speakers = set()
    for seg in segments:
        if "speaker_list" in seg and seg["speaker_list"]:
            unique_speakers.update(seg["speaker_list"])
        elif "speaker" in seg:
            unique_speakers.add(seg["speaker"])

    generate_color_srt = (max_speakers > 1) and (len(unique_speakers) > 1)

    spk1_id = s.get("spk1_id", "00")
    spk1_c = s.get("spk1_color", "#FFFFFF")
    spk2_id = s.get("spk2_id", "01")
    spk2_c = s.get("spk2_color", "#FFFF00")
    spk3_id = s.get("spk3_id", "02")
    spk3_c = s.get("spk3_color", "#00FFFF")
    cmap = {spk1_id: spk1_c, spk2_id: spk2_c, spk3_id: spk3_c}

    lines_plain = []
    lines_color = []
    idx = 1
    seen = set()

    for seg in prepared_segments:
        if seg.get("stt_pending"):
            continue
        text = _normalize_saved_subtitle_text(seg.get("text", ""))
        if not text or text == "\u200B":
            continue

        start_t = max(0.0, seg["start"])
        end_t = seg["end"]
        if end_t <= start_t:
            end_t = start_t + 0.1

        if effective_fps is not None:
            key = (int(seg.get("timeline_start_frame", seg.get("start_frame", -1)) or -1), text)
        else:
            key = (round(start_t, 3), text)
        if key in seen:
            continue
        seen.add(key)

        ts_str = f"{seconds_to_srt_time(start_t)} --> {seconds_to_srt_time(end_t)}"
        lines_plain += [str(idx), ts_str, text, ""]

        spk_list = seg.get("speaker_list", [])
        colored_parts = []
        for i, line in enumerate(text.split('\n')):
            cl = line.strip()
            spk = spk_list[i] if i < len(spk_list) else spk1_id
            color = cmap.get(spk, "#FFFFFF")
            colored_parts.append(f'<font color="{color}">{cl}</font>')

        lines_color += [str(idx), ts_str, "\n".join(colored_parts), ""]
        idx += 1

    target_dir = os.path.dirname(os.path.abspath(srt_path))
    base_name = os.path.splitext(os.path.basename(srt_path))[0]
    backup_dir = os.path.join(target_dir, "자막백업")

    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    plain_srt_path = os.path.join(target_dir, f"{base_name}.srt")
    color_srt_path = os.path.join(target_dir, f"{base_name}_화자.srt")

    plain_content = "\n".join(lines_plain)
    color_content = "\n".join(lines_color)

    with open(plain_srt_path, "w", encoding="utf-8") as f:
        f.write(plain_content)

    if generate_color_srt:
        with open(color_srt_path, "w", encoding="utf-8") as f:
            f.write(color_content)

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")

    if write_backup:
        backup_plain = os.path.join(backup_dir, f"{base_name}_{date_str}_{time_str}.srt")
        with open(backup_plain, "w", encoding="utf-8") as f:
            f.write(plain_content)

        if generate_color_srt:
            backup_color = os.path.join(backup_dir, f"{base_name}_화자_{date_str}_{time_str}.srt")
            with open(backup_color, "w", encoding="utf-8") as f:
                f.write(color_content)

        log_msg = f"✅ 자막 저장 및 자동 백업 완료: {time_str}"
        if not generate_color_srt:
            log_msg += " (단일 화자 감지: 화자 분리 파일 생략)"
    else:
        log_msg = f"✅ 자막 빠른 저장 완료: {time_str}"
        if not generate_color_srt:
            log_msg += " (단일 화자 감지: 화자 분리 파일 생략)"
    get_logger().log(log_msg)
