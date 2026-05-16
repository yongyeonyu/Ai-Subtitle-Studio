# Version: 03.14.32
# Phase: PHASE2
"""Gap settings preview simulator widget."""

from __future__ import annotations

import math
import re
from copy import deepcopy

from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QFontMetrics
from PyQt6.QtCore import Qt, QRect
from core.runtime import config
from ui.gpu_rendering import accelerated_widget_base, configure_lightweight_paint, configure_opengl_widget, gpu_backend_name
from ui.style import COLORS


GapSimulatorBase = accelerated_widget_base()


DEFAULT_SIM_BLOCKS = [
    {
        "id": 1,
        "start": 1.0,
        "end": 4.4,
        "text": "이 차는 BMW X5 40i 모델이고 대기가 두 달 정도 걸립니다",
        "kind": "normal",
    },
    {"id": 2, "start": 4.65, "end": 4.82, "text": "어", "kind": "noise"},
    {"id": 3, "start": 5.25, "end": 5.75, "text": "시청해주셔서감사합니다구독", "kind": "cps"},
    {"id": 4, "start": 6.45, "end": 7.25, "text": "그쵸 그쵸 그쵸", "kind": "repeat"},
    {"id": 5, "start": 7.35, "end": 8.05, "text": "그쵸 그쵸", "kind": "repeat"},
    {
        "id": 6,
        "start": 9.4,
        "end": 13.7,
        "text": "핸들이 묵직해졌고 반응이 즉각적이라서 운전이 편합니다",
        "kind": "long",
    },
    {"id": 7, "start": 15.9, "end": 16.45, "text": "와 좋다", "kind": "short"},
    {"id": 8, "start": 17.9, "end": 21.1, "text": "실내로 들어오면 소음이 훨씬 줄어든 게 느껴져요", "kind": "normal"},
]

DEFAULT_CONFIRMED_CUT_BOUNDARIES = [8.8, 14.8]
DEFAULT_PROVISIONAL_CUT_BOUNDARIES = [13.55, 16.7]


