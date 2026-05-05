# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_input.py
Timeline input mixin
"""
from bisect import bisect_left, bisect_right

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QPolygon

from core.runtime import config
from ui.editor.editor_helpers import find_segment_at

from ui.timeline.speaker_labels import current_speaker_settings, speaker_labels_for_segment
from ui.timeline.timeline_constants import (
    ANALYSIS_BOT,
    ANALYSIS_TOP,
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
    _build_gaps,
)


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class TimelineInputMixin:
    _REVIEW_FLAGS = {
        "non_speech_hallucination_risk",
        "high_no_speech_prob",
        "outside_vad_speech",
        "high_cps",
        "quality_stale",
    }

    def _segment_needs_manual_review(self, seg: dict) -> bool:
        quality = dict(seg.get("quality") or {})
        label = str(quality.get("confidence_label") or "")
        flags = set(str(flag) for flag in (quality.get("flags") or ()))
        manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
        return (
            bool(quality)
            and (
                manually_confirmed
                or label in {"red", "gray"}
                or bool(flags.intersection(self._REVIEW_FLAGS))
                or bool(seg.get("quality_stale"))
            )
        )

    def _is_stt_preview_segment(self, seg: dict) -> bool:
        return bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview"))

    def _stt_preview_source(self, seg: dict) -> str:
        source = (
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or "STT1"
        )
        return str(source or "STT1").strip().upper()

    def _is_readonly_analysis_lane_y(self, y: int) -> bool:
        return (
            VOICE_ACTIVITY_TOP <= int(y) <= VOICE_ACTIVITY_BOT
            or ANALYSIS_TOP <= int(y) <= ANALYSIS_BOT
        )

    def focusNextPrevChild(self, next):
        self._snap_closest_diamond()
        return False

    def keyPressEvent(self, ev):
        if self._edit_active:
            self._handle_edit_key(ev); ev.accept(); return

        if ev.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.active_seg_start is not None:
            candidates = self._active_segment_candidates() if hasattr(self, "_active_segment_candidates") else self.segments
            seg = next(
                (
                    s for s in candidates
                    if not self._is_stt_preview_segment(s)
                    and abs(s["start"] - self.active_seg_start) < 0.5
                ),
                None,
            )
            if seg: self.start_inline_edit(seg.get("line", 0), seg["start"])
            ev.accept(); return

        if ev.key() == Qt.Key.Key_Tab: self._snap_closest_diamond(); ev.accept(); return
        if ev.key() == Qt.Key.Key_Up: self.focus_mode = "waveform"; self.update(); ev.accept(); return
        elif ev.key() == Qt.Key.Key_Down: self.focus_mode = "segment"; self.update(); ev.accept(); return

        if getattr(self, 'focus_mode', '') == "waveform":
            if ev.key() == Qt.Key.Key_Left:
                self.step_frame.emit(-4 if ev.isAutoRepeat() else -1); ev.accept(); return
            elif ev.key() == Qt.Key.Key_Right:
                self.step_frame.emit(4 if ev.isAutoRepeat() else 1); ev.accept(); return
        else:
            if ev.key() == Qt.Key.Key_Left:
                if ev.isAutoRepeat(): self.step_frame.emit(-4)
                else: self._jump_to_prev_segment()
                ev.accept(); return
            elif ev.key() == Qt.Key.Key_Right:
                if ev.isAutoRepeat(): self.step_frame.emit(4)
                else: self._jump_to_next_segment()
                ev.accept(); return
        super().keyPressEvent(ev)

    def _jump_to_prev_segment(self):
        if not self.segments:
            return

        target = None
        for seg in reversed(self._editable_segments_sorted() if hasattr(self, "_editable_segments_sorted") else self.segments):
            if self._is_stt_preview_segment(seg):
                continue
            if seg["start"] < self.playhead_sec - 0.1:
                target = seg["start"]
                break

        self.scrub_sec.emit(target if target is not None else 0.0)

    def _jump_to_next_segment(self):
        if not self.segments:
            return

        target = None
        for seg in self._editable_segments_sorted() if hasattr(self, "_editable_segments_sorted") else self.segments:
            if self._is_stt_preview_segment(seg):
                continue
            if seg["start"] > self.playhead_sec + 0.1:
                target = seg["start"]
                break

        self.scrub_sec.emit(target if target is not None else self.total_duration)

    def _emit_smart_split_at_playhead(self):
        sec = self._snap_to_frame(self.playhead_sec)
        candidates = self._visible_items_for_paint(self.segments, "segments", sec, sec, pad_sec=0.02) if hasattr(self, "_visible_items_for_paint") else self.segments
        seg = find_segment_at([s for s in candidates if not self._is_stt_preview_segment(s)], sec, skip_gap=True)
        if not seg: return
        if sec <= seg["start"] + 0.05 or sec >= seg["end"] - 0.05: return
        mid = (seg["start"] + seg["end"]) / 2.0
        self.sig_smart_split.emit(seg.get("line", 0), float(sec), sec < mid)

    def wheelEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            event.ignore()
            return

        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        delta = -(dy if dy != 0 else dx)

        widget = self.parent()
        while widget:
            if hasattr(widget, "apply_manual_horizontal_scroll_delta"):
                widget.apply_manual_horizontal_scroll_delta(delta // 2)
                event.accept()
                return
            widget = widget.parent()

        widget = self.parent()
        from PyQt6.QtWidgets import QScrollArea as _ScrollArea

        while widget and not isinstance(widget, _ScrollArea):
            widget = widget.parent()

        if widget:
            scrollbar = widget.horizontalScrollBar()
            scrollbar.setValue(scrollbar.value() + delta // 2)

        event.accept()

    def _hit_multiclip_box(self, x: int):
        if not self._multiclip_boxes:
            return None
        boxes = self._multiclip_boxes_near_x_for_hit(x, pad_px=12) if hasattr(self, "_multiclip_boxes_near_x_for_hit") else self._multiclip_boxes
        for box in boxes:
            bx1, bx2 = self._x(box["start"]), self._x(box["end"])
            if bx1 <= x <= bx2:
                return box
        return None

    def _speaker_lane_rect_for_seg(self, seg):
        return QRect(
            self._x(seg["start"]),
            SPEAKER_TOP,
            max(1, self._x(seg["end"]) - self._x(seg["start"])),
            SPEAKER_BOT - SPEAKER_TOP,
        )

    def _speaker_lane_hit_rect_for_seg(self, seg):
        rect = self._speaker_lane_rect_for_seg(seg)
        owner = self._find_owner_with_settings()
        settings = current_speaker_settings(getattr(owner, "settings", {}) if owner is not None else {})
        names = [str(name).strip() for name in speaker_labels_for_segment(settings, seg) if str(name).strip()]
        if not names:
            target_w = min(rect.width(), 42)
            return QRect(rect.center().x() - target_w // 2, rect.y(), max(1, target_w), rect.height())

        visible_names = names[:2]
        multi_line = len(visible_names) > 1
        font_size = 7 if multi_line else 8
        fm = QFontMetrics(QFont(config.FONT, font_size, QFont.Weight.Bold))
        line_h = fm.height()
        gap = 0 if multi_line else 1
        dot = 6 if multi_line else 8
        text_gap = 5 if multi_line else 6
        row_h = max(dot, line_h)
        total_h = len(visible_names) * row_h + max(0, len(visible_names) - 1) * gap
        max_row_w = max(dot + text_gap + fm.horizontalAdvance(name) for name in visible_names)

        draw_y = rect.y() + max(0, (rect.height() - total_h) // 2)
        pad_y = 5
        ideal_w = max_row_w + 12
        max_center_w = max(36, min(96, int(rect.width() * 0.64)))
        target_w = max(1, min(rect.width(), ideal_w, max_center_w))
        left = max(rect.left(), rect.center().x() - target_w // 2)
        right = min(rect.right() + 1, left + target_w)
        left = max(rect.left(), right - target_w)
        top = max(rect.top(), draw_y - pad_y)
        bottom = min(rect.bottom() + 1, draw_y + total_h + pad_y)
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def _speaker_lane_seg_at(self, x: int, y: int):
        candidates = self._segments_near_x_for_hit(x, pad_px=14) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if self._is_stt_preview_segment(seg):
                continue
            if self._speaker_lane_hit_rect_for_seg(seg).contains(x, y):
                return seg
        return None

    def _stt_candidate_at(self, x: int, y: int):
        if STT1_TOP <= y <= STT1_BOT:
            lane_source = "STT1"
        elif STT2_TOP <= y <= STT2_BOT:
            lane_source = "STT2"
        else:
            return None
        candidates = self._segments_near_x_for_hit(x, pad_px=12) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if not self._is_stt_preview_segment(seg):
                continue
            source = self._stt_preview_source(seg)
            if lane_source == "STT1" and source == "STT2":
                continue
            if lane_source == "STT2" and source != "STT2":
                continue
            try:
                x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                x2 = self._x(float(seg.get("end", 0.0) or 0.0))
            except Exception:
                continue
            if x1 <= x <= x2:
                return seg
        return None

    def _gap_at(self, x: int, y: int):
        if not (SEG_TOP <= y <= SEG_BOT):
            return None
        candidates = self._gaps_near_x_for_hit(x, pad_px=12) if hasattr(self, "_gaps_near_x_for_hit") else getattr(self, "gap_segments", []) or []
        for gap in candidates:
            try:
                gx1 = self._x(float(gap.get("start", 0.0) or 0.0))
                gx2 = self._x(float(gap.get("end", 0.0) or 0.0))
            except Exception:
                continue
            if gx1 <= x <= gx2:
                return gap
        return None

    def _roughcut_major_lane_contains(self, x: int, y: int) -> bool:
        lane_top = RULER_H + WAVE_H + 5
        lane_h = max(18, SEG_TOP - lane_top - 7)
        if not (lane_top <= int(y) <= lane_top + lane_h):
            return False
        try:
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []
        except Exception:
            markers = []
        for marker in list(markers or []):
            try:
                x1 = self._x(float(marker.get("start", 0.0) or 0.0))
                x2 = self._x(float(marker.get("end", marker.get("start", 0.0)) or 0.0))
            except Exception:
                continue
            if x1 <= int(x) <= x2:
                return True
        return False

    def _scan_boundary_sec(self, item) -> float | None:
        try:
            if isinstance(item, dict):
                return float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
            return float(item or 0.0)
        except Exception:
            return None

    def _scan_boundary_hit_at(self, x: int, y: int, *, margin: int = 5):
        lane_top = RULER_H + WAVE_H + 5
        lane_h = max(18, SEG_TOP - lane_top - 7)
        if not (lane_top <= int(y) <= lane_top + lane_h):
            return None
        best = None
        best_dist = max(1, int(margin)) + 1
        items = list(getattr(self, "scan_boundary_times", []) or [])
        if len(items) >= 64:
            key = (id(getattr(self, "scan_boundary_times", None)), len(items), int(getattr(self, "_render_epoch", 0) or 0))
            cache = getattr(self, "_scan_boundary_hit_cache", None)
            if not cache or cache.get("key") != key:
                rows = []
                for idx, item in enumerate(items):
                    sec = self._scan_boundary_sec(item)
                    if sec is None or sec <= 0.0:
                        continue
                    rows.append((float(sec), int(idx), item))
                rows.sort(key=lambda row: (row[0], row[1]))
                cache = {"key": key, "rows": rows, "secs": [row[0] for row in rows]}
                self._scan_boundary_hit_cache = cache
            rows = list(cache.get("rows") or [])
            secs = list(cache.get("secs") or [])
            pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
            center = float(x or 0.0) / pps
            pad = max(0.02, (int(margin) + 8) / pps)
            start_idx = bisect_left(secs, center - pad)
            end_idx = bisect_right(secs, center + pad)
            candidates = ((idx, item, sec) for sec, idx, item in rows[start_idx:end_idx])
        else:
            candidates = ((idx, item, self._scan_boundary_sec(item)) for idx, item in enumerate(items))

        for idx, item, sec in candidates:
            if sec is None or sec <= 0.0:
                continue
            bx = self._x(sec)
            dist = abs(int(x) - int(bx))
            if dist <= margin and dist < best_dist:
                best = {"index": int(idx), "sec": float(sec), "item": item}
                best_dist = dist
        return best

    def _set_hover_scan_boundary(self, hit) -> bool:
        idx = int(hit["index"]) if hit is not None else None
        if getattr(self, "_hover_scan_boundary_idx", None) == idx:
            return False
        self._hover_scan_boundary_idx = idx
        return True

    def _show_scan_boundary_menu(self, hit, gpos):
        from PyQt6.QtWidgets import QMenu

        if not hit:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #151C20; color: #F5F7FA; border: 1px solid #2D3942; "
            "font-size: 13px; padding: 4px; } "
            "QMenu::item { padding: 7px 22px 7px 10px; border-radius: 4px; } "
            "QMenu::item:selected { background-color: #1F3A56; }"
        )
        act_delete = menu.addAction("삭제")
        if menu.exec(gpos) is act_delete:
            self.provisional_cut_boundary_delete_requested.emit(int(hit["index"]), float(hit["sec"]))

    def _handle_polygon(self, bx: int, is_left: bool) -> QPolygon:
        cy = SEG_TOP + 32
        w = HANDLE_R
        hw = HANDLE_R // 2
        hh = 12
        th = 4
        if is_left:
            bx += 2
            return QPolygon([
                QPoint(bx, cy),
                QPoint(bx + hw, cy - hh),
                QPoint(bx + hw, cy - th),
                QPoint(bx + w, cy - th),
                QPoint(bx + w, cy + th),
                QPoint(bx + hw, cy + th),
                QPoint(bx + hw, cy + hh),
            ])
        bx -= 2
        return QPolygon([
            QPoint(bx, cy),
            QPoint(bx - hw, cy - hh),
            QPoint(bx - hw, cy - th),
            QPoint(bx - w, cy - th),
            QPoint(bx - w, cy + th),
            QPoint(bx - hw, cy + th),
            QPoint(bx - hw, cy + hh),
        ])

    def _handle_drag_at(self, x: int, y: int):
        point = QPoint(x, y)
        candidates = self._segments_near_x_for_hit(x, pad_px=HANDLE_R + 8) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if self._is_stt_preview_segment(seg):
                continue
            x1, x2 = self._x(seg["start"]), self._x(seg["end"])
            if x2 - x1 < SEGMENT_HANDLE_MIN_WIDTH:
                continue
            if self._handle_polygon(x1, True).containsPoint(point, Qt.FillRule.OddEvenFill):
                return seg, "square_left"
            if self._handle_polygon(x2, False).containsPoint(point, Qt.FillRule.OddEvenFill):
                return seg, "square_right"
        return None

    def _handle_hover_at(self, x: int, y: int):
        hit = self._handle_drag_at(x, y)
        if not hit:
            return None
        seg, edge = hit
        return seg, "left" if edge == "square_left" else "right"

    def _diamond_hit_rect(self, bx: int, *, margin: int = 5) -> QRect:
        r = 5 + max(0, int(margin))
        return QRect(int(bx - r), int(DIAMOND_Y - r), r * 2, r * 2)

    def _diamond_pairs(self):
        key = self._segment_index_cache_key() if hasattr(self, "_segment_index_cache_key") else (
            id(getattr(self, "segments", None)),
            len(getattr(self, "segments", []) or []),
        )
        if getattr(self, "_diamond_pairs_cache_key", None) == key:
            return list((getattr(self, "_diamond_pairs_cache", {}) or {}).get("pairs") or [])

        if hasattr(self, "_editable_segments_with_indices_sorted"):
            editable = self._editable_segments_with_indices_sorted()
        else:
            editable = []
            for raw_idx, seg in enumerate(self.segments):
                if self._is_stt_preview_segment(seg) or bool(seg.get("is_gap")):
                    continue
                if "start" not in seg or "end" not in seg:
                    continue
                editable.append((raw_idx, seg))
            editable.sort(key=lambda item: (float(item[1].get("start", 0.0) or 0.0), int(item[0])))

        pairs = []
        ends = []
        for left, right in zip(editable, editable[1:]):
            left_idx, s1 = left
            right_idx, s2 = right
            if abs(float(s1.get("end", 0.0) or 0.0) - float(s2.get("start", 0.0) or 0.0)) < 0.05:
                pairs.append((left_idx, right_idx, s1, s2))
                ends.append(float(s1.get("end", 0.0) or 0.0))
        self._diamond_pairs_cache_key = key
        self._diamond_pairs_cache = {"pairs": pairs, "ends": ends}
        return pairs

    def _diamond_pair_for_index(self, pair_idx):
        if pair_idx is None:
            return None
        pairs = self._diamond_pairs()
        if 0 <= int(pair_idx) < len(pairs):
            return pairs[int(pair_idx)]
        return None

    def _diamond_index_at(self, x: int, y: int, *, margin: int = 5):
        pairs = self._diamond_pairs()
        if len(pairs) >= 64:
            cache = getattr(self, "_diamond_pairs_cache", {}) or {}
            ends = list(cache.get("ends") or [])
            pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
            center = float(x or 0.0) / pps
            pad = max(0.02, (int(margin) + 8) / pps)
            start_idx = bisect_left(ends, center - pad)
            end_idx = bisect_right(ends, center + pad)
            candidates = ((idx, pairs[idx]) for idx in range(start_idx, min(end_idx, len(pairs))))
        else:
            candidates = enumerate(pairs)
        for pair_idx, (_, _, s1, _) in candidates:
            if self._diamond_hit_rect(self._x(s1["end"]), margin=margin).contains(x, y):
                return pair_idx
        return None

    def _find_owner_with_settings(self):
        owner = self.parent()
        while owner and not hasattr(owner, "settings"):
            owner = owner.parent()
        return owner

    def _speaker_options(self):
        owner = self._find_owner_with_settings()
        settings = getattr(owner, "settings", {}) if owner is not None else {}
        max_spk = max(1, min(3, int(settings.get("max_speakers", 1) or 1)))
        options = []
        for idx in range(1, max_spk + 1):
            if idx > 1 and not bool(settings.get(f"spk{idx}_enabled", False)):
                continue
            spk_id = str(settings.get(f"spk{idx}_id", f"{idx - 1:02d}") or f"{idx - 1:02d}")
            color = str(settings.get(f"spk{idx}_color", "#FFFFFF") or "#FFFFFF")
            name = str(settings.get(f"spk{idx}_name", "") or f"화자{idx}")
            options.append((spk_id, name, color))
        return options

    def _speaker_icon(self, color_hex):
        pix = QPixmap(20, 20)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 12, 12)
        painter.end()
        return QIcon(pix)

    def _show_speaker_select_menu(self, seg, gpos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #151C20; color: #F5F7FA; border: 1px solid #2D3942; "
            "font-size: 13px; padding: 4px; } "
            "QMenu::item { padding: 7px 22px 7px 10px; border-radius: 4px; } "
            "QMenu::item:selected { background-color: #1F3A56; }"
        )
        line = int(seg.get("line", 0))
        current = str(seg.get("speaker", seg.get("spk_id", "")) or "")
        if current.startswith("SPEAKER_"):
            current = current.replace("SPEAKER_", "")
        for spk_id, name, color in self._speaker_options():
            action = menu.addAction(self._speaker_icon(color), name)
            action.setCheckable(True)
            action.setChecked(spk_id == current)
            action.triggered.connect(lambda checked=False, s=spk_id, ln=line: self.speaker_changed.emit(ln, s))
        if not menu.isEmpty():
            menu.exec(gpos)

    def _gap_menu_pivot_sec(self, gap, click_x: int) -> float:
        start = float(gap.get("start", 0.0) or 0.0)
        end = float(gap.get("end", start) or start)
        playhead = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        if start < playhead < end:
            return playhead
        clicked = self._snap_to_frame(max(start, min(end, float(click_x) / max(0.001, float(self.pps)))))
        return clicked

    def _gap_generation_scope_for_pivot(self, gap, pivot_sec: float) -> tuple[float, float] | None:
        gap_start = self._snap_to_frame(float(gap.get("start", 0.0) or 0.0))
        gap_end = self._snap_to_frame(float(gap.get("end", gap_start) or gap_start))
        if gap_end <= gap_start:
            return None

        try:
            if hasattr(self, "generation_silence_markers_cached"):
                markers = self.generation_silence_markers_cached()
            else:
                markers = []
        except Exception:
            markers = []
        silence_ranges: list[tuple[float, float]] = []
        for marker in list(markers or []):
            kind = str(marker.get("kind", "") or "").strip().lower()
            label = str(marker.get("label", "") or "").strip()
            if kind not in {"generation_silence", "linked_silence"} and label not in {"무음구간", "무음"}:
                continue
            start = self._snap_to_frame(float(marker.get("start", 0.0) or 0.0))
            end = self._snap_to_frame(float(marker.get("end", start) or start))
            start = max(gap_start, start)
            end = min(gap_end, end)
            if end > start:
                silence_ranges.append((start, end))

        if not silence_ranges:
            return gap_start, gap_end

        pivot = self._snap_to_frame(float(pivot_sec))
        containing = [item for item in silence_ranges if item[0] - 0.001 <= pivot <= item[1] + 0.001]
        if containing:
            return min(containing, key=lambda item: item[1] - item[0])
        return min(silence_ranges, key=lambda item: min(abs(pivot - item[0]), abs(pivot - item[1])))

    def _show_gap_generate_menu(self, gap, gpos, click_x: int):
        from PyQt6.QtWidgets import QMenu

        start = self._snap_to_frame(float(gap.get("start", 0.0) or 0.0))
        end = self._snap_to_frame(float(gap.get("end", start) or start))
        if end <= start:
            return

        pivot = self._gap_menu_pivot_sec(gap, click_x)
        scope = self._gap_generation_scope_for_pivot(gap, pivot)
        if scope is None:
            return
        scope_start, scope_end = scope
        pivot = self._snap_to_frame(max(scope_start, min(scope_end, pivot)))
        min_span = max(0.02, min(0.1, 1.0 / max(1.0, float(self._get_fps()))))

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #151C20; color: #F5F7FA; border: 1px solid #2D3942; "
            "font-size: 13px; padding: 4px; } "
            "QMenu::item { padding: 7px 22px 7px 10px; border-radius: 4px; } "
            "QMenu::item:selected { background-color: #1F3A56; }"
            "QMenu::item:disabled { color: #65717A; }"
        )
        act_to = menu.addAction("여기까지 생성")
        act_from = menu.addAction("여기부터 생성")
        # 무음 구간 내부에서는 어디를 눌러도 두 동작을 모두 사용할 수 있어야 합니다.
        # 실제 생성 길이는 에디터 쪽에서 최소 1프레임 이상 되도록 보정합니다.
        act_to.setEnabled(scope_end > scope_start + min_span)
        act_from.setEnabled(scope_end > scope_start + min_span)

        chosen = menu.exec(gpos)
        if chosen is act_to:
            self.gap_generate_requested.emit(start, end, pivot, "to")
        elif chosen is act_from:
            self.gap_generate_requested.emit(start, end, pivot, "from")

    def _playhead_handle_hit_rect(self) -> QRect:
        handle_r = 7
        px = self._x(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        return QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)

    def mousePressEvent(self, ev):
        if bool(getattr(self, "_scan_cut_input_locked", False)):
            ev.accept()
            return
        if ev.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            if self._playhead_handle_hit_rect().contains(ev.pos()):
                self.playhead_menu_requested.emit(ev.globalPosition().toPoint(), self.playhead_sec); return

        x, y = ev.pos().x(), ev.pos().y()
        self._last_click_x = x; self._last_click_y = y

        if ev.button() == Qt.MouseButton.LeftButton:
            for clip_idx, rect in getattr(self, '_clip_delete_rects', []) or []:
                if rect.contains(x, y):
                    self.sig_clip_delete_requested.emit(int(clip_idx))
                    ev.accept()
                    return
            if hasattr(self, '_clip_add_rect') and getattr(self, '_clip_add_rect', QRect()).contains(x, y):
                self.sig_clip_add_requested.emit()
                ev.accept()
                return

        # 멀티클립 박스 클릭 감지 (단일 경로)
        hit_box = self._hit_multiclip_box(x) if ev.button() == Qt.MouseButton.LeftButton else None
        if hit_box is not None:
            new_idx = hit_box.get("index", 1) - 1
            if new_idx != self._active_clip_idx:
                self._active_clip_idx = new_idx
                self.sig_clip_selected.emit(new_idx)
                self.update()

        if self._edit_active:
            if self._is_readonly_analysis_lane_y(y):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self._commit_inline_edit()
                ev.accept()
                return
            if ev.button() == Qt.MouseButton.RightButton:
                self._show_mic_menu(ev.globalPosition().toPoint()); return
            if ev.button() == Qt.MouseButton.LeftButton:
                seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else next((s for s in self.segments if s.get("line") == self._edit_line), None)
                is_inside = False
                if seg and SEG_TOP <= y <= SEG_BOT:
                    x1, x2 = self._x(seg["start"]), self._x(seg["end"])
                    if x1 + HANDLE_R < x < x2 - HANDLE_R:
                        is_inside = True
                        fm = QFontMetrics(QFont(config.FONT, 14))
                        lh = fm.height() + 4; tx0 = x1 + HANDLE_R + 6
                        rel_x = x - tx0; rel_y = y - (SEG_TOP + 5)
                        lines = self._edit_text.split('\n')
                        cl = max(0, min(int(rel_y / lh), len(lines) - 1))
                        ln_txt = lines[cl]
                        if rel_x <= 0: col = 0
                        else:
                            col = len(ln_txt)
                            for i in range(1, len(ln_txt) + 1):
                                if fm.horizontalAdvance(ln_txt[:i]) > rel_x:
                                    wp = fm.horizontalAdvance(ln_txt[:i - 1])
                                    wc = fm.horizontalAdvance(ln_txt[:i])
                                    col = i - 1 if (rel_x - wp) < (wc - rel_x) else i; break
                        self._edit_cursor = sum(len(l) + 1 for l in lines[:cl]) + col
                        self._cursor_vis = True; self.update()
                if is_inside:
                    return
                # 바깥 클릭 → 커밋 후 정상 클릭 동작으로 fall-through
                self._commit_inline_edit()
            else:
                return

        self._just_committed = False; self.setFocus()

        if self._is_readonly_analysis_lane_y(y):
            self._clear_active_gaps_for_segment_drag()
            ev.accept()
            return

        # 멀티클립 박스 클릭은 상단 단일 경로에서만 처리

        if ev.button() == Qt.MouseButton.RightButton:
            scan_boundary_hit = self._scan_boundary_hit_at(x, y, margin=7)
            if scan_boundary_hit:
                self._set_hover_scan_boundary(scan_boundary_hit)
                self.update()
                self._show_scan_boundary_menu(scan_boundary_hit, ev.globalPosition().toPoint())
                return
            if self._roughcut_major_lane_contains(x, y):
                self.provisional_cut_boundary_requested.emit(self._snap_to_frame(max(0.0, x / max(0.001, self.pps))))
                return
            candidate = self._stt_candidate_at(x, y)
            if candidate:
                self.stt_candidate_selected.emit(dict(candidate))
                return
            speaker_seg = self._speaker_lane_seg_at(x, y)
            if speaker_seg:
                self._show_speaker_learn_menu(int(speaker_seg.get("line", 0)), ev.globalPosition().toPoint())
                return
            gap = self._gap_at(x, y)
            if gap:
                self._show_gap_generate_menu(gap, ev.globalPosition().toPoint(), x)
                return
            if y < SEG_TOP: self._emit_smart_split_at_playhead(); return
            if SEG_TOP <= y <= SEG_BOT:
                seg = self._seg_at(x)
                if seg:
                    self._last_click_x = x; self._last_click_y = y
                    if self._segment_needs_manual_review(seg):
                        self.seg_right_clicked.emit(float(seg.get("start", 0.0) or 0.0), ev.globalPosition().toPoint())
                    else:
                        self._pending_split_sec = float(self.playhead_sec)
                        self.start_inline_edit(seg.get("line", 0), seg["start"])
            return

        if ev.button() != Qt.MouseButton.LeftButton: return

        self.focus_mode = "waveform" if y <= SEG_TOP else "segment"; self.update()

        candidate = self._stt_candidate_at(x, y)
        if candidate:
            self.stt_candidate_selected.emit(dict(candidate))
            return

        speaker_seg = self._speaker_lane_seg_at(x, y)
        if speaker_seg:
            self._show_speaker_select_menu(speaker_seg, ev.globalPosition().toPoint())
            return

        if y < SEG_TOP:
            self._is_panning = True; self._pan_last_x = ev.globalPosition().x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor); self.scrub_sec.emit(self._snap_to_frame(max(0.0, x / self.pps))); return

        handle_hit = self._handle_drag_at(x, y)
        if handle_hit:
            self._setup_drag(handle_hit[0], handle_hit[1], x)
            return

        diamond_idx = self._diamond_index_at(x, y, margin=5)
        if diamond_idx is not None:
            pair = self._diamond_pair_for_index(diamond_idx)
            if pair is None:
                return
            left_idx, right_idx, s1, _ = pair
            self.drag_started.emit(); self._drag_edge = "diamond"; self._drag_diamond_idx = diamond_idx
            self._drag_diamond_pair = (left_idx, right_idx)
            self._drag_diamond_orig = s1["end"]; self._drag_x0 = x
            self._clear_active_gaps_for_segment_drag()
            self._drag_snap_candidates_cache = self._drag_snap_candidates()
            self._drag_last_paint_rect = self._drag_visual_rect()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return

        gap_candidates = self._gaps_near_x_for_hit(x, pad_px=ICON_SZ + 10) if hasattr(self, "_gaps_near_x_for_hit") else self.gap_segments
        for g in gap_candidates:
            gx1, gx2 = self._x(g["start"]), self._x(g["end"])
            if self._plus_rect(gx1, gx2).adjusted(-5, -5, 5, 5).contains(x, y):
                if g.get("active"): self.gap_to_segs.emit(g["start"], g["end"])
                else: g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"])
                return

        if SEG_TOP <= y <= SEG_BOT:
            for g in gap_candidates:
                if g.get("active"): continue
                gx1, gx2 = self._x(g["start"]), self._x(g["end"])
                if gx2 - gx1 >= ICON_SZ + 8 and self._plus_rect(gx1, gx2).contains(x, y):
                    g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"]); return

        active_candidates = self._active_segment_candidates() if hasattr(self, "_active_segment_candidates") else self.segments
        for s in active_candidates:
            if self._is_stt_preview_segment(s):
                continue
            x1, x2 = self._x(s["start"]), self._x(s["end"])
            if self.active_seg_start is not None and abs(s["start"] - self.active_seg_start) < 0.5:
                if x1 + 25 < x < x2 - 25 and SEG_TOP <= y <= SEG_BOT:
                    self._setup_drag(s, "center", x); self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor)); return

        seg = self._seg_at(x)
        if seg: self.seg_clicked.emit(seg.get("line", 0), seg["start"]); return
        self._is_scrubbing = True; self.scrub_sec.emit(self._snap_to_frame(max(0.0, x / self.pps)))

    def _clear_active_gaps_for_segment_drag(self):
        changed = False
        for gap in getattr(self, "gap_segments", []) or []:
            if gap.get("active"):
                gap["active"] = False
                changed = True
        if changed:
            self.update()

    def _setup_drag(self, s, edge, x):
        if getattr(self, "_edit_active", False):
            self._commit_inline_edit()
        self._ime_preedit = ""
        self._cursor_vis = False
        if hasattr(self, "_cursor_timer"):
            self._cursor_timer.stop()
        self.drag_started.emit(); self._drag_seg, self._drag_edge = s, edge; self._drag_x0 = x
        self.active_seg_start = float(s.get("start", 0.0) or 0.0)
        if hasattr(self, "_sync_active_segment_key"):
            self._sync_active_segment_key(seg=s)
        self._drag_s0_start, self._drag_s0_end = s["start"], s["end"]
        self._drag_adj_l = self._get_prev_seg(s); self._drag_adj_r = self._get_next_seg(s)
        self._drag_adj_orig_start_l = self._drag_adj_l["start"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_end_l = self._drag_adj_l["end"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_start_r = self._drag_adj_r["start"] if self._drag_adj_r else 0.0
        self._drag_adj_orig_end_r = self._drag_adj_r["end"] if self._drag_adj_r else 0.0
        self._clear_active_gaps_for_segment_drag()
        self._drag_snap_candidates_cache = self._drag_snap_candidates()
        self._drag_last_paint_rect = self._drag_visual_rect()
        if edge != "center": self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _drag_visual_rect(self) -> QRect:
        edge = getattr(self, "_drag_edge", None)
        margin = 80
        top = max(0, SEG_TOP - 12)
        height = max(1, SEG_BOT - top + 12)

        if edge == "diamond":
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None and pair[0] < len(self.segments):
                x = self._x(self.segments[pair[0]]["end"])
                rect = QRect(x - margin, top, margin * 2, height)
            else:
                rect = QRect(0, top, 1, height)
        else:
            seg = getattr(self, "_drag_seg", None)
            if not seg:
                rect = QRect(0, top, 1, height)
            elif edge == "square_left":
                x = self._x(seg["start"])
                ox = self._x(getattr(self, "_drag_s0_start", seg["start"]))
                left = min(x, ox) - margin
                right = max(x, ox) + margin
                rect = QRect(left, top, max(1, right - left), height)
            elif edge == "square_right":
                x = self._x(seg["end"])
                ox = self._x(getattr(self, "_drag_s0_end", seg["end"]))
                left = min(x, ox) - margin
                right = max(x, ox) + margin
                rect = QRect(left, top, max(1, right - left), height)
            else:
                x1 = self._x(seg["start"])
                x2 = self._x(seg["end"])
                rect = QRect(min(x1, x2) - 16, top, abs(x2 - x1) + 32, height)

        for sx in getattr(self, "_snap_lines", []) or []:
            rect = rect.united(QRect(int(sx) - 4, top, 8, height))
        guide_x = getattr(self, "_drag_guide_x", None)
        if guide_x is not None:
            rect = rect.united(QRect(int(guide_x) - 4, 0, 8, self.height()))
        if hasattr(self, "_segment_repaint_rect"):
            related = [
                getattr(self, "_drag_seg", None),
                getattr(self, "_drag_adj_l", None),
                getattr(self, "_drag_adj_r", None),
            ]
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None:
                for idx in pair:
                    try:
                        related.append(self.segments[int(idx)])
                    except Exception:
                        pass
            for seg in related:
                if isinstance(seg, dict):
                    rect = rect.united(self._segment_repaint_rect(seg, margin=64, full_height=False))
        return rect.adjusted(-4, -4, 4, 4).intersected(QRect(0, 0, self.width(), self.height()))

    def _update_drag_visual_rect(self, before: QRect):
        after = self._drag_visual_rect()
        dirty = before.united(after).intersected(QRect(0, 0, self.width(), self.height()))
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()
        if hasattr(self, "_notify_scenegraph_layer"):
            self._notify_scenegraph_layer()
        self._drag_last_paint_rect = after

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton: return
        if self._edit_active: self._commit_inline_edit(); return
        x, y = ev.pos().x(), ev.pos().y()

        if self._is_readonly_analysis_lane_y(y):
            ev.accept()
            return

        diamond_idx = self._diamond_index_at(x, y, margin=5)
        if diamond_idx is not None:
            pair = self._diamond_pair_for_index(diamond_idx)
            if pair is None:
                return
            _, _, s1, s2 = pair
            self._drag_seg = None; self._drag_edge = None; self._drag_diamond_idx = None
            self._drag_diamond_pair = None
            self._clear_drag_guides(); self.unsetCursor()
            self.drag_finished.emit()
            self.diamond_merge.emit(s1.get("line", 0), s2.get("line", 0)); return

        if SEG_TOP <= y <= SEG_BOT:
            seg = self._seg_at(x)
            if seg: self.seg_double_clicked.emit(seg.get("line", 0), seg["start"])

    def mouseMoveEvent(self, ev):
        x, y = ev.pos().x(), ev.pos().y()

        if self._edit_active:
            seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else: self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._is_readonly_analysis_lane_y(y):
            if (
                self._hover_handle is not None
                or getattr(self, "_hover_diamond", None) is not None
                or self._hover_line is not None
                or getattr(self, "_hover_scan_boundary_idx", None) is not None
            ):
                self._hover_handle = None
                self._hover_diamond = None
                self._hover_line = None
                self._hover_scan_boundary_idx = None
                self.update()
            self.unsetCursor()
            return

        if getattr(self, '_is_panning', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            current_x = ev.globalPosition().x(); delta_x = self._pan_last_x - current_x
            w = self.parent()
            from PyQt6.QtWidgets import QScrollArea
            while w and not isinstance(w, QScrollArea): w = w.parent()
            if w: w.horizontalScrollBar().setValue(int(w.horizontalScrollBar().value() + delta_x))
            self._pan_last_x = current_x; return

        if getattr(self, '_is_scrubbing', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            self.scrub_sec.emit(self._snap_to_frame(max(0.0, x / self.pps))); return

        if self._drag_seg or getattr(self, '_drag_edge', None) == "diamond":
            if ev.buttons() & Qt.MouseButton.LeftButton: self._apply_drag((x - self._drag_x0) / self.pps)
            return

        scan_boundary_hit = self._scan_boundary_hit_at(x, y, margin=7)
        if scan_boundary_hit is not None:
            changed = self._set_hover_scan_boundary(scan_boundary_hit)
            if self._hover_handle is not None:
                self._hover_handle = None
                changed = True
            if getattr(self, '_hover_diamond', None) is not None:
                self._hover_diamond = None
                changed = True
            if self._hover_line is not None:
                self._hover_line = None
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            return
        if self._set_hover_scan_boundary(None):
            self.update()

        new_hh = self._handle_hover_at(x, y)
        if new_hh is not None:
            changed = False
            if getattr(self, '_hover_diamond', None) is not None:
                self._hover_diamond = None
                changed = True
            if self._hover_handle != new_hh:
                self._hover_handle = new_hh
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return

        hover_dia = self._diamond_index_at(x, y, margin=5)
        if hover_dia is not None:
            changed = False
            if self._hover_handle is not None:
                self._hover_handle = None
                changed = True
            if getattr(self, '_hover_diamond', None) != hover_dia:
                self._hover_diamond = hover_dia
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return
        if getattr(self, '_hover_diamond', None) != hover_dia: self._hover_diamond = hover_dia; self.update()

        hover_handle = bool(new_hh); hover_center = False
        if not hover_handle:
            active_candidates = self._active_segment_candidates() if hasattr(self, "_active_segment_candidates") else self.segments
            for s in active_candidates:
                if self._is_stt_preview_segment(s):
                    continue
                x1, x2 = self._x(s["start"]), self._x(s["end"])
                if self.active_seg_start is not None and abs(s["start"] - self.active_seg_start) < 0.5:
                    if x1 + 25 < x < x2 - 25 and SEG_TOP <= y <= SEG_BOT: hover_center = True; break

        if self._hover_handle != new_hh: self._hover_handle = new_hh; self.update()
        if hover_handle: self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hover_center: self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else: self.unsetCursor()

        seg2 = self._seg_at(x); new_h = seg2.get("line") if seg2 else None
        if new_h != self._hover_line: self._hover_line = new_h; self.update()

    def mouseReleaseEvent(self, ev):
        if getattr(self, '_is_panning', False): self._is_panning = False; self.unsetCursor(); return
        if getattr(self, '_is_scrubbing', False): self._is_scrubbing = False; return

        if getattr(self, '_drag_edge', None) == "diamond":
            dirty = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None and pair[1] < len(self.segments):
                s2 = self.segments[pair[1]]
                self.seg_time_changed.emit(s2.get("line", 0), s2["start"], s2["end"], "diamond")
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._drag_diamond_idx = None; self._drag_diamond_pair = None; self._clear_drag_guides(); self.unsetCursor()
            self._drag_snap_candidates_cache = []
            self.gap_segments = _build_gaps(self.segments, self.total_duration)
            if hasattr(self, "_invalidate_render_cache"):
                self._invalidate_render_cache()
            self._update_dirty_rect(dirty.adjusted(-8, -8, 8, 8))
            return

        if self._drag_seg:
            dirty = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
            edge = str(self._drag_edge) if self._drag_edge else ""
            self.seg_time_changed.emit(self._drag_seg.get("line", 0), self._drag_seg["start"], self._drag_seg["end"], edge)
            if self._drag_adj_l and self._drag_edge == "square_left":
                self.seg_time_changed.emit(self._drag_adj_l.get("line", 0), self._drag_adj_l["start"], self._drag_adj_l["end"], edge)
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._clear_drag_guides(); self.unsetCursor()
            self._drag_snap_candidates_cache = []
            self.gap_segments = _build_gaps(self.segments, self.total_duration)
            if hasattr(self, "_invalidate_render_cache"):
                self._invalidate_render_cache()
            self._update_dirty_rect(dirty.adjusted(-8, -8, 8, 8))

    def _apply_drag(self, delta):
        if delta == 0: return
        before_rect = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
        edge = getattr(self, '_drag_edge', None)
        self._clear_drag_guides(update=False)
        snap_candidates = list(getattr(self, "_drag_snap_candidates_cache", []) or [])
        if not snap_candidates:
            snap_candidates = self._drag_snap_candidates()
            self._drag_snap_candidates_cache = snap_candidates
        snap_threshold = self._drag_snap_threshold_sec()

        if edge == "diamond":
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None and pair[0] < len(self.segments) and pair[1] < len(self.segments):
                s1, s2 = self.segments[pair[0]], self.segments[pair[1]]
                orig = getattr(self, '_drag_diamond_orig', 0.0); nb = self._snap_to_frame(orig + delta)
                nb = max(self._snap_to_frame(s1["start"] + 0.1), min(self._snap_to_frame(s2["end"] - 0.1), nb))
                nb, snapped = self._snap_drag_time(nb, snap_candidates, snap_threshold, s1["start"] + 0.1, s2["end"] - 0.1)
                s1["end"] = s2["start"] = nb
                self._set_drag_guides(nb, snapped)
                self._update_drag_visual_rect(before_rect)
            return

        seg = self._drag_seg; MIN = self._snap_to_frame(0.1)

        if edge == "square_right":
            ne = self._snap_to_frame(self._drag_s0_end + delta)
            limit = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            min_end = self._snap_to_frame(seg["start"] + MIN)
            ne = max(min_end, min(ne, limit))
            seg["end"], snapped = self._snap_drag_time(ne, snap_candidates, snap_threshold, min_end, limit)
            self._set_drag_guides(seg["end"], snapped)

        elif edge == "square_left":
            ns = self._snap_to_frame(self._drag_s0_start + delta)
            limit = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            max_start = self._snap_to_frame(seg["end"] - MIN)
            ns = min(max_start, max(ns, limit))
            seg["start"], snapped = self._snap_drag_time(ns, snap_candidates, snap_threshold, limit, max_start)
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            if hasattr(self, "_sync_active_segment_key"):
                self._sync_active_segment_key(seg=seg)
            self._set_drag_guides(seg["start"], snapped)

        elif edge == "center":
            dur = self._drag_s0_end - self._drag_s0_start; ns = self._snap_to_frame(self._drag_s0_start + delta)
            ll = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            lr = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            ns = max(ll, min(ns, self._snap_to_frame(lr - dur)))
            ns, guide_time, snapped = self._snap_drag_span(ns, dur, snap_candidates, snap_threshold, ll, lr)
            seg["start"] = ns; seg["end"] = self._snap_to_frame(ns + dur)
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            if hasattr(self, "_sync_active_segment_key"):
                self._sync_active_segment_key(seg=seg)
            self._set_drag_guides(guide_time, snapped)

        self._update_drag_visual_rect(before_rect)

    def _clear_drag_guides(self, *, update: bool = False):
        self._snap_lines = []
        self._drag_guide_x = None
        self._drag_snap_candidate = None
        if update:
            self.update()

    def _set_drag_guides(self, guide_sec: float, snapped: dict | None = None):
        guide_sec = self._snap_to_frame(guide_sec)
        self._drag_guide_x = self._x(guide_sec)
        self._drag_snap_candidate = dict(snapped) if snapped else None
        self._snap_lines = [self._x(float(snapped["time"]))] if snapped else []

    def _drag_snap_threshold_sec(self) -> float:
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        frame = 1.0 / fps
        pixel = 8.0 / max(1.0, float(getattr(self, "pps", 1.0) or 1.0))
        return max(frame, pixel)

    def _add_snap_candidate(self, candidates: list[dict], sec, kind: str, source=None):
        raw_value = _as_float(sec, -1.0)
        if raw_value < 0.0:
            return
        value = self._snap_to_frame(raw_value)
        total = max(0.0, _as_float(getattr(self, "total_duration", 0.0), 0.0))
        if value < 0.0 or (total > 0.0 and value > total):
            return
        candidates.append({"time": value, "kind": kind, "source": source})

    def _drag_snap_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        dragged = getattr(self, "_drag_seg", None)
        for seg in list(getattr(self, "segments", []) or []):
            if seg is dragged or not isinstance(seg, dict) or bool(seg.get("is_gap")):
                continue
            kind = self._stt_preview_source(seg).lower() if self._is_stt_preview_segment(seg) else "subtitle"
            self._add_snap_candidate(candidates, seg.get("start"), kind, seg)
            self._add_snap_candidate(candidates, seg.get("end"), kind, seg)

        drag_original_edges = {
            self._snap_to_frame(getattr(self, "_drag_s0_start", -1.0)),
            self._snap_to_frame(getattr(self, "_drag_s0_end", -1.0)),
        }
        for gap in list(getattr(self, "gap_segments", []) or []):
            for edge_time in (gap.get("start"), gap.get("end")):
                snapped_edge = self._snap_to_frame(_as_float(edge_time, -1.0))
                if any(abs(snapped_edge - original) < 0.05 for original in drag_original_edges):
                    continue
                self._add_snap_candidate(candidates, snapped_edge, "gap", gap)
        for vad in list(getattr(self, "vad_segments", []) or []):
            self._add_snap_candidate(candidates, vad.get("start"), "vad", vad)
            self._add_snap_candidate(candidates, vad.get("end"), "vad", vad)
        for va in list(getattr(self, "voice_activity_segments", []) or []):
            self._add_snap_candidate(candidates, va.get("start"), "voice_activity", va)
            self._add_snap_candidate(candidates, va.get("end"), "voice_activity", va)
        for bt in list(getattr(self, "boundary_times", []) or []):
            self._add_snap_candidate(candidates, bt, "cut_official", None)
        for bt in list(getattr(self, "scan_boundary_times", []) or []):
            sec = bt.get("timeline_sec", bt.get("time", bt.get("start", 0.0))) if isinstance(bt, dict) else bt
            self._add_snap_candidate(candidates, sec, "cut_temporary", bt)
        try:
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []
        except Exception:
            markers = []
        for marker in list(markers or []):
            self._add_snap_candidate(candidates, marker.get("start"), "roughcut", marker)
            self._add_snap_candidate(candidates, marker.get("end"), "roughcut", marker)
        self._add_snap_candidate(candidates, 0.0, "timeline", None)
        self._add_snap_candidate(candidates, getattr(self, "total_duration", 0.0), "timeline", None)

        priority = {
            "cut_official": 12,
            "cut_temporary": 11,
            "subtitle": 10,
            "stt1": 9,
            "stt2": 9,
            "voice_activity": 8,
            "gap": 8,
            "vad": 7,
            "roughcut": 6,
            "timeline": 5,
        }
        deduped: dict[float, dict] = {}
        for item in candidates:
            t = float(item.get("time", 0.0) or 0.0)
            prev = deduped.get(t)
            if prev is None or priority.get(str(item.get("kind")), 0) > priority.get(str(prev.get("kind")), 0):
                deduped[t] = item
        return list(deduped.values())

    def _snap_drag_time(self, value: float, candidates: list[dict], threshold: float, min_value: float, max_value: float) -> tuple[float, dict | None]:
        value = self._snap_to_frame(value)
        min_value = self._snap_to_frame(min_value)
        max_value = self._snap_to_frame(max_value)
        best = None
        best_dist = float("inf")
        for candidate in candidates:
            t = self._snap_to_frame(candidate.get("time", 0.0))
            if t < min_value or t > max_value:
                continue
            dist = abs(t - value)
            if dist <= threshold and dist < best_dist:
                best = candidate
                best_dist = dist
        if best:
            return self._snap_to_frame(best["time"]), best
        return max(min_value, min(value, max_value)), None

    def _snap_drag_span(self, start: float, duration: float, candidates: list[dict], threshold: float, min_start: float, max_end: float) -> tuple[float, float, dict | None]:
        start = self._snap_to_frame(start)
        duration = max(0.0, self._snap_to_frame(duration))
        min_start = self._snap_to_frame(min_start)
        max_start = self._snap_to_frame(max_end - duration)
        start = max(min_start, min(start, max_start))
        anchors = (("start", start), ("end", self._snap_to_frame(start + duration)))
        best = None
        best_dist = float("inf")
        best_start = start
        best_guide = start
        for anchor_name, anchor_time in anchors:
            for candidate in candidates:
                t = self._snap_to_frame(candidate.get("time", 0.0))
                next_start = t if anchor_name == "start" else self._snap_to_frame(t - duration)
                if next_start < min_start or next_start > max_start:
                    continue
                dist = abs(t - anchor_time)
                if dist <= threshold and dist < best_dist:
                    best = candidate
                    best_dist = dist
                    best_start = next_start
                    best_guide = t
        if best:
            return self._snap_to_frame(best_start), self._snap_to_frame(best_guide), best
        return start, start, None

    def _snap_closest_diamond(self):
        if self.playhead_sec <= 0: return
        closest_seg_idx = None; closest_edge = None; min_dist = float('inf')
        for i, seg in enumerate(self.segments):
            ds = abs(seg["start"] - self.playhead_sec)
            if ds < min_dist: min_dist = ds; closest_seg_idx = i; closest_edge = "start"
            de = abs(seg["end"] - self.playhead_sec)
            if de < min_dist: min_dist = de; closest_seg_idx = i; closest_edge = "end"

        if closest_seg_idx is not None and min_dist <= 2.0:
            seg = self.segments[closest_seg_idx]
            nb = self._snap_to_frame(self.playhead_sec); ml = self._snap_to_frame(0.1)
            is_joint = False; joint_idx = None

            if closest_edge == "start" and closest_seg_idx > 0:
                ps = self.segments[closest_seg_idx - 1]
                if abs(ps["end"] - seg["start"]) < 0.05: is_joint = True; joint_idx = closest_seg_idx - 1
            elif closest_edge == "end" and closest_seg_idx < len(self.segments) - 1:
                ns = self.segments[closest_seg_idx + 1]
                if abs(seg["end"] - ns["start"]) < 0.05: is_joint = True; joint_idx = closest_seg_idx + 1

            if is_joint:
                if closest_edge == "start": s1, s2 = self.segments[joint_idx], seg
                else: s1, s2 = seg, self.segments[joint_idx]
                nb = max(self._snap_to_frame(s1["start"] + ml), min(self._snap_to_frame(s2["end"] - ml), nb))
                s1["end"] = s2["start"] = nb
                self.seg_time_changed.emit(s2.get("line", 0), s2["start"], s2["end"], "diamond")
            else:
                if closest_edge == "start":
                    ll = self.segments[closest_seg_idx - 1]["end"] if closest_seg_idx > 0 else 0.0
                    nb = max(self._snap_to_frame(ll), min(self._snap_to_frame(seg["end"] - ml), nb))
                    seg["start"] = nb
                    self.seg_time_changed.emit(seg.get("line", 0), seg["start"], seg["end"], "square_left")
                else:
                    lr = self.segments[closest_seg_idx + 1]["start"] if closest_seg_idx < len(self.segments) - 1 else self.total_duration
                    nb = max(self._snap_to_frame(seg["start"] + ml), min(self._snap_to_frame(lr), nb))
                    seg["end"] = nb
                    self.seg_time_changed.emit(seg.get("line", 0), seg["start"], seg["end"], "square_right")
            self.gap_segments = _build_gaps(self.segments, self.total_duration)
            if hasattr(self, "_invalidate_render_cache"):
                self._invalidate_render_cache()
            self.update()
