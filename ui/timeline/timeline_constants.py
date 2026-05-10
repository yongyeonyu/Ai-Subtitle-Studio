# Version: 03.10.01
# Phase: PHASE2
"""
ui/timeline_constants.py
Timeline constants and shared utilities
"""

from core.frame_time import frame_count, frame_to_sec, normalize_segment_to_frame_grid

RULER_H = 30
WAVE_H = 34

SEG_TOP_GAP = 34
SEG_TOP = RULER_H + WAVE_H + SEG_TOP_GAP

SUBTITLE_TOP = SEG_TOP + 8
SUBTITLE_BOT = SEG_TOP + 48
STT1_TOP = SUBTITLE_BOT + 5
STT1_BOT = STT1_TOP + 34
STT2_TOP = STT1_BOT + 5
STT2_BOT = STT2_TOP + 34
SPEAKER_TOP = STT2_BOT + 5
SPEAKER_BOT = SPEAKER_TOP + 22
VOICE_ACTIVITY_TOP = SPEAKER_BOT + 5
VOICE_ACTIVITY_BOT = VOICE_ACTIVITY_TOP + 24
# Legacy analysis-lane constants are collapsed because the separate
# "voice/silence" rail is no longer rendered. Silence markers now render as an
# overlay inside the speaker rail.
ANALYSIS_TOP = VOICE_ACTIVITY_BOT + 1
ANALYSIS_BOT = ANALYSIS_TOP
CANVAS_H = VOICE_ACTIVITY_BOT + 6
SEG_BOT = CANVAS_H
SEG_H = SEG_BOT - SEG_TOP
DIAMOND_Y = SUBTITLE_BOT + 2
LANE_LABEL_GUTTER_W = 92

WAVE_MID = RULER_H + (WAVE_H // 2)
WAVE_HALF = (WAVE_H // 2) - 3

ICON_SZ = 20
HANDLE_R = 16
EDGE_HIT = 15
SEGMENT_HANDLE_MIN_WIDTH = 56

FOCUS_BORDER_COLOR = "#FFFF00"
FOCUS_BORDER_WIDTH = 2


def _build_gaps(segs: list[dict], total_dur: float, fps: float = 30.0) -> list[dict]:
    real = [
        normalize_segment_to_frame_grid(s, fps, min_frames=1)
        for s in list(segs or [])
        if isinstance(s, dict) and not s.get("is_gap") and not bool(s.get("stt_pending") or s.get("_live_stt_preview"))
    ]
    real.sort(key=lambda s: (int(s.get("timeline_start_frame", 0) or 0), int(s.get("timeline_end_frame", 0) or 0)))

    gaps: list[dict] = []
    total_frames = max(0, frame_count(total_dur, fps))

    if real:
        first_start_frame = int(real[0].get("timeline_start_frame", 0) or 0)
    else:
        first_start_frame = 0
    if real and first_start_frame > 0:
        gaps.append(
            {
                "start": 0.0,
                "end": frame_to_sec(first_start_frame, fps),
                "text": "",
                "line": -1,
                "is_gap": True,
                "active": False,
            }
        )

    for i in range(len(real) - 1):
        gs_frame = int(real[i].get("timeline_end_frame", 0) or 0)
        ge_frame = int(real[i + 1].get("timeline_start_frame", gs_frame) or gs_frame)
        if ge_frame > gs_frame:
            gaps.append(
                {
                    "start": frame_to_sec(gs_frame, fps),
                    "end": frame_to_sec(ge_frame, fps),
                    "text": "",
                    "line": -(i + 2),
                    "is_gap": True,
                    "active": False,
                }
            )

    last_end_frame = int(real[-1].get("timeline_end_frame", 0) or 0) if real else 0
    if real and last_end_frame < total_frames:
        gaps.append(
            {
                "start": frame_to_sec(last_end_frame, fps),
                "end": frame_to_sec(total_frames, fps),
                "text": "",
                "line": -(len(real) + 10),
                "is_gap": True,
                "active": False,
            }
        )

    return gaps
