# Version: 01.00.00
"""
ui/timeline_paint.py
TimelineCanvas의 paintEvent / _draw_handle 분리
"""
import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPolygon, QBrush

import config
from ui.timeline_constants import (
    RULER_H, WAVE_H, SEG_TOP, SEG_BOT, CANVAS_H,
    WAVE_MID, WAVE_HALF, ICON_SZ, HANDLE_R
)


class TimelinePaintMixin:

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        total_w = self.total_width()
        total_secs = self.total_duration + 2
        sec_f = 0.0

        def _fmt_ruler(sec):
            s = int(sec)
            h, rem = divmod(s, 3600)
            m, sc = divmod(rem, 60)
            if h > 0: return f"{h}:{m:02d}:{sc:02d}"
            return f"{m:02d}:{sc:02d}"

        ruler_font = QFont(config.FONT, 12)
        ruler_font.setBold(True)
        p.setFont(ruler_font)

        while sec_f <= total_secs:
            tx = self._x(sec_f); sec_i = sec_f
            if abs(sec_i - round(sec_i, 0)) < 0.01:
                sec_i = round(sec_i)
                if sec_i % 5 == 0 and sec_i != 0:
                    p.setPen(QColor("#BBBBBB")); p.drawLine(tx, 0, tx, 15)
                    p.drawText(tx + 5, RULER_H - 5, _fmt_ruler(sec_i))
                elif sec_i % 1 == 0:
                    p.setPen(QColor("#666666")); p.drawLine(tx, 0, tx, 8)
                    if sec_i > 0: p.drawText(tx + 2, RULER_H - 2, _fmt_ruler(sec_i))
            elif abs(sec_i * 2 - round(sec_i * 2)) < 0.01: p.setPen(QColor("#444444")); p.drawLine(tx, 0, tx, 5)
            else: p.setPen(QColor("#333333")); p.drawLine(tx, 0, tx, 3)
            sec_f = round(sec_f + 0.1, 1)

        p.fillRect(QRect(0, RULER_H, total_w, WAVE_H), QColor("#0a0a0a"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            p.setPen(QPen(QColor("#333333"), 1))
            p.drawLine(0, WAVE_MID, total_w, WAVE_MID)

            if self._speech_mask is None or self._speech_mask_wf_len != wf_len:
                mask = np.zeros(wf_len, dtype=bool)
                for vs in self.vad_segments:
                    s_idx = max(0, int(vs["start"] * 100))
                    e_idx = min(wf_len, int(vs["end"] * 100) + 1)
                    mask[s_idx:e_idx] = True
                self._speech_mask = mask
                self._speech_mask_wf_len = wf_len
            speech_mask = self._speech_mask

            clip = event.rect()
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)

            pen_top_norm = QPen(QColor(100, 220, 255), 1)
            pen_bot_norm = QPen(QColor(40, 130, 170), 1)
            pen_top_loud = QPen(QColor(160, 255, 255), 1)
            pen_bot_loud = QPen(QColor(80, 180, 210), 1)
            pen_top_sil = QPen(QColor(75, 75, 75), 1)
            pen_bot_sil = QPen(QColor(45, 45, 45), 1)

            for x in range(x_start, x_end):
                idx = int((x / self.pps) * 100)
                if idx >= wf_len: break
                val = wf[idx]
                if val < 0.008: continue
                h = min(int(val * WAVE_HALF * 2.0), WAVE_HALF - 1)
                in_sp = speech_mask[idx]
                if in_sp:
                    if val > 0.6:
                        p.setPen(pen_top_loud); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                        p.setPen(pen_bot_loud); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                    else:
                        p.setPen(pen_top_norm); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                        p.setPen(pen_bot_norm); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                else:
                    p.setPen(pen_top_sil); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                    p.setPen(pen_bot_sil); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)

        if self.vad_segments:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255, 200, 0, 40))
            for vs in self.vad_segments:
                vx1 = self._x(vs["start"]); vx2 = self._x(vs["end"])
                p.drawRect(QRect(vx1, RULER_H, vx2 - vx1, WAVE_H))

        if self.re_recog_zone:
            rs, re_sec = self.re_recog_zone
            rp = self.re_recog_progress if self.re_recog_progress is not None else rs
            yx1 = self._x(rs); yx2 = self._x(rp)
            if yx2 > yx1:
                p.fillRect(QRect(yx1, RULER_H, yx2 - yx1, WAVE_H), QColor(255, 255, 0, 100))
            gx1 = self._x(max(rs, rp)); gx2 = self._x(re_sec)
            if gx2 > gx1:
                p.fillRect(QRect(gx1, RULER_H, gx2 - gx1, WAVE_H), QColor(0, 255, 0, 70))

        for g in self.gap_segments:
            x1, x2 = self._x(g["start"]), self._x(g["end"]); sw = max(4, x2 - x1)
            rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
            p.fillRect(rect, QColor("#0d0d0d"))
            is_active = g.get("active", False)
            if is_active:
                p.setPen(QPen(QColor("#FFFFFF"), 2)); p.drawRect(rect); ir = self._icon_rect(x1, x2)
                p.fillRect(ir, QColor("#442222")); p.setPen(QColor("#FF8888")); p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")
            else:
                p.setPen(QPen(QColor("#888888"), 1, Qt.PenStyle.DotLine)); p.drawRect(rect)
                if sw >= ICON_SZ + 8:
                    ir = self._plus_rect(x1, x2); p.fillRect(ir, QColor("#112233")); p.setPen(QColor("#6699CC"))
                    p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold)); p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "+")

        seg_font = QFont(config.FONT, 14); p.setFont(seg_font)
        for seg in self.segments:
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = max(10, x2 - x1)
            rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
            is_active = (self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.5)
            is_hover = self._hover_line == seg.get("line")
            fill = (QColor("#1a3a1a") if is_active else QColor("#3a3a00") if is_hover else QColor("#2C2C2C"))
            border = QColor("#FFFF00") if is_active else QColor(config.ACCENT)
            bw = 2 if is_active else (2 if is_hover else 1)

            p.fillRect(rect, fill); p.setPen(QPen(border, bw)); p.drawRect(rect); p.setFont(seg_font)
            text_rect = QRect(x1 + HANDLE_R + 6, SEG_TOP + 5, sw - (HANDLE_R * 2) - 12, SEG_BOT - SEG_TOP - 10)
            is_editing = (self._edit_active and self._edit_line == seg.get("line"))

            if is_editing:
                disp_text = self._edit_text
                preedit = getattr(self, '_ime_preedit', '')
                cur = self._edit_cursor
                if preedit:
                    disp_text = disp_text[:cur] + preedit + disp_text[cur:]
                lines = disp_text.split('\n')
                fm = p.fontMetrics()
                line_h = fm.height()
                tx0 = text_rect.x(); ty0 = text_rect.y() + fm.ascent()
                p.fillRect(text_rect, QColor("#002200"))
                vis_cur = cur + len(preedit)
                r = 0; c = vis_cur
                for i, line in enumerate(lines):
                    if c <= len(line): r = i; break
                    c -= (len(line) + 1)
                curr_y = ty0
                for i, line in enumerate(lines):
                    p.setPen(QColor("#FFFF88"))
                    if preedit and i == r:
                        pre_start = c - len(preedit)
                        p.drawText(tx0, curr_y, line)
                        pre_w_start = fm.horizontalAdvance(line[:pre_start])
                        pre_w_end = fm.horizontalAdvance(line[:c])
                        p.setPen(QColor("#FFFF00"))
                        p.drawText(tx0 + pre_w_start, curr_y, preedit)
                        p.setPen(QPen(QColor("#FFFF00"), 1))
                        p.drawLine(tx0 + pre_w_start, curr_y + 1, tx0 + pre_w_end, curr_y + 1)
                    else:
                        p.drawText(tx0, curr_y, line)
                    if self._cursor_vis and i == r:
                        cx = tx0 + fm.horizontalAdvance(line[:c])
                        cursor_top = curr_y - fm.ascent()
                        cursor_bot = cursor_top + line_h
                        p.setPen(QPen(QColor("#FFFFFF"), 1))
                        p.drawLine(cx, cursor_top, cx, cursor_bot)
                    curr_y += line_h + 4
            else:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg.get("text", ""))

            ir = self._icon_rect(x1, x2)
            if sw > ICON_SZ + HANDLE_R + 4:
                p.fillRect(ir, QColor("#550000")); p.setPen(QColor("#FF6666")); p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")

            hovered = self._hover_handle
            lh = hovered and hovered[0] is seg and hovered[1] == "left"
            rh = hovered and hovered[0] is seg and hovered[1] == "right"
            self._draw_handle(p, x1, True, QColor("#44FF88") if lh else QColor("#888888"))
            self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        if hasattr(self, '_snap_lines') and self._snap_lines:
            p.setPen(QPen(QColor("#FF4444"), 4))
            for sx in self._snap_lines: p.drawLine(sx, SEG_TOP, sx, SEG_BOT)

        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]; s2 = self.segments[i + 1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"]); w = int(HANDLE_R * 1.2) * 2; h = 10; cy = SEG_BOT - (h // 2)
                rect = QRect(int(bx - w / 2), int(cy - h / 2), w, h)
                is_hover = (getattr(self, '_hover_diamond', None) == i)
                color = QColor("#FFD700") if is_hover else QColor("#AAAAAA")
                p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawRoundedRect(rect, 4, 4); p.setBrush(Qt.BrushStyle.NoBrush)

        # 멀티클립 박스
        if self._multiclip_boxes:
            for box in self._multiclip_boxes:
                bx1 = self._x(box["start"])
                bx2 = self._x(box["end"])
                bw = bx2 - bx1
                clip_idx = box.get("index", 1) - 1

                is_active = (clip_idx == getattr(self, '_active_clip_idx', -1))
                if is_active:
                    color = "#4AFF80"
                    width = 3
                else:
                    color = "#666666"
                    width = 1

                p.setPen(QPen(QColor(color), width))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(int(bx1), 0, int(bw), CANVAS_H)
                p.setPen(QColor(label_color))
                p.setFont(QFont("", 9, QFont.Weight.Bold))
                p.drawText(int(bx1) + 4, 12, f"CLIP {box.get('index', '?')}")

        if self.boundary_times:
            pen_boundary = QPen(QColor("#4AFF80"), 1)
            for bt in self.boundary_times:
                bx = self._x(bt)
                p.setPen(pen_boundary)
                p.drawLine(bx, 0, bx, CANVAS_H)

        if getattr(self, '_is_listening', False) and self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg:
                mic_x = self._x(seg["end"]) + 8
                mic_y = SEG_TOP + 5
                p.setFont(QFont(config.FONT, 18))
                p.setPen(QColor("#FF4444"))
                p.drawText(mic_x, mic_y + 20, "🎤")
                p.setFont(QFont(config.FONT, 10))
                p.setPen(QColor("#FF8888"))
                p.drawText(mic_x + 24, mic_y + 18, "음성인식 중...")

        if self.playhead_sec >= 0:
            ph_color = QColor("#4AFF80") if getattr(self, 'focus_mode', 'segment') == "waveform" else QColor("#FF4444")
            p.setPen(QPen(ph_color, 2)); px = self._x(self.playhead_sec); p.drawLine(px, 0, px, CANVAS_H)
            handle_r = 7
            self._playhead_handle_rect = QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QBrush(QColor("#FFCC00")))
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.drawEllipse(self._playhead_handle_rect)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _draw_handle(self, p, bx, is_left, color):
        cy = SEG_TOP + (SEG_BOT - SEG_TOP) // 2
        w = HANDLE_R; hw = HANDLE_R // 2; hh = 12; th = 4
        if is_left:
            bx += 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx + hw, cy - hh), QPoint(bx + hw, cy - th), QPoint(bx + w, cy - th), QPoint(bx + w, cy + th), QPoint(bx + hw, cy + th), QPoint(bx + hw, cy + hh)])
        else:
            bx -= 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx - hw, cy - hh), QPoint(bx - hw, cy - th), QPoint(bx - w, cy - th), QPoint(bx - w, cy + th), QPoint(bx - hw, cy + th), QPoint(bx - hw, cy + hh)])
        p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawPolygon(pts); p.setBrush(Qt.BrushStyle.NoBrush)