from __future__ import annotations

import difflib
import re
from typing import Any

from core.engine.subtitle_settings import _get_user_settings, _setting_float, _setting_int
from core.engine.subtitle_text_policy import clean_subtitle_text as _clean
from core.runtime.logger import get_logger

_S = _get_user_settings()
_GAP_BREAK_SEC = _setting_float(_S, "sub_gap_break_sec", 1.5)
_MIN_DURATION = _setting_float(_S, "sub_min_duration", 0.3)
_MAX_CPS = _setting_int(_S, "sub_max_cps", 12)
_DEDUP_WINDOW = _setting_float(_S, "sub_dedup_window", 0.5)

_MIN_CHARS = 5
_PRE_MERGE_MULT = 3.0
_HALLUC_MIN_DUR = 0.8
_HALLUC_MAX_CHARS = 10

_HALLUC_PHRASES = [
    "한국어 대화",
    "자막 생성",
    "번역 중",
    "처리 중",
    "대화 내용",
    "Korean conversation",
    "subtitle",
    "transcription",
    "Thank you for watching",
]


def configure_segment_filter(settings: dict[str, Any] | None) -> None:
    global _GAP_BREAK_SEC, _MIN_DURATION, _MAX_CPS, _DEDUP_WINDOW
    data = dict(settings or {})
    _GAP_BREAK_SEC = _setting_float(data, "sub_gap_break_sec", _GAP_BREAK_SEC)
    _MIN_DURATION = _setting_float(data, "sub_min_duration", _MIN_DURATION)
    _MAX_CPS = _setting_int(data, "sub_max_cps", _MAX_CPS)
    _DEDUP_WINDOW = _setting_float(data, "sub_dedup_window", _DEDUP_WINDOW)


def _compact(text: Any) -> str:
    return str(text or "").replace(" ", "").replace("\n", "")


def sanitize_segments(segments: list[dict], corrections: dict) -> list[dict]:
    result = []
    for seg in segments:
        text = _clean(seg.get("text", ""), corrections)
        if not text:
            continue

        if any(phrase in text for phrase in _HALLUC_PHRASES):
            get_logger().log(f"[삭제-환각문구] '{text[:15]}...'")
            continue

        if not re.search(r"[가-힣a-zA-Z]", text):
            continue

        clean_len = len(_compact(text))
        duration = seg.get("end", 0) - seg.get("start", 0)
        if duration < _HALLUC_MIN_DUR and len(text) > _HALLUC_MAX_CHARS:
            get_logger().log(f"[삭제-환청지어내기] 짧은 구간 과다 텍스트 제거({duration:.2f}초): '{text[:10]}...'")
            continue

        if duration <= _MIN_DURATION:
            get_logger().log(f"[삭제-초단문] {_MIN_DURATION}초 이하 차단({duration:.2f}초): '{text[:15]}...'")
            continue

        cps = clean_len / max(0.01, duration)
        if cps > _MAX_CPS:
            get_logger().log(f"[삭제-환각복붙] 발음 속도({_MAX_CPS}자 초과) 차단(CPS:{cps:.1f}): '{text[:15]}...'")
            continue

        result.append({**seg, "text": text})
    return result


def dedup_close_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments
    result = [segments[0]]
    for seg in segments[1:]:
        prev = result[-1]
        gap = seg["start"] - prev["end"]
        t = _compact(seg["text"])
        pt = _compact(prev["text"])

        if t == pt:
            continue

        if gap < _DEDUP_WINDOW and t and pt and (t in pt or pt in t):
            get_logger().log(f"[삭제-근접포함] 이전 텍스트 겹침 삭제 (Gap: {gap:.2f}s): '{seg['text'][:15]}...'")
            continue

        if gap < 2.0 and len(t) >= 3 and len(pt) >= 3:
            match = difflib.SequenceMatcher(None, pt, t).find_longest_match(0, len(pt), 0, len(t))
            if match.size >= 5 and (match.size / len(t)) >= 0.8:
                get_logger().log(f"[삭제-유사중복] 꼬리물기 중복 삭제: '{seg['text'][:15]}...'")
                continue

        if gap < 0.15 and len(t) < 4:
            continue

        result.append(seg)
    return result


