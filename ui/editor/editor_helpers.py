# Version: 02.03.00
# Phase: PHASE1-B
"""
ui/editor_helpers.py
[v01.01.00] Gap 헬퍼 통합 (5~7 방향)
- delete_block_safely, insert_gap_after, merge_adjacent_gaps_around 추가
- is_gap_block, make_gap_ud 유틸 추가
"""
from bisect import bisect_right

from PyQt6.QtGui import QTextCursor
from ui.editor.subtitle_text_edit import SubtitleBlockData


# ---------------------------------------------------------
# Segment 검색
# ---------------------------------------------------------
def find_segment_at(segs, sec, skip_gap=True):
    """segs 리스트에서 sec 시간을 포함하는 세그먼트 반환 (없으면 None)"""
    for seg in segs:
        if skip_gap and seg.get("is_gap"):
            continue
        if seg["start"] <= sec < seg["end"]:
            return seg
    return None


def build_segment_lookup(segs) -> dict:
    """Build an in-memory lookup table for playback/editor subtitle sync."""
    ordered = sorted(
        [dict(seg) for seg in list(segs or []) if isinstance(seg, dict)],
        key=lambda seg: (float(seg.get("start", 0.0) or 0.0), int(seg.get("line", 0) or 0)),
    )
    visible = [
        seg for seg in ordered
        if not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
    ]
    line_map = {
        int(seg.get("line", -1)): seg
        for seg in ordered
        if int(seg.get("line", -1)) >= 0
    }
    return {
        "segments": ordered,
        "starts": [float(seg.get("start", 0.0) or 0.0) for seg in ordered],
        "visible_segments": visible,
        "visible_starts": [float(seg.get("start", 0.0) or 0.0) for seg in visible],
        "line_map": line_map,
        "line_numbers": sorted(line_map.keys()),
    }


def find_segment_at_lookup(lookup: dict | None, sec: float, skip_gap=True):
    """Binary-search a segment lookup table for the segment containing sec."""
    if not isinstance(lookup, dict):
        return None
    segments = lookup.get("visible_segments" if skip_gap else "segments") or []
    starts = lookup.get("visible_starts" if skip_gap else "starts") or []
    if not segments or not starts:
        return None
    try:
        now = float(sec)
    except Exception:
        now = 0.0
    idx = bisect_right(starts, now) - 1
    if 0 <= idx < len(segments):
        seg = segments[idx]
        try:
            if float(seg.get("start", 0.0) or 0.0) <= now < float(seg.get("end", 0.0) or 0.0):
                return seg
        except Exception:
            return None
    return None


def find_segment_for_line_lookup(lookup: dict | None, line_num: int):
    """Return the nearest segment at or before a QTextDocument line number."""
    if not isinstance(lookup, dict):
        return None
    line_map = lookup.get("line_map") or {}
    line_numbers = lookup.get("line_numbers") or []
    if not line_numbers:
        return None
    try:
        line = int(line_num)
    except Exception:
        line = 0
    idx = bisect_right(line_numbers, line) - 1
    if idx < 0:
        return None
    return line_map.get(int(line_numbers[idx]))


def get_sub_block_indices(doc, line_num, start_sec, tol=0.05):
    """같은 start_sec를 공유하는 연속 블록 인덱스 리스트 반환"""
    indices = [line_num]
    for i in range(line_num + 1, doc.blockCount()):
        b = doc.findBlockByNumber(i)
        ud = b.userData()
        if (isinstance(ud, SubtitleBlockData)
                and not ud.is_gap
                and abs(ud.start_sec - start_sec) < tol):
            indices.append(i)
        else:
            break
    return indices


# ---------------------------------------------------------
# Gap 블록 유틸
# ---------------------------------------------------------
def is_gap_block(block) -> bool:
    """블록이 유효한 Gap 블록인지 판별"""
    if not block or not block.isValid():
        return False
    ud = block.userData()
    return isinstance(ud, SubtitleBlockData) and bool(getattr(ud, "is_gap", False))


def make_gap_ud(start_sec: float) -> SubtitleBlockData:
    """Gap용 SubtitleBlockData 생성"""
    return SubtitleBlockData("00", round(float(start_sec), 6), is_gap=True)


def delete_block_safely(block):
    """
    블록 1개를 안전하게 삭제.
    ⚠ beginEditBlock 안에서 호출할 것.
    """
    if not block or not block.isValid():
        return
    c = QTextCursor(block)
    c.select(QTextCursor.SelectionType.BlockUnderCursor)
    c.removeSelectedText()
    if c.position() > 0:
        c.deletePreviousChar()
    else:
        c.deleteChar()


def insert_gap_after(block, gap_start_sec: float) -> bool:
    """
    block 뒤에 Gap 블록 1개 삽입.
    ⚠ beginEditBlock 안에서 호출할 것.
    """
    if not block or not block.isValid():
        return False
    c = QTextCursor(block)
    c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    c.insertText("\n")
    c.block().setUserData(make_gap_ud(gap_start_sec))
    return True


def merge_adjacent_gaps_around(gap_block):
    """
    gap_block 주변의 연속 Gap을 하나로 정리.
    - 뒤쪽 Gap → 제거
    - 앞쪽 Gap 존재 시 → 현재 Gap 제거 (앞 Gap 유지)
    ⚠ beginEditBlock 안에서 호출할 것.
    """
    if not gap_block or not gap_block.isValid() or not is_gap_block(gap_block):
        return

    # 1) 뒤쪽 Gap 제거
    nb = gap_block.next()
    if nb.isValid() and is_gap_block(nb):
        delete_block_safely(nb)

    # 2) 앞쪽 Gap 있으면 현재 Gap 제거 (앞 Gap 유지)
    doc = gap_block.document()
    idx = gap_block.blockNumber()
    gap_block = doc.findBlockByNumber(idx)
    if gap_block.isValid() and is_gap_block(gap_block):
        pb = gap_block.previous()
        if pb.isValid() and is_gap_block(pb):
            delete_block_safely(gap_block)
