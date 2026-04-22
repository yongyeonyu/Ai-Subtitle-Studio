# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/editor_helpers.py
[v01.01.00] Gap 헬퍼 통합 (5~7 방향)
- delete_block_safely, insert_gap_after, merge_adjacent_gaps_around 추가
- is_gap_block, make_gap_ud 유틸 추가
"""
from PyQt6.QtGui import QTextCursor
from ui.subtitle_text_edit import SubtitleBlockData


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
    return SubtitleBlockData("00", round(float(start_sec), 2), is_gap=True)


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