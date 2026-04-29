# Version: 03.00.22
# Phase: PHASE1-C
"""
ui/timeline_paint.py
Timeline paint mixin
"""
import numpy as np
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPolygon

import config

from ui.timeline.timeline_constants import (
    CANVAS_H,
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
    WAVE_H,
    WAVE_HALF,
    WAVE_MID,
)


class TimelinePaintMixin:

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        total_w = self.total_width()
        total_secs = self.total_duration + 2
        subtitle_top = SUBTITLE_TOP
        subtitle_bot = SUBTITLE_BOT
        speaker_top = SPEAKER_TOP
        speaker_bot = SPEAKER_BOT
        voice_mid = speaker_bot + 17
        audio_mid = voice_mid + 28
        track_bottom = CANVAS_H - 8

        def _speaker_color(seg):
            spk = str(seg.get("speaker", seg.get("spk_id", "")) or "")
            if spk.startswith("SPEAKER_"):
                spk = spk.replace("SPEAKER_", "")
            palette = {
                "00": "#579DFF",
                "01": "#75C76B",
                "02": "#FF9F2F",
            }
            return QColor(palette.get(spk, "#8E8E93"))

        def _speaker_name(seg):
            def label_for(raw, fallback="홍길동"):
                spk = str(raw or "")
                if spk.startswith("SPEAKER_"):
                    spk = spk.replace("SPEAKER_", "")
                if spk in ("00", "01", "02"):
                    return f"화자{int(spk) + 1}"
                return fallback

            spk_list = list(seg.get("speaker_list", []) or [])
            if len(spk_list) > 1:
                return " / ".join(label_for(spk, f"화자{i + 1}") for i, spk in enumerate(spk_list))
            if seg.get("speaker_name"):
                return str(seg.get("speaker_name"))
            if "speaker" in seg or "spk_id" in seg:
                return label_for(seg.get("speaker", seg.get("spk_id")), "화자1")
            return "홍길동"

        def _draw_lane_wave(mid_y, color_top, color_bot, gain=1.0, alpha=210):
            if self._waveform is None:
                return
            wf = self._waveform
            wf_len = len(wf)
            if wf_len <= 0:
                return
            clip = event.rect()
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            top = QColor(color_top); top.setAlpha(alpha)
            bot = QColor(color_bot); bot.setAlpha(alpha)
            p.setPen(QPen(QColor(255, 255, 255, 24), 1))
            p.drawLine(x_start, mid_y, x_end, mid_y)
            for x in range(x_start, x_end):
                idx = int((x / max(0.001, self.pps)) * 100)
                if idx >= wf_len:
                    break
                val = float(wf[idx])
                if val < 0.006:
                    continue
                h = max(1, min(11, int(val * 18 * gain)))
                p.setPen(QPen(top, 1)); p.drawLine(x, mid_y, x, mid_y - h)
                p.setPen(QPen(bot, 1)); p.drawLine(x, mid_y + 1, x, mid_y + h)

        def _draw_vad_voice_lane(mid_y):
            if self._waveform is None:
                return
            clip = event.rect()
            lane_top = mid_y - 12
            lane_h = 24
            p.setPen(Qt.PenStyle.NoPen)
            for vs in self.vad_segments:
                x1 = self._x(float(vs.get("start", 0.0)))
                x2 = self._x(float(vs.get("end", 0.0)))
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                rect = QRectF(x1, lane_top, w, lane_h)
                p.setBrush(QColor(22, 84, 156, 82))
                p.drawRoundedRect(rect, 4, 4)
                p.setPen(QPen(QColor(87, 157, 255, 210), 1))
                p.drawLine(x1, lane_top + 2, x1, lane_top + lane_h - 2)
                p.drawLine(x2, lane_top + 2, x2, lane_top + lane_h - 2)
                p.setPen(QPen(QColor(116, 184, 255, 190), 1))
                step = max(3, int(5 * max(1.0, self.pps / 40)))
                for x in range(max(int(x1), clip.left()), min(int(x2), clip.right()) + 1, step):
                    idx = int((x / max(0.001, self.pps)) * 100)
                    if idx >= len(self._waveform):
                        break
                    val = float(self._waveform[idx])
                    h = max(2, min(9, int(val * 15)))
                    p.drawLine(x, mid_y - h, x, mid_y + h)
            p.setPen(QPen(QColor(87, 157, 255, 80), 1))
            p.drawLine(max(0, clip.left()), mid_y, min(total_w, clip.right() + 1), mid_y)

        p.fillRect(QRect(0, 0, total_w, CANVAS_H), QColor("#0F1518"))

        def _fmt_ruler(sec):
            s = int(sec)
            h, rem = divmod(s, 3600)
            m, sc = divmod(rem, 60)
            if h > 0:
                return f"{h}:{m:02d}:{sc:02d}"
            return f"{m:02d}:{sc:02d}"

        ruler_font = QFont(config.FONT, 10)
        ruler_font.setBold(True)
        p.setFont(ruler_font)
        fm_ruler = p.fontMetrics()

        MIN_LABEL_PX = 80
        nice_steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]

        major_step = 1.0
        for ns in nice_steps:
            if ns * self.pps >= MIN_LABEL_PX:
                major_step = ns
                break
        else:
            major_step = nice_steps[-1]

        if major_step >= 0.5:
            sub_step = major_step / 5
        else:
            sub_step = major_step / 2
        
        # 메이저 틱 + 라벨
        sec_i = 0.0
        while sec_i <= total_secs:
            tx = self._x(sec_i)
            if sec_i > 0:
                p.setPen(QColor("#6F7A83"))
                p.drawLine(tx, 10, tx, RULER_H - 9)
                label = _fmt_ruler(sec_i)
                lw = fm_ruler.horizontalAdvance(label)
                p.setPen(QColor("#A9B0B7"))
                p.drawText(tx - lw // 2, RULER_H - 7, label)
            sec_i = round(sec_i + major_step, 3)

        # 서브 틱 (라벨 없음)
        sec_f = 0.0
        while sec_f <= total_secs:
            # 메이저 틱 위치면 스킵
            if major_step > 0 and abs(round(sec_f / major_step) * major_step - sec_f) < 0.001:
                sec_f = round(sec_f + sub_step, 3)
                continue
            tx = self._x(sec_f)
            p.setPen(QColor("#46525B"))
            p.drawLine(tx, 13, tx, RULER_H - 14)
            sec_f = round(sec_f + sub_step, 3)

        p.fillRect(QRect(0, RULER_H, total_w, WAVE_H), QColor("#070A0C"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            p.setPen(QPen(QColor("#2D3942"), 1))
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

            pen_top_norm = QPen(QColor(170, 176, 184), 1)
            pen_bot_norm = QPen(QColor(104, 110, 118), 1)
            pen_top_loud = QPen(QColor(220, 224, 228), 1)
            pen_bot_loud = QPen(QColor(150, 156, 164), 1)
            pen_top_sil = QPen(QColor(82, 87, 94), 1)
            pen_bot_sil = QPen(QColor(56, 61, 68), 1)

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

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(87, 157, 255, 34))
            for vs in self.vad_segments:
                vx1 = self._x(vs["start"])
                vx2 = self._x(vs["end"])
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

        p.fillRect(QRect(0, SEG_TOP, total_w, SEG_BOT - SEG_TOP), QColor("#11181C"))
        p.setPen(QPen(QColor("#2D3942"), 1))
        for y in (subtitle_top - 5, speaker_top - 3, voice_mid - 14, audio_mid - 14, track_bottom):
            p.drawLine(0, y, total_w, y)

        label_font = QFont(config.FONT, 9, QFont.Weight.Bold)
        p.setFont(label_font)
        for text, y in (("자막", subtitle_top + 20), ("화자", speaker_top + 15), ("음성 감지", voice_mid + 4), ("오디오", audio_mid + 4)):
            p.setPen(QColor("#A9B0B7"))
            p.drawText(8, y, text)

        for g in self.gap_segments:
            x1, x2 = self._x(g["start"]), self._x(g["end"]); sw = max(4, x2 - x1)
            rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
            p.fillRect(rect, QColor(20, 16, 0, 118))
            is_active = g.get("active", False)
            if is_active:
                p.setPen(QPen(QColor("#FFFFFF"), 2)); p.drawRect(rect); ir = self._icon_rect(x1, x2)
                p.fillRect(ir, QColor("#3B1D20")); p.setPen(QColor("#FF8A80")); p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")
            else:
                p.setPen(QPen(QColor("#4F5962"), 1, Qt.PenStyle.DotLine)); p.drawRect(rect)
                if sw >= ICON_SZ + 8:
                    ir = self._plus_rect(x1, x2); p.fillRect(ir, QColor("#17232A")); p.setPen(QColor("#8EA4B8"))
                    p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold)); p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "+")

        seg_font = QFont(config.FONT, 9); p.setFont(seg_font)
        for seg in self.segments:
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = max(10, x2 - x1)
            rect = QRect(x1 + 2, subtitle_top, max(8, sw - 4), subtitle_bot - subtitle_top)
            is_active = (self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.5)
            is_hover = self._hover_line == seg.get("line")
            is_stt_pending = bool(seg.get("stt_pending"))
            fill = QColor("#4A1F24") if is_stt_pending else (QColor("#1D3D76") if is_active else (QColor("#222A31") if is_hover else QColor("#242A30")))
            border = QColor("#FF453A") if is_stt_pending else (QColor("#8AB8FF") if is_active else QColor("#3A4650"))
            bw = 2 if is_active else (2 if is_hover else 1)

            grad = QLinearGradient(float(rect.left()), float(rect.top()), float(rect.left()), float(rect.bottom()))
            grad.setColorAt(0, fill.lighter(112))
            grad.setColorAt(1, fill.darker(118))
            p.setBrush(QBrush(grad)); p.setPen(QPen(border, bw)); p.drawRoundedRect(QRectF(rect), 5, 5); p.setBrush(Qt.BrushStyle.NoBrush); p.setFont(seg_font)
            text_rect = QRect(rect.x() + 10, rect.y() + 6, max(8, rect.width() - 20), rect.height() - 12)
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
                p.fillRect(text_rect, QColor("#123A24"))
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
                p.setPen(QColor("#8A8F98") if is_stt_pending else QColor("#DCE3EA"))
                p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg.get("text", ""))

            ir = self._icon_rect(x1, x2)
            if sw > ICON_SZ + HANDLE_R + 4:
                p.fillRect(ir, QColor("#3B1D20")); p.setPen(QColor("#FF8A80")); p.setFont(QFont(config.FONT, 12, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")

            spk_color = _speaker_color(seg)
            speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.setBrush(QColor("#1B2429"))
            p.drawRoundedRect(QRectF(speaker_rect), 4, 4)
            p.setBrush(spk_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRect(speaker_rect.x() + 9, speaker_rect.y() + 6, 8, 8))
            p.setPen(spk_color)
            p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
            p.drawText(QRect(speaker_rect.x() + 22, speaker_rect.y(), speaker_rect.width() - 26, speaker_rect.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, _speaker_name(seg))

            hovered = self._hover_handle
            lh = hovered and hovered[0] is seg and hovered[1] == "left"
            rh = hovered and hovered[0] is seg and hovered[1] == "right"
            self._draw_handle(p, x1, True, QColor("#44FF88") if lh else QColor("#888888"))
            self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        if hasattr(self, '_snap_lines') and self._snap_lines:
            p.setPen(QPen(QColor("#FF4444"), 4))
            for sx in self._snap_lines: p.drawLine(sx, SEG_TOP, sx, SEG_BOT)

        _draw_vad_voice_lane(voice_mid)
        _draw_lane_wave(audio_mid, "#7BD88F", "#2F8F46", gain=0.85, alpha=165)

        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]; s2 = self.segments[i + 1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"]); r = 5; cy = DIAMOND_Y
                is_hover = (getattr(self, '_hover_diamond', None) == i)
                color = QColor("#FFFFFF") if is_hover else QColor("#AAB0B6")
                pts = QPolygon([
                    QPoint(bx, cy - r),
                    QPoint(bx + r, cy),
                    QPoint(bx, cy + r),
                    QPoint(bx - r, cy),
                ])
                p.setPen(QPen(QColor("#000000"), 1))
                p.setBrush(QBrush(color))
                p.drawPolygon(pts)
                p.setBrush(Qt.BrushStyle.NoBrush)

        self._clip_delete_rects = []
        self._clip_add_rect = QRect()
        if self._multiclip_boxes:
            for box in self._multiclip_boxes:
                bx1 = self._x(box["start"])
                bx2 = self._x(box["end"])
                bw = bx2 - bx1

                clip_idx = box.get("index", 1) - 1
                is_active = clip_idx == getattr(self, "_active_clip_idx", -1)

                color = "#4AFF80" if is_active else "#666666"
                width = 3 if is_active else 1

                p.setPen(QPen(QColor(color), width))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(int(bx1), 0, int(bw), CANVAS_H)

                # CLIP label: top-right outside box + delete
                clip_label = f"CLIP {box.get('index', '?')}"
                delete_label = '[X]'
                p.setFont(QFont("", 9, QFont.Weight.Bold))
                fm = p.fontMetrics()
                label_w = fm.horizontalAdvance(clip_label) + 10
                delete_w = fm.horizontalAdvance(delete_label) + 10
                total_w = label_w + 6 + delete_w
                lbl_x = int(bx2) - total_w - 4
                lbl_y = 20
                clip_rect = QRect(lbl_x, lbl_y, label_w, 16)
                delete_rect = QRect(lbl_x + label_w + 6, lbl_y, delete_w, 16)
                self._clip_delete_rects.append((clip_idx, delete_rect))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 180))
                p.drawRoundedRect(clip_rect, 3, 3)
                p.drawRoundedRect(delete_rect, 3, 3)
                p.setPen(QColor(color))
                p.drawText(clip_rect, Qt.AlignmentFlag.AlignCenter, clip_label)
                p.setPen(QColor('#FF8080'))
                p.drawText(delete_rect, Qt.AlignmentFlag.AlignCenter, delete_label)

        if self._multiclip_boxes:
            placeholder_dur = 30.0
            last_box = self._multiclip_boxes[-1]
            px1 = self._x(last_box['end'])
            px2 = self._x(last_box['end'] + placeholder_dur)
            pw = px2 - px1
            p.setPen(QPen(QColor('#555555'), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(int(px1), 0, int(pw), CANVAS_H)
            self._clip_add_placeholder = {'start': last_box['end'], 'end': last_box['end'] + placeholder_dur}
            self._clip_add_rect = QRect(int(px1 + (pw // 2) - 14), int((CANVAS_H // 2) - 14), 28, 28)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#112233'))
            p.drawRoundedRect(self._clip_add_rect, 4, 4)
            p.setPen(QColor('#4AFF80'))
            p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold))
            p.drawText(self._clip_add_rect, Qt.AlignmentFlag.AlignCenter, '+')

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
                p.drawText(mic_x + 24, mic_y + 18, "Listening...")

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

        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#FFFF00"), 2))
            left = 1
            right = max(1, total_w - 2)
            bottom = max(1, CANVAS_H - 2)
            p.drawLine(left, 1, left, bottom)
            p.drawLine(right, 1, right, bottom)
            p.drawLine(left, bottom, right, bottom)

    def _draw_handle(self, p, bx, is_left, color):
        cy = SEG_TOP + 32
        w = HANDLE_R; hw = HANDLE_R // 2; hh = 12; th = 4
        if is_left:
            bx += 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx + hw, cy - hh), QPoint(bx + hw, cy - th), QPoint(bx + w, cy - th), QPoint(bx + w, cy + th), QPoint(bx + hw, cy + th), QPoint(bx + hw, cy + hh)])
        else:
            bx -= 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx - hw, cy - hh), QPoint(bx - hw, cy - th), QPoint(bx - w, cy - th), QPoint(bx - w, cy + th), QPoint(bx - hw, cy + th), QPoint(bx - hw, cy + hh)])
        p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawPolygon(pts); p.setBrush(Qt.BrushStyle.NoBrush)
