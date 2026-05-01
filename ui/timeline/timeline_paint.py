# Version: 03.02.17
# Phase: PHASE1-C
"""
ui/timeline_paint.py
Timeline paint mixin
"""
import numpy as np
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon

import config

from ui.timeline.timeline_constants import (
    CANVAS_H,
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
    WAVE_H,
    WAVE_HALF,
    WAVE_MID,
)
from ui.timeline.timeline_analysis import analysis_markers_for_widget, roughcut_major_markers_for_widget
from ui.timeline.speaker_labels import (
    current_speaker_settings,
    normalize_speaker_id,
    speaker_labels_for_segment,
)

SEGMENT_TEXT_KIND_STYLES = {
    "speech": {
        "fill": "#123A24",
        "border": "#34C759",
        "text": "#E8FFF0",
    },
    "silence": {
        "fill": "#3B2A13",
        "border": "#FF9500",
        "text": "#FFF1D6",
    },
}


def segment_text_kind(text: str) -> str:
    normalized = "".join(str(text or "").split())
    if normalized == "음성":
        return "speech"
    if normalized == "무음":
        return "silence"
    return ""


class TimelinePaintMixin:

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        total_w = self.total_width()
        total_secs = self.total_duration + 2
        paint_clip = event.rect()
        clip_left = max(0, paint_clip.left())
        clip_right = min(total_w, paint_clip.right() + 1)
        overview_mode = float(getattr(self, "pps", 0.0) or 0.0) < 8.0
        subtitle_top = SUBTITLE_TOP
        subtitle_bot = SUBTITLE_BOT
        speaker_top = SPEAKER_TOP
        speaker_bot = SPEAKER_BOT
        voice_mid = speaker_bot + 17
        audio_mid = voice_mid + 28
        track_bottom = SEG_BOT

        def _owner_speaker_settings():
            owner = self.parent()
            while owner and not hasattr(owner, "settings"):
                owner = owner.parent()
            return getattr(owner, "settings", {}) if owner is not None else {}

        speaker_settings = current_speaker_settings(_owner_speaker_settings())

        def _speaker_color(seg):
            spk = normalize_speaker_id(seg.get("speaker", seg.get("spk_id", "")))
            palette = {
                str(speaker_settings.get("spk1_id", "00")): str(speaker_settings.get("spk1_color", "#579DFF")),
                str(speaker_settings.get("spk2_id", "01")): str(speaker_settings.get("spk2_color", "#75C76B")),
                str(speaker_settings.get("spk3_id", "02")): str(speaker_settings.get("spk3_color", "#FF9F2F")),
            }
            return QColor(palette.get(spk, "#8E8E93"))

        def _speaker_names(seg):
            return speaker_labels_for_segment(speaker_settings, seg)

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

        def _draw_analysis_lane(mid_y):
            lane_top = mid_y - 12
            lane_h = 24
            clip = event.rect()
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#0B1418"))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.drawLine(x_start, mid_y, x_end, mid_y)

            if hasattr(self, "analysis_markers_cached"):
                markers = self.analysis_markers_cached()
            else:
                markers = analysis_markers_for_widget(
                    self,
                    list(getattr(self, "segments", []) or []),
                    list(getattr(self, "vad_segments", []) or []),
                    list(getattr(self, "gap_segments", []) or []),
                    float(getattr(self, "total_duration", 0.0) or 0.0),
                )
            markers.sort(key=lambda item: int(item.get("priority", 0) or 0))
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x1 = self._x(start)
                x2 = self._x(end)
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                color = QColor(str(marker.get("color", "#8B949E")))
                color.setAlpha(int(marker.get("alpha", 120) or 120))
                border = QColor(str(marker.get("color", "#8B949E")))
                border.setAlpha(220)
                rect = QRectF(x1, lane_top + 3, w, lane_h - 6)
                p.setBrush(color)
                p.setPen(QPen(border, 1))
                p.drawRoundedRect(rect, 3, 3)
                if w >= 42:
                    p.setPen(QColor("#F5F7FA"))
                    p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
                    p.drawText(QRect(int(x1) + 4, lane_top + 2, int(w) - 8, lane_h - 4), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(marker.get("label", "")))

        def _draw_roughcut_major_lane():
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else roughcut_major_markers_for_widget(self)
            if not markers:
                return
            clip = event.rect()
            lane_top = RULER_H + WAVE_H + 5
            lane_h = max(18, SEG_TOP - lane_top - 7)
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.setBrush(QColor("#0B1418"))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x1 = self._x(start)
                x2 = self._x(end)
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                color = QColor(str(marker.get("color", "#34C759")))
                fill = QColor(color)
                fill.setAlpha(int(marker.get("alpha", 48) or 48))
                border = QColor(color)
                border.setAlpha(230)
                rect = QRectF(x1 + 1, lane_top + 2, max(2, w - 2), lane_h - 4)
                p.setBrush(fill)
                p.setPen(QPen(border, 1))
                p.drawRoundedRect(rect, 5, 5)
                label = str(marker.get("label", "") or "")
                title = str(marker.get("title", "") or "").strip()
                text = label if w < 118 or not title else f"{label}  {title[:18]}"
                if w >= 28 and text:
                    p.setPen(border.lighter(145))
                    p.drawText(QRect(int(x1) + 6, lane_top, int(w) - 12, lane_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter, text)

        p.fillRect(paint_clip, QColor("#0F1518"))

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
        
        visible_start_sec = max(0.0, clip_left / max(0.001, float(self.pps)))

        # 메이저 틱 + 라벨
        sec_i = max(0.0, (int(visible_start_sec / major_step) * major_step) - major_step)
        while sec_i <= total_secs:
            tx = self._x(sec_i)
            if tx > clip_right:
                break
            if sec_i > 0:
                p.setPen(QColor("#6F7A83"))
                p.drawLine(tx, 10, tx, RULER_H - 9)
                label = _fmt_ruler(sec_i)
                lw = fm_ruler.horizontalAdvance(label)
                p.setPen(QColor("#A9B0B7"))
                p.drawText(tx - lw // 2, RULER_H - 7, label)
            sec_i = round(sec_i + major_step, 3)

        # 서브 틱 (라벨 없음)
        sec_f = max(0.0, (int(visible_start_sec / sub_step) * sub_step) - sub_step)
        while sec_f <= total_secs:
            tx = self._x(sec_f)
            if tx > clip_right:
                break
            # 메이저 틱 위치면 스킵
            if major_step > 0 and abs(round(sec_f / major_step) * major_step - sec_f) < 0.001:
                sec_f = round(sec_f + sub_step, 3)
                continue
            p.setPen(QColor("#46525B"))
            p.drawLine(tx, 13, tx, RULER_H - 14)
            sec_f = round(sec_f + sub_step, 3)

        p.fillRect(QRect(clip_left, RULER_H, max(1, clip_right - clip_left), WAVE_H), QColor("#070A0C"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            p.setPen(QPen(QColor("#2D3942"), 1))
            p.drawLine(clip_left, WAVE_MID, clip_right, WAVE_MID)

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
                if vx2 < clip_left or vx1 > clip_right:
                    continue
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

        _draw_roughcut_major_lane()

        p.fillRect(QRect(clip_left, SEG_TOP, max(1, clip_right - clip_left), SEG_BOT - SEG_TOP), QColor("#11181C"))
        p.setPen(QPen(QColor("#2D3942"), 1))
        for y in (subtitle_top - 5, speaker_top - 3, voice_mid - 14, audio_mid - 14, track_bottom):
            p.drawLine(clip_left, y, clip_right, y)

        label_font = QFont(config.FONT, 9, QFont.Weight.Bold)
        p.setFont(label_font)
        for text, y in (("자막", subtitle_top + 20), ("화자", speaker_top + 15), ("음성 감지", voice_mid + 4), ("분석", audio_mid + 4)):
            if overview_mode and text in {"음성 감지", "분석"}:
                continue
            p.setPen(QColor("#A9B0B7"))
            p.drawText(8, y, text)

        for g in self.gap_segments:
            x1, x2 = self._x(g["start"]), self._x(g["end"]); sw = max(4, x2 - x1)
            if x2 < clip_left or x1 > clip_right:
                continue
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
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = max(2, x2 - x1)
            if x2 < clip_left or x1 > clip_right:
                continue
            compact_seg = sw < 24
            rect = QRect(x1 + 1, subtitle_top, max(2, sw - 2), subtitle_bot - subtitle_top)
            is_active = (self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.5)
            is_hover = self._hover_line == seg.get("line")
            is_stt_pending = bool(seg.get("stt_pending"))
            spk_color = _speaker_color(seg)
            if overview_mode and compact_seg:
                fill = QColor("#4A1F24") if is_stt_pending else (QColor("#1D3D76") if is_active else QColor("#242A30"))
                border = QColor("#FF453A") if is_stt_pending else (QColor("#8AB8FF") if is_active else QColor("#3A4650"))
                p.fillRect(rect, fill)
                p.setPen(QPen(border, 1))
                p.drawRect(rect)
                speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                p.fillRect(speaker_rect, spk_color.darker(135))
                continue
            quality = dict(seg.get("quality") or {})
            q_label = str(quality.get("confidence_label") or "")
            q_flags = set(quality.get("flags") or ())
            q_filter = str(getattr(self, "quality_filter", "all") or "all")
            q_colors = {
                "green": ("#203A2A", "#34C759"),
                "yellow": ("#3B341D", "#FFCC00"),
                "red": ("#4A1F24", "#FF453A"),
                "gray": ("#2F343A", "#8E8E93"),
            }
            q_matches = (
                q_filter == "all"
                or q_filter == q_label
                or (q_filter == "needs_review" and (q_label in {"red", "gray"} or bool(q_flags.intersection({"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}))))
                or (q_filter == "auto_corrected" and "auto_corrected" in q_flags)
            )
            text_kind = segment_text_kind(seg.get("text", ""))
            kind_style = SEGMENT_TEXT_KIND_STYLES.get(text_kind, {})
            if kind_style:
                fill = QColor(kind_style["fill"])
                border = QColor(kind_style["border"])
            elif quality and q_label in q_colors:
                fill = QColor(q_colors[q_label][0])
                border = QColor(q_colors[q_label][1])
            else:
                fill = QColor("#4A1F24") if is_stt_pending else (QColor("#1D3D76") if is_active else (QColor("#222A31") if is_hover else QColor("#242A30")))
                border = QColor("#FF453A") if is_stt_pending else (QColor("#8AB8FF") if is_active else QColor("#3A4650"))
            if quality and not q_matches:
                fill = QColor("#1A2025")
                border = QColor("#2D3942")
            bw = 2 if (is_active or is_hover) and not compact_seg else 1

            p.fillRect(rect, fill)
            p.setPen(QPen(border, bw))
            p.drawRect(rect)
            p.setFont(seg_font)
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
                if rect.width() >= 44:
                    text_color = kind_style.get("text", "")
                    p.setPen(QColor(text_color) if text_color else (QColor("#8A8F98") if is_stt_pending else QColor("#DCE3EA")))
                    p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg.get("text", ""))

            ir = self._icon_rect(x1, x2)
            if sw > ICON_SZ + HANDLE_R + 4:
                p.fillRect(ir, QColor("#3B1D20")); p.setPen(QColor("#FF8A80")); p.setFont(QFont(config.FONT, 12, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")

            speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
            if compact_seg:
                p.fillRect(speaker_rect, spk_color.darker(135))
            else:
                p.setPen(QPen(QColor("#2D3942"), 1))
                p.setBrush(QColor("#1B2429"))
                p.drawRect(speaker_rect)
            if not compact_seg and speaker_rect.width() >= 42:
                self._draw_speaker_names(p, speaker_rect, spk_color, _speaker_names(seg))

            if sw >= SEGMENT_HANDLE_MIN_WIDTH:
                lh = self._hover_handle_matches(seg, "left")
                rh = self._hover_handle_matches(seg, "right")
                self._draw_handle(p, x1, True, QColor("#44FF88") if lh else QColor("#888888"))
                self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        self._draw_edge_drag_preview(p, subtitle_top, subtitle_bot, clip_left, clip_right)

        if hasattr(self, '_snap_lines') and self._snap_lines:
            p.setPen(QPen(QColor("#FF4444"), 4))
            for sx in self._snap_lines: p.drawLine(sx, SEG_TOP, sx, SEG_BOT)

        if not overview_mode:
            _draw_vad_voice_lane(voice_mid)
            _draw_analysis_lane(audio_mid)

        if self.pps >= 8:
            for i in range(len(self.segments) - 1):
                s1 = self.segments[i]; s2 = self.segments[i + 1]
                if abs(s1["end"] - s2["start"]) < 0.05:
                    bx = self._x(s1["end"]); r = 5; cy = DIAMOND_Y
                    if bx < clip_left - r or bx > clip_right + r:
                        continue
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
        self._clip_add_placeholder = None
        if self._multiclip_boxes:
            for box in self._multiclip_boxes:
                bx1 = self._x(box["start"])
                bx2 = self._x(box["end"])
                bw = bx2 - bx1
                if bx2 < clip_left or bx1 > clip_right:
                    continue

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
                label_total_w = label_w + 6 + delete_w
                lbl_x = int(bx2) - label_total_w - 4
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

        add_anchor_sec = None
        if self._multiclip_boxes:
            add_anchor_sec = float(self._multiclip_boxes[-1].get("end", 0.0) or 0.0)
        elif self.total_duration > 0:
            add_anchor_sec = float(self.total_duration)
        elif self.segments:
            add_anchor_sec = max(float(seg.get("end", 0.0) or 0.0) for seg in self.segments)

        if add_anchor_sec is not None:
            add_x = self._x(add_anchor_sec) + 8
            add_w = 50
            add_h = max(24, subtitle_bot - subtitle_top)
            self._clip_add_rect = QRect(int(add_x), int(subtitle_top), add_w, add_h)
            self._clip_add_placeholder = {
                "start": add_anchor_sec,
                "end": add_anchor_sec + (add_w / max(1.0, float(self.pps))),
            }
            p.setPen(QPen(QColor("#4AFF80"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(17, 34, 51, 180))
            p.drawRoundedRect(QRectF(self._clip_add_rect), 5, 5)
            p.setPen(QColor("#4AFF80"))
            p.setFont(QFont(config.FONT, 20, QFont.Weight.Bold))
            p.drawText(self._clip_add_rect, Qt.AlignmentFlag.AlignCenter, "+")

        if self.boundary_times:
            pen_boundary = QPen(QColor("#4AFF80"), 1)
            for bt in self.boundary_times:
                bx = self._x(bt)
                if bx < clip_left or bx > clip_right:
                    continue
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

        if self.playhead_sec >= 0 and not getattr(self, "_external_playhead_overlay", False):
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
        cy = SEG_TOP + 32
        w = HANDLE_R; hw = HANDLE_R // 2; hh = 12; th = 4
        if is_left:
            bx += 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx + hw, cy - hh), QPoint(bx + hw, cy - th), QPoint(bx + w, cy - th), QPoint(bx + w, cy + th), QPoint(bx + hw, cy + th), QPoint(bx + hw, cy + hh)])
        else:
            bx -= 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx - hw, cy - hh), QPoint(bx - hw, cy - th), QPoint(bx - w, cy - th), QPoint(bx - w, cy + th), QPoint(bx - hw, cy + th), QPoint(bx - hw, cy + hh)])
        p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawPolygon(pts); p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_speaker_names(self, p, rect: QRect, color: QColor, names: list[str]):
        names = [str(name).strip() for name in names if str(name).strip()]
        if not names:
            return

        max_lines = 2
        visible_names = names[:max_lines]
        multi_line = len(visible_names) > 1
        font_size = 7 if multi_line else 8
        p.setFont(QFont(config.FONT, font_size, QFont.Weight.Bold))
        fm = p.fontMetrics()
        line_h = fm.height()
        gap = 0 if multi_line else 1
        dot = 6 if multi_line else 8
        text_gap = 5 if multi_line else 6
        row_h = max(dot, line_h)
        total_h = len(visible_names) * row_h + max(0, len(visible_names) - 1) * gap
        y = rect.y() + max(0, (rect.height() - total_h) // 2)
        max_row_w = max(
            dot + text_gap + fm.horizontalAdvance(name)
            for name in visible_names
        )
        x = rect.x() + max(6, (rect.width() - max_row_w) // 2)
        max_text_w = max(8, rect.right() - x - dot - text_gap - 4)

        p.setPen(color)
        p.setBrush(color)
        for idx, name in enumerate(visible_names):
            row_y = y + idx * (row_h + gap)
            dot_y = row_y + max(0, (row_h - dot) // 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRect(x, dot_y, dot, dot))
            p.setPen(color)
            text_rect = QRect(x + dot + text_gap, row_y, max_text_w, row_h)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

    def _draw_edge_drag_preview(self, p, subtitle_top: int, subtitle_bot: int, clip_left: int, clip_right: int):
        edge = str(getattr(self, "_drag_edge", "") or "")
        if edge not in {"square_left", "square_right"}:
            return
        seg = getattr(self, "_drag_seg", None)
        if not seg:
            return

        if edge == "square_left":
            original_x = self._x(float(getattr(self, "_drag_s0_start", seg.get("start", 0.0)) or 0.0))
            current_x = self._x(float(seg.get("start", 0.0) or 0.0))
            handle_x = current_x
            is_left = True
        else:
            original_x = self._x(float(getattr(self, "_drag_s0_end", seg.get("end", 0.0)) or 0.0))
            current_x = self._x(float(seg.get("end", 0.0) or 0.0))
            handle_x = current_x
            is_left = False

        left = min(original_x, current_x)
        right = max(original_x, current_x)
        if right - left < 2:
            return
        if right < clip_left or left > clip_right:
            return

        y = subtitle_top + 5
        h = max(8, subtitle_bot - subtitle_top - 10)
        rect = QRect(max(left, clip_left), y, max(2, min(right, clip_right) - max(left, clip_left)), h)
        fill = QColor("#FFF200")
        fill.setAlpha(150)
        border = QColor("#FF453A")
        border.setAlpha(235)
        p.fillRect(rect, fill)
        p.setPen(QPen(border, 2))
        p.drawRect(rect)
        self._draw_handle(p, handle_x, is_left, QColor("#44FF88"))

    def _hover_handle_matches(self, seg, edge: str) -> bool:
        hovered = getattr(self, "_hover_handle", None)
        if not hovered or len(hovered) < 2 or hovered[1] != edge:
            return False
        hover_seg = hovered[0]
        if hover_seg is seg:
            return True
        try:
            return (
                hover_seg.get("line") == seg.get("line")
                and abs(float(hover_seg.get("start", -1.0)) - float(seg.get("start", -2.0))) < 0.001
                and abs(float(hover_seg.get("end", -1.0)) - float(seg.get("end", -2.0))) < 0.001
            )
        except Exception:
            return False
