# Version: 01.00.00
"""
ui/timeline_constants.py - 타임라인 위젯에서 사용하는 상수 및 공통 유틸리티
"""

RULER_H  = 18
WAVE_H   = 75
SEG_H    = 90
SEG_TOP  = RULER_H + WAVE_H
SEG_BOT  = SEG_TOP + SEG_H
CANVAS_H = SEG_BOT + 35  # 💡 하단에 버튼 전용 여백 35픽셀을 추가합니다!
WAVE_MID = RULER_H + WAVE_H // 2
WAVE_HALF = WAVE_H // 2 - 3

ICON_SZ  = 20
HANDLE_R = 16      
EDGE_HIT = 15

def _build_gaps(segs: list[dict], total_dur: float) -> list[dict]:
    real = sorted([s for s in segs if not s.get("is_gap")], key=lambda s: s["start"])
    gaps = []
    if real and round(real[0]["start"], 1) > 0.0:
        gaps.append({"start": 0.0, "end": real[0]["start"], "text": "", "line": -1, "is_gap": True, "active": False})
    for i in range(len(real) - 1):
        gs, ge = real[i]["end"], real[i+1]["start"]
        if round(ge - gs, 1) >= 0.1:
            gaps.append({"start": gs, "end": ge, "text": "", "line": -(i+2), "is_gap": True, "active": False})
    if real and round(real[-1]["end"], 1) < round(total_dur, 1):
        gaps.append({"start": real[-1]["end"], "end": total_dur, "text": "", "line": -(len(real)+10), "is_gap": True, "active": False})
    return gaps