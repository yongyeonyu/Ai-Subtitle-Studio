# Version: 03.14.00
# Phase: PHASE2
"""Frame timebase augmentation helpers for project JSON documents."""

from collections.abc import Callable

from core.frame_time import frame_count, frame_duration, frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import copy_media_probe_result, probe_media
from core.project.project_analysis_store import (
    VOICE_ACTIVITY_SCHEMA,
    mirror_project_voice_activity_analysis,
    store_project_voice_activity_segments,
)
from core.project.project_format import refresh_project_video_header

ProbeFunc = Callable[[str], dict]


def _get_media_probe(filepath: str, probe_func: ProbeFunc | None = None) -> dict:
    try:
        return copy_media_probe_result((probe_func or probe_media)(filepath))
    except Exception:
        return {}


def _clip_frame_fields(timeline_start: float, timeline_end: float, fps: float, timeline_fps: float) -> dict:
    duration = max(0.0, float(timeline_end) - float(timeline_start))
    source_fps = normalize_fps(fps)
    timeline_fps = normalize_fps(timeline_fps)
    timeline_start_frame = sec_to_frame(timeline_start, timeline_fps)
    timeline_end_frame = sec_to_frame(timeline_end, timeline_fps)
    source_frame_count = frame_count(duration, source_fps)
    return {
        "fps": source_fps,
        "source_frame_rate": source_fps,
        "timeline_frame_rate": timeline_fps,
        "frame_duration": frame_duration(source_fps),
        "timeline_frame_duration": frame_duration(timeline_fps),
        "source_frame_count": source_frame_count,
        "timeline_start_frame": timeline_start_frame,
        "timeline_end_frame": timeline_end_frame,
        "start_frame": timeline_start_frame,
        "end_frame": timeline_end_frame,
        "source_start_frame": 0,
        "source_end_frame": source_frame_count,
        "in_frame": 0,
        "out_frame": source_frame_count,
        "frame_map": {
            "canonical_unit": "frame",
            "timeline_start_frame": timeline_start_frame,
            "timeline_end_frame": timeline_end_frame,
            "source_start_frame": 0,
            "source_end_frame": source_frame_count,
            "timeline_frame_rate": timeline_fps,
            "source_frame_rate": source_fps,
        },
    }


def _clip_for_timeline_time(clips: list[dict], timeline_sec: float) -> tuple[int, dict | None]:
    for idx, clip in enumerate(clips):
        start = float(clip.get("timeline_start", 0.0) or 0.0)
        end = float(clip.get("timeline_end", start) or start)
        if start <= timeline_sec < end - 0.000001:
            return idx, clip
    return (len(clips) - 1, clips[-1]) if clips else (-1, None)


