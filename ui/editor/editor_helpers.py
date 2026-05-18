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


def _segment_sort_key(seg: dict) -> tuple[float, int]:
    try:
        start = float(seg.get("start", 0.0) or 0.0)
    except Exception:
        start = 0.0
    try:
        line = int(seg.get("line", 0) or 0)
    except Exception:
        line = 0
    return start, line


def build_segment_lookup(segs) -> dict:
    """Build an in-memory lookup table for playback/editor subtitle sync."""
    source = segs if isinstance(segs, list) else list(segs or [])
    ordered = []
    starts = []
    lines = []
    previous_key: tuple[float, int] | None = None
    sorted_ok = True
    for seg in source:
        if not isinstance(seg, dict):
            continue
        key = _segment_sort_key(seg)
        if previous_key is not None and key < previous_key:
            sorted_ok = False
        previous_key = key
        starts.append(key[0])
        lines.append(key[1])
        ordered.append(seg)
    if not sorted_ok:
        entries = sorted(zip(starts, lines, ordered), key=lambda item: (item[0], item[1]))
        starts = [item[0] for item in entries]
        lines = [item[1] for item in entries]
        ordered = [item[2] for item in entries]

    visible = []
    visible_starts = []
    line_map = {}
    for start, line, seg in zip(starts, lines, ordered):
        if not seg.get("is_gap") and str(seg.get("text", "") or "").strip():
            visible.append(seg)
            visible_starts.append(start)
        if line >= 0:
            line_map[line] = seg
    return {
        "segments": ordered,
        "starts": starts,
        "visible_segments": visible,
        "visible_starts": visible_starts,
        "line_map": line_map,
        "line_numbers": sorted(line_map.keys()),
    }


def segment_has_multi_speaker_payload(seg: dict | None) -> bool:
    """Return True only when a row explicitly carries multiple speakers."""
    if not isinstance(seg, dict):
        return False
    speakers = []
    for item in list(seg.get("speaker_list") or []):
        speaker = str(item or "").strip()
        if speaker:
            speakers.append(speaker)
    if len(set(speakers)) >= 2:
        return True
    speaker = str(seg.get("speaker", seg.get("spk", "")) or "").strip()
    second_speaker = str(seg.get("speaker2", "") or "").strip()
    return bool(speaker and second_speaker and speaker != second_speaker)


def should_split_multiline_part_into_block(seg: dict | None, part: str) -> bool:
    """Split multiline subtitle parts into separate QTextBlocks only for true speaker-split rows."""
    if not str(part or "").startswith("-"):
        return False
    return segment_has_multi_speaker_payload(seg)


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
    anchor = doc.findBlockByNumber(int(line_num))
    anchor_ud = anchor.userData() if anchor.isValid() else None
    if not isinstance(anchor_ud, SubtitleBlockData):
        return [line_num]
    if bool(anchor_ud.is_gap):
        return [line_num]

    anchor_start = float(getattr(anchor_ud, "start_sec", start_sec))
    anchor_end = getattr(anchor_ud, "end_sec", None)
    indices = [line_num]
    for i in range(line_num + 1, doc.blockCount()):
        b = doc.findBlockByNumber(i)
        ud = b.userData()
        if not (isinstance(ud, SubtitleBlockData) and not ud.is_gap):
            break
        if abs(float(ud.start_sec) - anchor_start) >= tol:
            break
        next_end = getattr(ud, "end_sec", None)
        if anchor_end is not None and next_end is not None and abs(float(next_end) - float(anchor_end)) >= tol:
            break
        indices.append(i)
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