def global_dedup_segments(segments: list[dict]) -> list[dict]:
    result = []
    history = []
    for seg in segments:
        t = _compact(seg["text"])
        if len(t) < 5:
            result.append(seg)
            history.append(t)
            continue

        is_halluc = False
        for past_t in reversed(history[-40:]):
            if len(past_t) < 5:
                continue
            if t in past_t or past_t in t:
                is_halluc = True
                break
            match = difflib.SequenceMatcher(None, past_t, t).find_longest_match(0, len(past_t), 0, len(t))
            if match.size >= 8 and (match.size / len(t)) >= 0.7:
                is_halluc = True
                break

        if is_halluc:
            get_logger().log(f"[삭제-과거복붙] 앵무새 환각 삭제: '{seg['text'][:15]}...'")
            continue

        result.append(seg)
        history.append(t)
    return result


def absorb_tiny_segments(segments: list[dict], threshold: int) -> list[dict]:
    tiny = max(_MIN_CHARS, int(threshold * 0.3))
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(segments):
            seg = segments[i]
            clen = len(_compact(seg["text"]))
            if clen > tiny:
                i += 1
                continue

            if i > 0:
                prev = segments[i - 1]
                gap = seg["start"] - prev["end"]
                if gap < _GAP_BREAK_SEC:
                    merged_text = (prev["text"] + " " + seg["text"]).strip()
                    get_logger().log(f"[흡수-앞] 파편 -> 앞 문장 병합: '{merged_text[:15]}...'")
                    segments[i - 1] = {
                        **prev,
                        "end": seg["end"],
                        "text": merged_text,
                        "words": prev.get("words", []) + seg.get("words", []),
                    }
                    segments.pop(i)
                    changed = True
                    continue

            if i < len(segments) - 1:
                nxt = segments[i + 1]
                gap = nxt["start"] - seg["end"]
                if gap < _GAP_BREAK_SEC:
                    merged_text = (seg["text"] + " " + nxt["text"]).strip()
                    get_logger().log(f"[흡수-뒤] 파편 -> 뒤 문장 병합: '{merged_text[:15]}...'")
                    segments[i + 1] = {
                        **nxt,
                        "start": seg["start"],
                        "text": merged_text,
                        "words": seg.get("words", []) + nxt.get("words", []),
                    }
                    segments.pop(i)
                    changed = True
                    continue

            i += 1
    return segments


def pre_merge_segments(segments: list[dict], threshold: int) -> list[dict]:
    if len(segments) < 2:
        return segments
    max_chars = threshold * _PRE_MERGE_MULT
    groups = [[segments[0]]]

    for seg in segments[1:]:
        prev = groups[-1][-1]
        gap = seg["start"] - prev["end"]
        g_len = sum(len(_compact(s["text"])) for s in groups[-1])
        c_len = len(_compact(seg["text"]))
        p_len = len(_compact(prev["text"]))

        if (
            gap < _GAP_BREAK_SEC
            and (c_len <= threshold * 0.5 or p_len <= threshold * 0.5 or g_len <= threshold)
            and g_len + c_len <= max_chars
        ):
            groups[-1].append(seg)
        else:
            groups.append([seg])

    result = []
    for grp in groups:
        if len(grp) == 1:
            result.append(grp[0])
            continue
        all_words = []
        for row in grp:
            all_words.extend(row.get("words", []))
        merged_text = " ".join(row["text"].strip() for row in grp).strip()
        get_logger().log(f"[병합-문맥] {len(grp)}개 합체: '{merged_text[:15]}...'")
        result.append(
            {
                "start": grp[0]["start"],
                "end": grp[-1]["end"],
                "text": merged_text,
                "speaker": grp[0].get("speaker", "SPEAKER_00"),
                "words": all_words,
            }
        )
    return result


__all__ = [
    "absorb_tiny_segments",
    "configure_segment_filter",
    "dedup_close_segments",
    "global_dedup_segments",
    "pre_merge_segments",
    "sanitize_segments",
]