def _augment_vector_subtitle_canvas(project: dict, clips: list[dict], primary_fps: float) -> None:
    editor_state = project.get("editor_state")
    if not isinstance(editor_state, dict):
        return
    rendering = editor_state.get("rendering")
    if not isinstance(rendering, dict):
        return
    canvas = rendering.get("subtitle_canvas")
    if not isinstance(canvas, dict):
        return
    rows = canvas.get("segments")
    if not isinstance(rows, list):
        return

    coordinate_space = canvas.setdefault("coordinate_space", {})
    old_canvas_fps = normalize_fps(coordinate_space.get("timeline_frame_rate") or primary_fps)
    coordinate_space["x"] = "timeline_frame"
    coordinate_space["time_unit"] = "frame"
    coordinate_space["timeline_frame_rate"] = primary_fps

    for row in rows:
        if not isinstance(row, dict):
            continue
        timing = row.setdefault("time", {})
        if not isinstance(timing, dict):
            timing = {}
            row["time"] = timing
        old_fps = normalize_fps(timing.get("timeline_frame_rate") or old_canvas_fps)
        old_start_frame = timing.get("start_frame")
        old_end_frame = timing.get("end_frame")
        if old_start_frame is not None:
            timeline_start = frame_to_sec(old_start_frame, old_fps)
        else:
            timeline_start = float(timing.get("start_sec", 0.0) or 0.0)
        if old_end_frame is not None:
            timeline_end = frame_to_sec(old_end_frame, old_fps)
        else:
            timeline_end = float(timing.get("end_sec", timeline_start) or timeline_start)

        start_frame = sec_to_frame(timeline_start, primary_fps)
        end_frame = max(start_frame, sec_to_frame(max(timeline_start, timeline_end), primary_fps))
        timing.pop("start_sec", None)
        timing.pop("end_sec", None)
        timing.update(
            {
                "unit": "frame",
                "start_frame": start_frame,
                "end_frame": end_frame,
                "timeline_frame_rate": primary_fps,
            }
        )

        clip_idx, clip = _clip_for_timeline_time(clips, timeline_start)
        meta = row.setdefault("meta", {})
        if not isinstance(meta, dict):
            meta = {}
            row["meta"] = meta
        if clip is None:
            meta["source_frame_rate"] = primary_fps
            continue

        source_fps = normalize_fps(clip.get("fps") or clip.get("source_frame_rate") or primary_fps)
        offset = float(clip.get("timeline_start", 0.0) or 0.0)
        meta["clip_local_start_frame"] = sec_to_frame(max(0.0, timeline_start - offset), source_fps)
        meta["clip_local_end_frame"] = sec_to_frame(max(0.0, timeline_end - offset), source_fps)
        meta["source_frame_rate"] = source_fps
        clip_ref = row.setdefault("clip", {})
        if isinstance(clip_ref, dict):
            clip_ref["index"] = clip_idx
            if clip.get("source_path"):
                clip_ref["file"] = str(clip.get("source_path") or "")


def _augment_frame_synced_ranges(rows, primary_fps: float) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
        row_fps = normalize_fps(
            row.get("timeline_frame_rate")
            or frame_range.get("timeline_frame_rate")
            or row.get("frame_rate")
            or primary_fps
        )
        start_frame = row.get("start_frame", row.get("timeline_start_frame", frame_range.get("start")))
        end_frame = row.get("end_frame", row.get("timeline_end_frame", frame_range.get("end")))
        if start_frame is not None:
            start = frame_to_sec(start_frame, row_fps)
        else:
            start = float(row.get("start", row.get("timeline_start", 0.0)) or 0.0)
            start_frame = sec_to_frame(start, primary_fps)
        if end_frame is not None:
            end = frame_to_sec(end_frame, row_fps)
        else:
            end = float(row.get("end", row.get("timeline_end", start)) or start)
            end_frame = sec_to_frame(end, primary_fps)
        start_frame = int(start_frame)
        end_frame = max(start_frame, int(end_frame))
        row["start_frame"] = start_frame
        row["end_frame"] = end_frame
        row["timeline_start_frame"] = start_frame
        row["timeline_end_frame"] = end_frame
        row["frame_rate"] = primary_fps
        row["timeline_frame_rate"] = primary_fps
        row["start"] = frame_to_sec(start_frame, primary_fps)
        row["end"] = max(row["start"], frame_to_sec(end_frame, primary_fps))
        row["timeline_start"] = row["start"]
        row["timeline_end"] = row["end"]
        row["frame_range"] = {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": primary_fps,
        }


