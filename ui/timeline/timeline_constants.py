# Version: 03.09.26
# Phase: PHASE2
"""
ui/timeline_constants.py
Timeline constants and shared utilities
"""

RULER_H = 30
WAVE_H = 34

CANVAS_H = 314
SEG_TOP_GAP = 34
SEG_TOP = RULER_H + WAVE_H + SEG_TOP_GAP
SEG_BOT = CANVAS_H
SEG_H = SEG_BOT - SEG_TOP

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
ANALYSIS_TOP = VOICE_ACTIVITY_BOT + 4
ANALYSIS_BOT = ANALYSIS_TOP + 24
DIAMOND_Y = SUBTITLE_BOT + 2

WAVE_MID = RULER_H + (WAVE_H // 2)
WAVE_HALF = (WAVE_H // 2) - 3

ICON_SZ = 20
HANDLE_R = 16
EDGE_HIT = 15
SEGMENT_HANDLE_MIN_WIDTH = 56

FOCUS_BORDER_COLOR = "#FFFF00"
FOCUS_BORDER_WIDTH = 2


def _build_gaps(segs: list[dict], total_dur: float) -> list[dict]:
    real = sorted(
        [
            s for s in segs
            if not s.get("is_gap") and not bool(s.get("stt_pending") or s.get("_live_stt_preview"))
        ],
        key=lambda s: s["start"],
    )

    gaps: list[dict] = []

    if real and round(real[0]["start"], 1) > 0.0:
        gaps.append(
            {
                "start": 0.0,
                "end": real[0]["start"],
                "text": "",
                "line": -1,
                "is_gap": True,
                "active": False,
            }
        )

    for i in range(len(real) - 1):
        gs = real[i]["end"]
        ge = real[i + 1]["start"]
        if round(ge - gs, 1) >= 0.1:
            gaps.append(
                {
                    "start": gs,
                    "end": ge,
                    "text": "",
                    "line": -(i + 2),
                    "is_gap": True,
                    "active": False,
                }
            )

    if real and round(real[-1]["end"], 1) < round(total_dur, 1):
        gaps.append(
            {
                "start": real[-1]["end"],
                "end": total_dur,
                "text": "",
                "line": -(len(real) + 10),
                "is_gap": True,
                "active": False,
            }
        )

    return gaps