def _num(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _token_overlap(left: str, right: str) -> float:
    left_chars = set(_compact_text(left))
    right_chars = set(_compact_text(right))
    if not left_chars or not right_chars:
        return 0.0
    return len(left_chars & right_chars) / max(1, min(len(left_chars), len(right_chars)))


def _split_text_evenly(text: str, count: int) -> list[str]:
    text = str(text or "").strip()
    count = max(1, int(count or 1))
    if count <= 1 or len(text) <= 1:
        return [text]
    chunk = max(1, math.ceil(len(text) / count))
    parts = [text[i:i + chunk].strip() for i in range(0, len(text), chunk)]
    if len(parts) > count:
        parts[count - 1] = "".join(parts[count - 1:])
        parts = parts[:count]
    return [part for part in parts if part]


def _split_text_by_ratio(text: str, ratio: float) -> tuple[str, str]:
    text = str(text or "").strip()
    ratio = max(0.05, min(0.95, float(ratio or 0.5)))
    if len(text) <= 1:
        return text, ""
    words = text.split()
    if len(words) > 1:
        cut_idx = max(1, min(len(words) - 1, int(round(len(words) * ratio))))
        return " ".join(words[:cut_idx]).strip(), " ".join(words[cut_idx:]).strip()
    cut_idx = max(1, min(len(text) - 1, int(round(len(text) * ratio))))
    return text[:cut_idx].strip(), text[cut_idx:].strip()


def _normalise_cut_boundaries(values) -> list[float]:
    boundaries = []
    for item in values or []:
        if isinstance(item, dict):
            item = (
                item.get("timeline_sec")
                or item.get("time")
                or item.get("seconds")
                or item.get("sec")
                or item.get("start")
            )
        sec = round(_num(item, -1.0), 3)
        if sec <= 0:
            continue
        if any(abs(sec - existing) < 0.01 for existing in boundaries):
            continue
        boundaries.append(sec)
    return sorted(boundaries)


def _refresh_timing_meta(row: dict) -> dict:
    start = _num(row.get("start"), 0.0)
    end = max(start + 0.01, _num(row.get("end"), start + 0.01))
    row["start"] = round(start, 3)
    row["end"] = round(end, 3)
    row["chars"] = len(_compact_text(row.get("text", "")))
    row["duration"] = max(0.01, row["end"] - row["start"])
    row["cps"] = row["chars"] / row["duration"]
    return row


def _apply_confirmed_cut_alignment(rows: list[dict], boundaries: list[float], snap_window: float) -> tuple[list[dict], int]:
    if not boundaries:
        return [dict(row) for row in rows], 0

    aligned = []
    applied = 0
    min_piece = 0.05
    for row in rows:
        parts = [dict(row)]
        for boundary in boundaries:
            next_parts = []
            for part in parts:
                start = _num(part.get("start"), 0.0)
                end = _num(part.get("end"), start)
                if start + min_piece < boundary < end - min_piece:
                    ratio = (boundary - start) / max(0.01, end - start)
                    left_text, right_text = _split_text_by_ratio(str(part.get("text", "")), ratio)
                    left = dict(part)
                    right = dict(part)
                    left["end"] = boundary
                    right["start"] = boundary
                    left["text"] = left_text
                    right["text"] = right_text
                    left["cut_alignment"] = "정식 컷 분할"
                    right["cut_alignment"] = "정식 컷 분할"
                    left["confirmed_cut"] = boundary
                    right["confirmed_cut"] = boundary
                    next_parts.append(_refresh_timing_meta(left))
                    next_parts.append(_refresh_timing_meta(right))
                    applied += 1
                    continue

                snapped = False
                item = dict(part)
                if abs(end - boundary) <= snap_window and start + min_piece < boundary:
                    item["end"] = boundary
                    snapped = True
                if abs(start - boundary) <= snap_window and boundary + min_piece < _num(item.get("end"), end):
                    item["start"] = boundary
                    snapped = True
                if snapped:
                    item["cut_alignment"] = "정식 컷 스냅"
                    item["confirmed_cut"] = boundary
                    applied += 1
                next_parts.append(_refresh_timing_meta(item))
            parts = next_parts

        base_id = _num(row.get("id"), len(aligned) + 1.0)
        for idx, part in enumerate(parts):
            item = dict(part)
            if len(parts) > 1:
                item["id"] = round(base_id + (idx / 100.0), 3)
            aligned.append(_refresh_timing_meta(item))
    return aligned, applied


def _apply_provisional_cut_alignment(rows: list[dict], boundaries: list[float], snap_window: float) -> tuple[list[dict], int]:
    if not boundaries:
        return [dict(row) for row in rows], 0

    aligned = []
    applied = 0
    min_piece = 0.05
    for row in rows:
        item = dict(row)
        matches = []
        for boundary in boundaries:
            start = _num(item.get("start"), 0.0)
            end = _num(item.get("end"), start)
            if abs(end - boundary) <= snap_window and start + min_piece < boundary:
                item["end"] = boundary
                matches.append(f"{boundary:.1f}s 끝")
                applied += 1
            start = _num(item.get("start"), 0.0)
            end = _num(item.get("end"), start)
            if abs(start - boundary) <= snap_window and boundary + min_piece < end:
                item["start"] = boundary
                matches.append(f"{boundary:.1f}s 시작")
                applied += 1
        if matches:
            prefix = str(item.get("cut_alignment", "") or "")
            item["cut_alignment"] = f"{prefix} · 임시 컷 스냅".strip(" ·")
            item["provisional_cut"] = ", ".join(matches)
        aligned.append(_refresh_timing_meta(item))
    return aligned, applied


def _confirmed_boundary_between(left_sec: float, right_sec: float, boundaries: list[float]) -> float | None:
    low = min(left_sec, right_sec)
    high = max(left_sec, right_sec)
    candidates = [boundary for boundary in boundaries if low - 0.001 <= boundary <= high + 0.001]
    if not candidates:
        return None
    return min(candidates, key=lambda sec: abs(sec - ((left_sec + right_sec) / 2.0)))


def simulate_gap_pipeline(
    params: dict | None = None,
    blocks: list[dict] | None = None,
    confirmed_cut_boundaries: list | None = None,
    provisional_cut_boundaries: list | None = None,
) -> dict:
    """Return each visible simulator stage for gap, split, and deletion rules."""
    params = dict(params or {})
    source_blocks = deepcopy(blocks if blocks is not None else DEFAULT_SIM_BLOCKS)
    if confirmed_cut_boundaries is None:
        confirmed_cut_boundaries = params.get("confirmed_cut_boundaries")
    if provisional_cut_boundaries is None:
        provisional_cut_boundaries = params.get("provisional_cut_boundaries")
    if confirmed_cut_boundaries is None and blocks is None:
        confirmed_cut_boundaries = DEFAULT_CONFIRMED_CUT_BOUNDARIES
    if provisional_cut_boundaries is None and blocks is None:
        provisional_cut_boundaries = DEFAULT_PROVISIONAL_CUT_BOUNDARIES

    confirmed_cuts = _normalise_cut_boundaries(confirmed_cut_boundaries)
    provisional_cuts = _normalise_cut_boundaries(provisional_cut_boundaries)
    cont_thresh = max(0.0, _num(params.get("continuous_threshold"), 2.0))
    push_rate = max(0.0, min(1.0, _num(params.get("gap_push_rate"), 0.7)))
    pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
    single_ext = max(0.0, _num(params.get("single_subtitle_end"), 0.2))
    split_len = max(4.0, _num(params.get("split_length_threshold"), 15.0))
    min_dur = max(0.0, _num(params.get("sub_min_duration"), 0.3))
    max_dur = max(0.3, _num(params.get("sub_max_duration"), 6.0))
    max_cps = max(1.0, _num(params.get("sub_max_cps"), 12.0))
    dedup_win = max(0.0, _num(params.get("sub_dedup_window"), 0.5))
    gap_break = max(0.0, _num(params.get("sub_gap_break_sec"), 1.5))
    confirmed_window = max(0.05, _num(params.get("confirmed_cut_snap_window"), 0.42))
    provisional_window = max(0.05, _num(params.get("provisional_cut_snap_window"), 0.34))

    original = []
    for block in source_blocks:
        row = dict(block)
        row["chars"] = len(_compact_text(row.get("text", "")))
        row["duration"] = max(0.01, _num(row.get("end"), 0.0) - _num(row.get("start"), 0.0))
        row["cps"] = row["chars"] / row["duration"]
        original.append(row)

    filtered = []
    last_kept_text = ""
    last_kept_end = -999.0
    for block in original:
        row = dict(block)
        start = _num(row.get("start"), 0.0)
        end = _num(row.get("end"), start)
        dur = max(0.01, end - start)
        cps = row["chars"] / dur
        gap = start - last_kept_end
        reason = ""
        if dur <= min_dur:
            reason = f"{dur:.1f}s <= 최소 {min_dur:.1f}s"
        elif cps > max_cps:
            reason = f"CPS {cps:.1f} > {max_cps:.0f}"
        elif last_kept_text and gap <= dedup_win and _token_overlap(last_kept_text, row.get("text", "")) >= 0.55:
            reason = f"반복 {gap:.1f}s <= {dedup_win:.1f}s"

        row["delete_reason"] = reason
        row["passed"] = not bool(reason)
        filtered.append(row)
        if not reason:
            last_kept_text = str(row.get("text", "") or "")
            last_kept_end = end

    survivors = [dict(row) for row in filtered if row.get("passed")]
    split_limit = max(4.0, split_len * 1.5)
    split_stage = []
    for row in survivors:
        start = _num(row.get("start"), 0.0)
        end = _num(row.get("end"), start)
        dur = max(0.01, end - start)
        chars = max(1, int(row.get("chars", len(_compact_text(row.get("text", "")))) or 1))
        split_count = max(1, int(math.ceil(chars / split_limit)), int(math.ceil(dur / max_dur)))
        parts = _split_text_evenly(str(row.get("text", "") or ""), split_count)
        split_count = max(1, len(parts))
        for idx, text_part in enumerate(parts):
            part_start = start + (dur * idx / split_count)
            part_end = start + (dur * (idx + 1) / split_count)
            item = dict(row)
            item["id"] = float(row.get("id", 0.0) or 0.0) + (idx / 10.0)
            item["start"] = round(part_start, 3)
            item["end"] = round(part_end, 3)
            item["text"] = text_part
            item["chars"] = len(_compact_text(text_part))
            item["split_applied"] = split_count > 1
            item["split_reason"] = "글자수/최대길이" if split_count > 1 else ""
            split_stage.append(item)

    merge_stage = []
    short_limit = max(3, min(8, int(round(split_len * 0.35))))
    for row in split_stage:
        item = dict(row)
        if merge_stage:
            prev = merge_stage[-1]
            gap = _num(item.get("start"), 0.0) - _num(prev.get("end"), 0.0)
            if int(item.get("chars", 0) or 0) <= short_limit and gap <= gap_break:
                prev["end"] = item["end"]
                prev["text"] = f"{prev.get('text', '')} {item.get('text', '')}".strip()
                prev["chars"] = len(_compact_text(prev.get("text", "")))
                prev["merge_applied"] = True
                prev["merge_reason"] = f"짧은 자막 + 무음 {gap:.1f}s"
                continue
        item["merge_applied"] = False
        merge_stage.append(item)

    cut_stage, confirmed_count = _apply_confirmed_cut_alignment(merge_stage, confirmed_cuts, confirmed_window)
    cut_stage, provisional_count = _apply_provisional_cut_alignment(cut_stage, provisional_cuts, provisional_window)

    tuned = [dict(row) for row in cut_stage]
    for idx in range(len(tuned) - 1):
        cur = tuned[idx]
        nxt = tuned[idx + 1]
        cur_start = _num(cur.get("start"), 0.0)
        cur_end = _num(cur.get("end"), 0.0)
        nxt_start = _num(nxt.get("start"), 0.0)
        gap = nxt_start - cur_end
        hard_boundary = _confirmed_boundary_between(cur_end, nxt_start, confirmed_cuts)
        if gap < 0.0:
            boundary = hard_boundary if hard_boundary is not None else (cur_end + nxt_start) / 2.0
            cur["end"] = round(max(cur_start + 0.05, boundary), 3)
            nxt["start"] = round(max(0.0, cur["end"]), 3)
            cur["gap_action"] = "정식 컷 보호 / 겹침 보정" if hard_boundary is not None else "겹침 보정"
        elif hard_boundary is not None:
            left_room = max(0.0, hard_boundary - cur_end)
            right_room = max(0.0, nxt_start - hard_boundary)
            if gap <= cont_thresh:
                cur["end"] = round(cur_end + min(gap * push_rate, left_room), 3)
                nxt["start"] = round(max(0.0, nxt_start - min(gap * pull_rate, right_room)), 3)
                cur["gap_action"] = f"정식 컷 보호 / 연속 {gap:.1f}s"
            else:
                ext = min(single_ext, gap / 2.0)
                cur["end"] = round(cur_end + min(ext, left_room), 3)
                nxt["start"] = round(max(0.0, nxt_start - min(ext, right_room)), 3)
                cur["gap_action"] = f"정식 컷 보호 +{ext:.1f}s"
        elif gap <= cont_thresh:
            cur["end"] = round(cur_end + (gap * push_rate), 3)
            nxt["start"] = round(max(0.0, nxt_start - (gap * pull_rate)), 3)
            cur["gap_action"] = f"연속 {gap:.1f}s / 앞 {int(push_rate * 100)}%"
        else:
            ext = min(single_ext, gap / 2.0)
            cur["end"] = round(cur_end + ext, 3)
            nxt["start"] = round(max(0.0, nxt_start - ext), 3)
            cur["gap_action"] = f"단일 유지 +{ext:.1f}s"
    if tuned:
        last_end = _num(tuned[-1].get("end"), 0.0)
        if any(abs(last_end - boundary) <= 0.001 for boundary in confirmed_cuts):
            tuned[-1]["gap_action"] = "정식 컷 보호"
        else:
            tuned[-1]["end"] = round(last_end + single_ext, 3)
            tuned[-1]["gap_action"] = f"마지막 유지 +{single_ext:.1f}s"

    return {
        "original": original,
        "filtered": filtered,
        "split": split_stage,
        "merged": merge_stage,
        "cut_aligned": cut_stage,
        "tuned": tuned,
        "cut_boundaries": {
            "confirmed": confirmed_cuts,
            "provisional": provisional_cuts,
        },
        "summary": {
            "deleted": sum(1 for row in filtered if row.get("delete_reason")),
            "split": sum(1 for row in split_stage if row.get("split_applied")),
            "merged": sum(1 for row in merge_stage if row.get("merge_applied")),
            "confirmed_cuts": confirmed_count,
            "provisional_snaps": provisional_count,
            "gap_adjusted": sum(1 for row in tuned if row.get("gap_action")),
        },
    }


class GapSimulatorWidget(GapSimulatorBase):
    """Subtitle gap simulator covering tuning, split, and deletion rules."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(462)
        self.setStyleSheet("background: #0F1518; border: 1px solid #24313A; border-radius: 8px;")
        configure_lightweight_paint(self, opaque=True)
        configure_opengl_widget(self, "settings")
        self.render_backend = gpu_backend_name()
        self.setMouseTracking(True)
        self.hover_rects = []

        self.cont_thresh = 2.0
        self.push_rate = 0.7
        self.pull_rate = 0.3
        self.single_ext = 0.2
        self.split_len = 15
        self.min_dur = 0.3
        self.max_dur = 6.0
        self.max_cps = 12
        self.dedup_win = 0.5
        self.gap_break = 1.5

    def _params(self) -> dict:
        return {
            "continuous_threshold": self.cont_thresh,
            "gap_push_rate": self.push_rate,
            "single_subtitle_end": self.single_ext,
            "split_length_threshold": self.split_len,
            "sub_min_duration": self.min_dur,
            "sub_max_duration": self.max_dur,
            "sub_max_cps": self.max_cps,
            "sub_dedup_window": self.dedup_win,
            "sub_gap_break_sec": self.gap_break,
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor("#0F1518"))
        self.hover_rects.clear()

        simulation = simulate_gap_pipeline(self._params())
        cut_boundaries = simulation.get("cut_boundaries", {})
        confirmed_cuts = cut_boundaries.get("confirmed", [])
        provisional_cuts = cut_boundaries.get("provisional", [])
        boundary_max = max([0.0, *confirmed_cuts, *provisional_cuts])
        max_time = max(
            24.0,
            max(max((_num(row.get("end"), 0.0) for row in simulation["tuned"]), default=22.0), boundary_max) + 1.4,
        )
        offset_x = 22
        usable_w = max(160, rect.width() - (offset_x * 2))
        px_per_sec = usable_w / max_time

        font_main = QFont(config.FONT, 9, QFont.Weight.DemiBold)
        font_small = QFont(config.FONT, 8)
        font_header = QFont(config.FONT, 10, QFont.Weight.DemiBold)
        fm_main = QFontMetrics(font_main)

        def x_for(sec: float) -> int:
            return offset_x + int(max(0.0, float(sec or 0.0)) * px_per_sec)

        def draw_lane_title(y: int, title: str, color: str = "#D6DEE5"):
            painter.setPen(QColor(color))
            painter.setFont(font_header)
            painter.drawText(offset_x, y, title)

        def draw_cut_markers(y_top: int, y_bottom: int):
            painter.setFont(font_small)
            for sec in confirmed_cuts:
                x = x_for(sec)
                pen = QPen(QColor("#D7DCE2"), 1)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(x, y_top, x, y_bottom)
                painter.setPen(QColor("#D7DCE2"))
                painter.drawText(x - 18, y_top - 17, 36, 14, Qt.AlignmentFlag.AlignCenter, "정식")
            for sec in provisional_cuts:
                x = x_for(sec)
                pen = QPen(QColor("#8E949B"), 1)
                pen.setStyle(Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.drawLine(x, y_top, x, y_bottom)
                painter.setPen(QColor("#A9B0B7"))
                painter.drawText(x - 18, y_top - 2, 36, 14, Qt.AlignmentFlag.AlignCenter, "임시")

        def draw_box(y: int, row: dict, color: str, label: str, tooltip: str, *, hatch: bool = False, outline: str = ""):
            start = _num(row.get("start"), 0.0)
            end = max(start + 0.04, _num(row.get("end"), start + 0.04))
            x = x_for(start)
            w = max(int((end - start) * px_per_sec), 7)
            h = 28
            box_rect = QRect(x, y, w, h)
            self.hover_rects.append((box_rect, tooltip))

            painter.setPen(Qt.PenStyle.NoPen)
            brush = QBrush(QColor(color), Qt.BrushStyle.BDiagPattern if hatch else Qt.BrushStyle.SolidPattern)
            painter.setBrush(brush)
            painter.drawRoundedRect(box_rect, 5, 5)
            if outline:
                painter.setPen(QPen(QColor(outline), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box_rect, 5, 5)
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(font_main)
            elided = fm_main.elidedText(str(label or ""), Qt.TextElideMode.ElideRight, max(8, w - 8))
            painter.drawText(box_rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignCenter, elided)

        painter.setPen(QPen(QColor("#5C6871"), 1))
        painter.setFont(font_small)
        axis_y = 24
        painter.drawLine(offset_x, axis_y, offset_x + int(max_time * px_per_sec), axis_y)
        for row in simulation["original"]:
            x_s = x_for(_num(row.get("start"), 0.0))
            x_e = x_for(_num(row.get("end"), 0.0))
            painter.drawLine(x_s, axis_y - 4, x_s, axis_y + 4)
            painter.drawLine(x_e, axis_y - 4, x_e, axis_y + 4)
            painter.drawText(x_s, 5, max(24, x_e - x_s), 15, Qt.AlignmentFlag.AlignCenter, f"{row['duration']:.1f}s")

        draw_lane_title(52, "1. 원본 STT")
        for row in simulation["original"]:
            draw_box(
                58,
                row,
                "#253E56",
                f"{row.get('text', '')} ({row.get('chars', 0)}자)",
                f"원본 후보\n길이 {row.get('duration', 0):.1f}s / CPS {row.get('cps', 0):.1f}",
            )

        draw_lane_title(118, "2. 자막 분할 및 삭제 기준")
        for row in simulation["filtered"]:
            if row.get("delete_reason"):
                draw_box(
                    124,
                    row,
                    "#C84A4A",
                    f"삭제: {row.get('delete_reason', '')}",
                    f"삭제 기준 적용\n{row.get('delete_reason', '')}",
                    hatch=True,
                )
            else:
                draw_box(
                    124,
                    row,
                    "#1684E8",
                    str(row.get("text", "")),
                    f"삭제 기준 통과\n길이 {row.get('duration', 0):.1f}s / CPS {row.get('cps', 0):.1f}",
                )
        for row in simulation["split"]:
            if row.get("split_applied"):
                draw_box(
                    158,
                    row,
                    "#7D5FFF",
                    f"분할: {row.get('text', '')}",
                    f"분할 기준 적용\n{row.get('split_reason', '')}",
                    outline="#B7A7FF",
                )

        draw_lane_title(198, "3. 컷 경계 정렬")
        for row in simulation["cut_aligned"]:
            alignment = str(row.get("cut_alignment") or "컷 경계 영향 없음")
            if "정식" in alignment:
                color = "#5E6470"
                outline = "#D7DCE2"
            elif "임시" in alignment:
                color = "#69717B"
                outline = "#A9B0B7"
            else:
                color = "#256E9A"
                outline = ""
            draw_box(
                204,
                row,
                color,
                str(row.get("text", "")),
                f"컷 경계 정렬\n{alignment}",
                outline=outline,
            )

        draw_lane_title(264, "4. 파라미터 튜닝")
        for row in simulation["tuned"]:
            draw_box(
                270,
                row,
                "#B66A1E" if row.get("gap_action") else "#256E9A",
                str(row.get("text", "")),
                f"간격 파라미터 적용\n{row.get('gap_action', '보정 없음')}",
                outline=COLORS["warning"] if row.get("gap_action") else "",
            )

        draw_lane_title(330, "5. 최종 자막", "#34C759")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#151C20")))
        painter.drawRoundedRect(offset_x, 336, int(max_time * px_per_sec), 30, 5, 5)
        for row in simulation["tuned"]:
            draw_box(
                337,
                row,
                "#34C759",
                str(row.get("text", "")),
                f"최종 간격 적용\n{row.get('gap_action', '')}",
            )

        draw_cut_markers(42, 368)

        summary = simulation["summary"]
        painter.setFont(font_small)
        painter.setPen(QColor("#A9B0B7"))
        painter.drawText(
            offset_x,
            394,
            usable_w,
            22,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            (
                f"삭제 {summary['deleted']}개 · 분할 {summary['split']}개 · "
                f"정식컷 {summary['confirmed_cuts']}개 · 임시스냅 {summary['provisional_snaps']}개 · "
                f"간격 보정 {summary['gap_adjusted']}개"
            ),
        )

        painter.setPen(QPen(QColor("#5C6871"), 1))
        y_axis = 430
        painter.drawLine(offset_x, y_axis, int(offset_x + max_time * px_per_sec), y_axis)
        painter.setFont(font_small)
        painter.setPen(QColor("#AAAAAA"))
        tick_step = 2 if max_time <= 30 else 4
        for t in range(0, int(max_time) + 1, tick_step):
            tx = x_for(float(t))
            painter.drawLine(tx, y_axis - 4, tx, y_axis + 4)
            painter.drawText(tx - 15, y_axis + 7, 30, 14, Qt.AlignmentFlag.AlignCenter, f"{t}s")

    def mouseMoveEvent(self, event):
        pos = event.pos()
        for box_rect, text in self.hover_rects:
            if box_rect.contains(pos):
                QToolTip.showText(event.globalPosition().toPoint(), text, self)
                return
        QToolTip.hideText()