def _augment_project_frame_metadata(project: dict, probe_func: ProbeFunc | None = None):
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []) or []
    first_info = {}
    if clips:
        first_path = str(clips[0].get("source_path", "") or "")
        if not (
            float(clips[0].get("fps", 0.0) or 0.0) > 0.0
            and float(clips[0].get("source_duration", 0.0) or 0.0) > 0.0
        ):
            first_info = _get_media_probe(first_path, probe_func=probe_func) if first_path else {}
    primary_fps = normalize_fps((clips[0].get("fps") or first_info.get("fps")) if clips else 30.0)

    for clip in clips:
        path = str(clip.get("source_path", "") or "")
        needs_probe = bool(path) and not (
            float(clip.get("fps", 0.0) or 0.0) > 0.0
            and float(clip.get("source_duration", 0.0) or 0.0) > 0.0
        )
        info = _get_media_probe(path, probe_func=probe_func) if needs_probe else {}
        fps = normalize_fps(clip.get("fps") or info.get("fps") or 30.0)
        start = float(clip.get("timeline_start", 0.0) or 0.0)
        end = float(clip.get("timeline_end", start) or start)
        clip.update(_clip_frame_fields(start, end, fps, primary_fps))
        clip["source_duration"] = float(clip.get("source_duration", info.get("duration", end - start)) or max(0.0, end - start))
        clip["width"] = int(clip.get("width", info.get("width", 0)) or 0)
        clip["height"] = int(clip.get("height", info.get("height", 0)) or 0)

    total_duration = float(project.get("timeline", {}).get("total_duration", 0.0) or 0.0)
    total_frames = frame_count(total_duration, primary_fps)
    project.setdefault("timeline", {})
    project["timeline"]["timebase"] = {
        "unit": "frame",
        "canonical_unit": "frame",
        "mode": "per_clip_frame",
        "primary_fps": primary_fps,
        "frame_duration": frame_duration(primary_fps),
        "timeline_start_frame": 0,
        "timeline_end_frame": total_frames,
        "total_frames": total_frames,
        "seconds_are_derived": True,
        "time_fields_are_compatibility": True,
        "frame_to_seconds": "frame / primary_fps",
        "seconds_to_frame": "floor(seconds * primary_fps)",
        "clips": [
            {
                "id": clip.get("id", ""),
                "order": int(clip.get("order", idx) or idx),
                "timeline_start_frame": int(clip.get("timeline_start_frame", 0) or 0),
                "timeline_end_frame": int(clip.get("timeline_end_frame", 0) or 0),
                "source_start_frame": int(clip.get("source_start_frame", 0) or 0),
                "source_end_frame": int(clip.get("source_end_frame", clip.get("source_frame_count", 0)) or 0),
                "source_frame_rate": normalize_fps(clip.get("source_frame_rate", clip.get("fps", primary_fps))),
            }
            for idx, clip in enumerate(clips)
        ],
    }
    project["frame_timebase"] = dict(project["timeline"]["timebase"])

    media = project.get("media", []) or []
    clip_by_path = {str(c.get("source_path", "")): c for c in clips}
    for item in media:
        clip = clip_by_path.get(str(item.get("path", "")))
        if not clip:
            continue
        fps = normalize_fps(clip.get("fps"))
        item["fps"] = fps
        item["frame_duration"] = frame_duration(fps)
        item["frame_count"] = int(clip.get("source_frame_count", 0) or 0)
        item["offset_frame"] = int(clip.get("timeline_start_frame", 0) or 0)
        item["timeline_start_frame"] = int(clip.get("timeline_start_frame", 0) or 0)
        item["timeline_end_frame"] = int(clip.get("timeline_end_frame", 0) or 0)

    subtitles = project.get("subtitles", {}) or {}
    for seg in subtitles.get("segments", []) or []:
        existing_start_frame = seg.get("start_frame", seg.get("timeline_start_frame"))
        existing_end_frame = seg.get("end_frame", seg.get("timeline_end_frame"))
        if existing_start_frame is not None:
            t_start = frame_to_sec(existing_start_frame, primary_fps)
        else:
            t_start = float(seg.get("timeline_start", seg.get("start", 0.0)) or 0.0)
        if existing_end_frame is not None:
            t_end = frame_to_sec(existing_end_frame, primary_fps)
        else:
            t_end = float(seg.get("timeline_end", seg.get("end", t_start)) or t_start)
        clip = next(
            (
                c for c in clips
                if float(c.get("timeline_start", 0.0) or 0.0)
                <= t_start
                < float(c.get("timeline_end", 0.0) or 0.0) - 0.000001
            ),
            clips[-1] if clips else None,
        )
        fps = normalize_fps(clip.get("fps") if clip else primary_fps)
        offset = float(clip.get("timeline_start", 0.0) or 0.0) if clip else 0.0
        seg["timeline_start_frame"] = sec_to_frame(t_start, primary_fps)
        seg["timeline_end_frame"] = sec_to_frame(t_end, primary_fps)
        seg["start_frame"] = seg["timeline_start_frame"]
        seg["end_frame"] = seg["timeline_end_frame"]
        seg["clip_local_start_frame"] = sec_to_frame(max(0.0, t_start - offset), fps)
        seg["clip_local_end_frame"] = sec_to_frame(max(0.0, t_end - offset), fps)
        seg["frame_rate"] = primary_fps
        seg["timeline_frame_rate"] = primary_fps
        seg["source_frame_rate"] = fps
        seg["timeline_start"] = frame_to_sec(seg["start_frame"], primary_fps)
        seg["timeline_end"] = frame_to_sec(seg["end_frame"], primary_fps)
        seg["start"] = seg["timeline_start"]
        seg["end"] = seg["timeline_end"]
        seg["frame_range"] = {
            "unit": "frame",
            "start": seg["start_frame"],
            "end": seg["end_frame"],
            "clip_local_start": seg["clip_local_start_frame"],
            "clip_local_end": seg["clip_local_end_frame"],
            "timeline_frame_rate": primary_fps,
            "source_frame_rate": fps,
        }

    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state["frame_timebase"] = dict(project["timeline"]["timebase"])
        _augment_vector_subtitle_canvas(project, clips, primary_fps)
        editor_subtitles = editor_state.get("subtitles", {}) or {}
        for seg in editor_subtitles.get("segments", []) or []:
            existing_start_frame = seg.get("start_frame", seg.get("timeline_start_frame"))
            existing_end_frame = seg.get("end_frame", seg.get("timeline_end_frame"))
            if existing_start_frame is not None:
                t_start = frame_to_sec(existing_start_frame, primary_fps)
            else:
                t_start = float(seg.get("start", seg.get("timeline_start", 0.0)) or 0.0)
            if existing_end_frame is not None:
                t_end = frame_to_sec(existing_end_frame, primary_fps)
            else:
                t_end = float(seg.get("end", seg.get("timeline_end", t_start)) or t_start)
            start_frame = sec_to_frame(t_start, primary_fps)
            end_frame = sec_to_frame(t_end, primary_fps)
            seg["start_frame"] = start_frame
            seg["end_frame"] = end_frame
            seg["timeline_start_frame"] = start_frame
            seg["timeline_end_frame"] = end_frame
            seg["frame_rate"] = primary_fps
            seg["timeline_frame_rate"] = primary_fps
            seg["start"] = frame_to_sec(start_frame, primary_fps)
            seg["end"] = frame_to_sec(end_frame, primary_fps)
            seg["frame_range"] = {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": primary_fps,
            }
        stt_state = editor_state.get("stt", {}) or {}
        stt_preview = stt_state.get("preview_segments")
        if isinstance(stt_preview, list):
            stt_state["schema"] = "stt_candidates.v1"
            for idx, seg in enumerate(stt_preview):
                if not isinstance(seg, dict):
                    continue
                start_frame = seg.get("start_frame", seg.get("timeline_start_frame"))
                end_frame = seg.get("end_frame", seg.get("timeline_end_frame"))
                if start_frame is not None:
                    start = frame_to_sec(start_frame, primary_fps)
                else:
                    start = float(seg.get("start", 0.0) or 0.0)
                    start_frame = sec_to_frame(start, primary_fps)
                if end_frame is not None:
                    end = frame_to_sec(end_frame, primary_fps)
                else:
                    end = float(seg.get("end", start) or start)
                    end_frame = sec_to_frame(end, primary_fps)
                seg["index"] = int(seg.get("index", idx + 1) or idx + 1)
                seg["start_frame"] = int(start_frame)
                seg["end_frame"] = int(end_frame)
                seg["timeline_start_frame"] = int(start_frame)
                seg["timeline_end_frame"] = int(end_frame)
                seg["frame_rate"] = primary_fps
                seg["timeline_frame_rate"] = primary_fps
                seg["start"] = frame_to_sec(seg["start_frame"], primary_fps)
                seg["end"] = frame_to_sec(seg["end_frame"], primary_fps)
                seg["stt_pending"] = True
                seg["_live_stt_preview"] = True
                seg["frame_range"] = {
                    "unit": "frame",
                    "start": seg["start_frame"],
                    "end": seg["end_frame"],
                    "timeline_frame_rate": primary_fps,
                }
            editor_state["stt"] = stt_state

    analysis = project.get("analysis")
    if isinstance(analysis, dict):
        for key in (
            "cut_boundary_topicless_middle_segments",
            "topicless_middle_segments",
            "roughcut_topicless_segments",
            "middle_segments",
            "preliminary_middle_segments",
        ):
            _augment_frame_synced_ranges(analysis.get(key), primary_fps)
        segments = analysis.get("voice_activity_segments")
        if isinstance(segments, list):
            store_project_voice_activity_segments(
                project,
                segments,
                schema=str(analysis.get("voice_activity_schema") or VOICE_ACTIVITY_SCHEMA),
                timebase=project["timeline"]["timebase"],
            )
            for idx, seg in enumerate(segments):
                if not isinstance(seg, dict):
                    continue
                start_frame = seg.get("start_frame", seg.get("timeline_start_frame"))
                end_frame = seg.get("end_frame", seg.get("timeline_end_frame"))
                if start_frame is not None:
                    start = frame_to_sec(start_frame, primary_fps)
                else:
                    start = float(seg.get("start", 0.0) or 0.0)
                    start_frame = sec_to_frame(start, primary_fps)
                if end_frame is not None:
                    end = frame_to_sec(end_frame, primary_fps)
                else:
                    end = float(seg.get("end", start) or start)
                    end_frame = sec_to_frame(end, primary_fps)
                seg["index"] = int(seg.get("index", idx + 1) or idx + 1)
                seg["start_frame"] = int(start_frame)
                seg["end_frame"] = int(end_frame)
                seg["timeline_start_frame"] = int(start_frame)
                seg["timeline_end_frame"] = int(end_frame)
                seg["frame_rate"] = primary_fps
                seg["timeline_frame_rate"] = primary_fps
                seg["start"] = frame_to_sec(seg["start_frame"], primary_fps)
                seg["end"] = frame_to_sec(seg["end_frame"], primary_fps)
                seg["frame_range"] = {
                    "unit": "frame",
                    "start": seg["start_frame"],
                    "end": seg["end_frame"],
                    "timeline_frame_rate": primary_fps,
                }
        if isinstance(segments, list):
            mirror_project_voice_activity_analysis(
                project,
                rows=segments,
                timebase=project["timeline"]["timebase"],
            )

    _augment_frame_synced_ranges(project.get("middle_segments"), primary_fps)
    _augment_frame_synced_ranges(project.get("preliminary_middle_segments"), primary_fps)
    _augment_frame_synced_ranges(project.get("roughcut_segments"), primary_fps)
    for key in ("roughcut", "roughcut_draft", "roughcut_result"):
        box = project.get(key)
        if isinstance(box, dict):
            _augment_frame_synced_ranges(box.get("segments"), primary_fps)
    refresh_project_video_header(project)
