# Version: 03.00.26
# Phase: PHASE2
from __future__ import annotations


TABLE_COLUMNS = ("시간", "썸네일", "기존 자막", "챕터 주제", "태그", "상태", "판단", "안전", "출력")
EDITABLE_COLUMNS = {3, 4}


def fmt_time(sec: float | None) -> str:
    value = max(0.0, float(sec or 0.0))
    minutes, seconds = divmod(value, 60.0)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"
