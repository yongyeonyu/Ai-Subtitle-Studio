# Version: 03.06.17
# Phase: PHASE2
"""
ui/timeline_input.py
Timeline input mixin
"""
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QPolygon

import config
from ui.editor.editor_helpers import find_segment_at

from ui.timeline.speaker_labels import current_speaker_settings, speaker_labels_for_segment
from ui.timeline.timeline_constants import (
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    _build_gaps,
)

class TimelineInputMixin:
    def focusNextPrevChild(self, next):
        self._snap_closest_diamond()
        return False

    def keyPressEvent(self, ev):
        if self._edit_active:
            self._handle_edit_key(ev); ev.accept(); return

        if ev.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.active_seg_start is not None:
            seg = next((s for s in self.segments if abs(s["start"] - self.active_seg_start) < 0.5), None)
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
        for seg in reversed(self.segments):
            if seg["start"] < self.playhead_sec - 0.1:
                target = seg["start"]
                break

        self.scrub_sec.emit(target if target is not None else 0.0)

    def _jump_to_next_segment(self):
        if not self.segments:
            return

        target = None
        for seg in self.segments:
            if seg["start"] > self.playhead_sec + 0.1:
                target = seg["start"]
                break

        self.scrub_sec.emit(target if target is not None else self.total_duration)

    def _emit_smart_split_at_playhead(self):
        sec = self._snap_to_frame(self.playhead_sec)
        seg = find_segment_at(self.segments, sec, skip_gap=True)
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
        for box in self._multiclip_boxes:
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
        for seg in self.segments:
            if self._speaker_lane_hit_rect_for_seg(seg).contains(x, y):
                return seg
        return None

    def _gap_at(self, x: int, y: int):
        if not (SEG_TOP <= y <= SEG_BOT):
            return None
        for gap in getattr(self, "gap_segments", []) or []:
            try:
                gx1 = self._x(float(gap.get("start", 0.0) or 0.0))
                gx2 = self._x(float(gap.get("end", 0.0) or 0.0))
            except Exception:
                continue
            if gx1 <= x <= gx2:
                return gap
        return None

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
        for seg in self.segments:
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

    def _diamond_index_at(self, x: int, y: int, *, margin: int = 5):
        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]
            s2 = self.segments[i + 1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                if self._diamond_hit_rect(self._x(s1["end"]), margin=margin).contains(x, y):
                    return i
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

    def _show_gap_generate_menu(self, gap, gpos, click_x: int):
        from PyQt6.QtWidgets import QMenu

        start = self._snap_to_frame(float(gap.get("start", 0.0) or 0.0))
        end = self._snap_to_frame(float(gap.get("end", start) or start))
        if end <= start:
            return

        pivot = self._gap_menu_pivot_sec(gap, click_x)
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
        act_to.setEnabled(pivot > start + min_span)
        act_from.setEnabled(pivot < end - min_span)

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
            if ev.button() == Qt.MouseButton.RightButton:
                self._show_mic_menu(ev.globalPosition().toPoint()); return
            if ev.button() == Qt.MouseButton.LeftButton:
                seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
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

        # 멀티클립 박스 클릭은 상단 단일 경로에서만 처리

        if ev.button() == Qt.MouseButton.RightButton:
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
                    self._pending_split_sec = float(self.playhead_sec)
                    self.start_inline_edit(seg.get("line", 0), seg["start"])
            return

        if ev.button() != Qt.MouseButton.LeftButton: return

        self.focus_mode = "waveform" if y <= SEG_TOP else "segment"; self.update()

        speaker_seg = self._speaker_lane_seg_at(x, y)
        if speaker_seg:
            self._show_speaker_select_menu(speaker_seg, ev.globalPosition().toPoint())
            return

        for seg in self.segments:
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = x2 - x1
            if sw > 20 and self._icon_rect(x1, x2).adjusted(-5, -5, 5, 5).contains(x, y):
                self.seg_to_gap.emit(seg.get("line", 0)); return

        if y < SEG_TOP:
            self._is_panning = True; self._pan_last_x = ev.globalPosition().x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor); self.scrub_sec.emit(self._snap_to_frame(max(0.0, x / self.pps))); return

        handle_hit = self._handle_drag_at(x, y)
        if handle_hit:
            self._setup_drag(handle_hit[0], handle_hit[1], x)
            return

        diamond_idx = self._diamond_index_at(x, y, margin=5)
        if diamond_idx is not None:
            s1 = self.segments[diamond_idx]
            self.drag_started.emit(); self._drag_edge = "diamond"; self._drag_diamond_idx = diamond_idx
            self._drag_diamond_orig = s1["end"]; self._drag_x0 = x
            self._clear_active_gaps_for_segment_drag()
            self._drag_last_paint_rect = self._drag_visual_rect()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return

        for g in self.gap_segments:
            gx1, gx2 = self._x(g["start"]), self._x(g["end"])
            if self._plus_rect(gx1, gx2).adjusted(-5, -5, 5, 5).contains(x, y):
                if g.get("active"): self.gap_to_segs.emit(g["start"], g["end"])
                else: g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"])
                return

        if SEG_TOP <= y <= SEG_BOT:
            for g in self.gap_segments:
                if g.get("active"): continue
                gx1, gx2 = self._x(g["start"]), self._x(g["end"])
                if gx2 - gx1 >= ICON_SZ + 8 and self._plus_rect(gx1, gx2).contains(x, y):
                    g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"]); return

        for s in self.segments:
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
        self._drag_last_paint_rect = self._drag_visual_rect()
        if edge != "center": self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _drag_visual_rect(self) -> QRect:
        edge = getattr(self, "_drag_edge", None)
        margin = 80
        top = max(0, SEG_TOP - 12)
        height = max(1, SEG_BOT - top + 12)

        if edge == "diamond":
            idx = getattr(self, "_drag_diamond_idx", None)
            if idx is not None and idx + 1 < len(self.segments):
                x = self._x(self.segments[idx]["end"])
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
        return rect.adjusted(-4, -4, 4, 4).intersected(QRect(0, 0, self.width(), self.height()))

    def _update_drag_visual_rect(self, before: QRect):
        after = self._drag_visual_rect()
        dirty = before.united(after).intersected(QRect(0, 0, self.width(), self.height()))
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()
        self._drag_last_paint_rect = after

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton: return
        if self._edit_active: self._commit_inline_edit(); return
        x, y = ev.pos().x(), ev.pos().y()

        diamond_idx = self._diamond_index_at(x, y, margin=5)
        if diamond_idx is not None:
            s1 = self.segments[diamond_idx]
            s2 = self.segments[diamond_idx + 1]
            self._drag_seg = None; self._drag_edge = None; self._drag_diamond_idx = None
            self._snap_lines = []; self.unsetCursor()
            self.drag_finished.emit()
            self.diamond_merge.emit(s1.get("line", 0), s2.get("line", 0)); return

        if SEG_TOP <= y <= SEG_BOT:
            seg = next((s for s in self.segments if self._x(s["start"]) <= x <= self._x(s["end"])), None)
            if seg: self.seg_double_clicked.emit(seg.get("line", 0), seg["start"])

    def mouseMoveEvent(self, ev):
        x, y = ev.pos().x(), ev.pos().y()

        if self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else: self.setCursor(Qt.CursorShape.ArrowCursor)
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
            for s in self.segments:
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
            idx = getattr(self, '_drag_diamond_idx', None)
            if idx is not None and idx + 1 < len(self.segments):
                s2 = self.segments[idx + 1]
                self.seg_time_changed.emit(s2.get("line", 0), s2["start"], s2["end"], "diamond")
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._drag_diamond_idx = None; self._snap_lines = []; self.unsetCursor()
            self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update(); return

        if self._drag_seg:
            edge = str(self._drag_edge) if self._drag_edge else ""
            self.seg_time_changed.emit(self._drag_seg.get("line", 0), self._drag_seg["start"], self._drag_seg["end"], edge)
            if self._drag_adj_l and self._drag_edge == "square_left":
                self.seg_time_changed.emit(self._drag_adj_l.get("line", 0), self._drag_adj_l["start"], self._drag_adj_l["end"], edge)
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._snap_lines = []; self.unsetCursor()
            self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update()

    def _apply_drag(self, delta):
        if delta == 0: return
        before_rect = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
        edge = getattr(self, '_drag_edge', None); self._snap_lines = []; playhead_snap = 2.0 / max(1.0, self.pps)

        if edge == "diamond":
            idx = getattr(self, '_drag_diamond_idx', None)
            if idx is not None and idx + 1 < len(self.segments):
                s1, s2 = self.segments[idx], self.segments[idx + 1]
                orig = getattr(self, '_drag_diamond_orig', 0.0); nb = self._snap_to_frame(orig + delta)
                if self.playhead_sec > 0 and abs(nb - self.playhead_sec) <= playhead_snap:
                    nb = self._snap_to_frame(self.playhead_sec); self._snap_lines.append(self._x(nb))
                nb = max(self._snap_to_frame(s1["start"] + 0.1), min(self._snap_to_frame(s2["end"] - 0.1), nb))
                s1["end"] = s2["start"] = nb
                self._update_drag_visual_rect(before_rect)
            return

        seg = self._drag_seg; MIN = self._snap_to_frame(0.1)

        if edge == "square_right":
            ne = self._snap_to_frame(self._drag_s0_end + delta)
            limit = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            if self.playhead_sec > 0 and abs(ne - self.playhead_sec) <= playhead_snap: ne = self._snap_to_frame(self.playhead_sec)
            seg["end"] = max(self._snap_to_frame(seg["start"] + MIN), min(ne, limit))
            if abs(seg["end"] - limit) < 0.05 or (self.playhead_sec > 0 and abs(seg["end"] - self.playhead_sec) < 0.05): self._snap_lines.append(self._x(seg["end"]))

        elif edge == "square_left":
            ns = self._snap_to_frame(self._drag_s0_start + delta)
            limit = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            if self.playhead_sec > 0 and abs(ns - self.playhead_sec) <= playhead_snap: ns = self._snap_to_frame(self.playhead_sec)
            seg["start"] = min(self._snap_to_frame(seg["end"] - MIN), max(ns, limit))
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            if hasattr(self, "_sync_active_segment_key"):
                self._sync_active_segment_key(seg=seg)
            if abs(seg["start"] - limit) < 0.05 or (self.playhead_sec > 0 and abs(seg["start"] - self.playhead_sec) < 0.05): self._snap_lines.append(self._x(seg["start"]))

        elif edge == "center":
            dur = self._drag_s0_end - self._drag_s0_start; ns = self._snap_to_frame(self._drag_s0_start + delta)
            ll = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            lr = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            snapped = False
            if self.playhead_sec > 0:
                if abs(ns - self.playhead_sec) <= playhead_snap: ns = self._snap_to_frame(self.playhead_sec); snapped = True
                elif abs(ns + dur - self.playhead_sec) <= playhead_snap: ns = self._snap_to_frame(self.playhead_sec - dur); snapped = True
            if not snapped:
                if self._drag_adj_l and abs(ns - ll) <= 0.2: ns = ll
                elif self._drag_adj_r and abs(ns + dur - lr) <= 0.2: ns = self._snap_to_frame(lr - dur)
                elif not self._drag_adj_l and abs(ns) <= 0.2: ns = 0.0
                elif not self._drag_adj_r and abs(ns + dur - self.total_duration) <= 0.2: ns = self._snap_to_frame(self.total_duration - dur)
            ns = max(ll, min(ns, self._snap_to_frame(lr - dur)))
            seg["start"] = ns; seg["end"] = self._snap_to_frame(ns + dur)
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            if hasattr(self, "_sync_active_segment_key"):
                self._sync_active_segment_key(seg=seg)
            if abs(seg["start"] - ll) < 0.05 or (self.playhead_sec > 0 and abs(seg["start"] - self.playhead_sec) < 0.05) or (not self._drag_adj_l and abs(seg["start"]) < 0.05): self._snap_lines.append(self._x(seg["start"]))
            if abs(seg["end"] - lr) < 0.05 or (self.playhead_sec > 0 and abs(seg["end"] - self.playhead_sec) < 0.05) or (not self._drag_adj_r and abs(seg["end"] - self.total_duration) < 0.05): self._snap_lines.append(self._x(seg["end"]))

        self._update_drag_visual_rect(before_rect)

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
            self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update()
