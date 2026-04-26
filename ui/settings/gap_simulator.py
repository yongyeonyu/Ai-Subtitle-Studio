# Version: 02.03.02
# Phase: PHASE1-B
"""Gap settings live preview simulator widget."""

from PyQt6.QtWidgets import QWidget, QToolTip
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QFontMetrics
from PyQt6.QtCore import Qt, QRect


class GapSimulatorWidget(QWidget):
    """실시간 AI 엔진 시뮬레이터 (X5 시승기 실전 데이터 + 오답 필터링 + 마우스 호버 툴팁)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(380) 
        
        # 💡 [추가] 마우스 움직임을 추적하여 그려진 상자 위에서 툴팁을 띄우기 위함
        self.setMouseTracking(True)
        self.hover_rects = [] # (QRect, 설명텍스트) 저장 리스트
        
        # 엔진 파라미터 초기화
        self.cont_thresh = 2.0
        self.push_rate = 0.7
        self.pull_rate = 0.3
        self.single_ext = 0.2
        self.split_len = 15
        self.min_dur = 0.3
        self.max_cps = 12
        self.dedup_win = 0.5
        self.gap_break = 1.5
        self.min_chars = 5
        self.pre_merge = 3.0
        self.enforce_ratio = 1.5
        self.hal_dur = 0.8
        self.hal_chars = 10
        self.skip_dur = 1.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        painter.fillRect(rect, QColor("#121212"))
        
        self.hover_rects.clear() # 💡 [추가] 화면을 다시 그릴 때마다 툴팁 영역 초기화
        
        max_time = 28.0
        offset_x = 20
        usable_w = rect.width() - (offset_x * 2)
        px_per_sec = usable_w / max_time
        
        blocks = [
            {"id": 1, "start": 1.0, "end": 5.5, "text": "이 차는 BMW X5 40i 모델이고 인기가 너무 좋아가지고 대기가 두 달 정도 걸립니다", "chars": 39, "type": "normal"}, 
            {"id": 2, "start": 6.5, "end": 6.7, "text": "어", "chars": 1, "type": "noise"}, 
            {"id": 3, "start": 7.5, "end": 8.0, "text": "시청해주셔서감사합니다구독", "chars": 13, "type": "halluc"}, 
            {"id": 4, "start": 9.0, "end": 11.0, "text": "그쵸 그쵸 그쵸 그쵸", "chars": 11, "type": "repeat"},
            {"id": 5, "start": 12.0, "end": 12.5, "text": "오우~", "chars": 3, "type": "normal"}, 
            {"id": 6, "start": 12.8, "end": 14.5, "text": "잘 나간다", "chars": 5, "type": "normal"}, 
            {"id": 7, "start": 15.5, "end": 16.0, "text": "이차는진짜엄청나게빨라요순식간에", "chars": 16, "type": "cps"}, 
            {"id": 8, "start": 17.5, "end": 18.3, "text": "와 바다다", "chars": 5, "type": "normal"}, 
            {"id": 9, "start": 19.5, "end": 22.0, "text": "반응이 즉각적이고", "chars": 8, "type": "normal"}, 
            {"id": 10, "start": 22.5, "end": 25.5, "text": "핸들이 묵직해졌어요", "chars": 9, "type": "normal"}, 
        ]

        filtered = []
        last_text = ""
        last_end = -99
        for b in blocks:
            c = dict(b)
            dur = c["end"] - c["start"]
            cps = c["chars"] / max(0.01, dur)
            gap = c["start"] - last_end
            reason = ""

            if dur <= self.min_dur: reason = "초단문"
            elif dur < self.hal_dur and c["chars"] > self.hal_chars: reason = "환각"
            elif cps > self.max_cps: reason = "CPS초과"
            elif gap < self.dedup_win and c["type"] == "repeat": reason = "앵무새"
            
            c["reason"] = reason
            c["is_skip"] = (dur < self.skip_dur) and not reason
            filtered.append(c)

            if not reason:
                last_text = c["text"]
                last_end = c["end"]

        survivors = [dict(b) for b in filtered if not b["reason"]]

        split_res = []
        limit = int(self.split_len * self.enforce_ratio)
        for b in survivors:
            if b["chars"] > limit:
                mid = (b["start"] + b["end"]) / 2
                half = len(b["text"]) // 2
                t1 = b["text"][:half] + ".."
                t2 = ".." + b["text"][half:]
                split_res.append({"id": b["id"], "start": b["start"], "end": mid, "text": t1, "chars": len(t1), "is_skip": b.get("is_skip")})
                split_res.append({"id": float(b["id"])+0.5, "start": mid, "end": b["end"], "text": t2, "chars": len(t2), "is_skip": b.get("is_skip")})
            else:
                split_res.append(b)

        merged_res = []
        i = 0
        while i < len(split_res):
            curr = split_res[i]
            if curr["chars"] < self.min_chars:
                merged = False
                if i > 0 and (curr["start"] - split_res[i-1]["end"]) < self.gap_break:
                    split_res[i-1]["end"] = curr["end"]
                    split_res[i-1]["text"] += " " + curr["text"]
                    split_res[i-1]["chars"] += curr["chars"]
                    merged = True
                    i += 1
                    continue
                if not merged and i < len(split_res)-1 and (split_res[i+1]["start"] - curr["end"]) < self.gap_break:
                    split_res[i+1]["start"] = curr["start"]
                    split_res[i+1]["text"] = curr["text"] + " " + split_res[i+1]["text"]
                    split_res[i+1]["chars"] += curr["chars"]
                    i += 1
                    continue
            merged_res.append(curr)
            i += 1

        final_res = [dict(b) for b in merged_res]
        for i in range(len(final_res)-1):
            c, n = final_res[i], final_res[i+1]
            gap = n["start"] - c["end"]
            if gap <= self.cont_thresh:
                c["end"] += gap * self.push_rate
                n["start"] -= gap * self.pull_rate
            else:
                ext = min(self.single_ext, gap/2)
                c["end"] += ext
                n["start"] -= ext
        if final_res:
            final_res[-1]["end"] += self.single_ext

        font_main = QFont("Arial", 11, QFont.Weight.Bold)
        font_small = QFont("Arial", 9)
        font_header = QFont("Arial", 12, QFont.Weight.Bold)

        def draw_box(y, start, end, color, txt, h_style=False, is_skip=False, is_final=False):
            x = offset_x + int(start * px_per_sec)
            w = max(int((end - start) * px_per_sec), 5)
            h = 38 
            
            # 💡 [추가] 마우스 호버 시 보여줄 툴팁 영역 저장
            box_rect = QRect(x, y, w, h)
            if h_style:
                self.hover_rects.append((box_rect, f"❌ [삭제됨] 필터 조건에 걸려 엔진에서 삭제된 자막입니다.\n원인: {txt.replace('❌ ', '')}"))
            elif is_skip:
                self.hover_rects.append((box_rect, "⏩ [AI 패스] 자막이 너무 짧아 환각 방지를 위해 AI를 거치지 않고 원본을 유지합니다."))
            elif is_final:
                self.hover_rects.append((box_rect, "✅ [최종결과] 분할/병합 및 간격 조절이 완료된 상태입니다."))
            else:
                self.hover_rects.append((box_rect, "🔵 [통과] AI 필터를 무사히 통과한 정상 자막입니다."))

            painter.setPen(Qt.PenStyle.NoPen)
            if h_style: 
                painter.setBrush(QBrush(QColor(color), Qt.BrushStyle.BDiagPattern))
            else:
                painter.setBrush(QBrush(QColor(color)))
            
            radius = 2 if is_final else 6
            painter.drawRoundedRect(x, y, w, h, radius, radius)
            
            if is_skip:
                painter.setPen(QPen(QColor("#FFCC00"), 3))
                painter.drawRoundedRect(x, y, w, h, radius, radius)
                
            painter.setPen(QColor("#FFFFFF" if not is_final else "#111111"))
            painter.setFont(font_main)
            
            fm = QFontMetrics(font_main)
            elided = fm.elidedText(txt, Qt.TextElideMode.ElideRight, w - 8)
            painter.drawText(x, y, w, h, Qt.AlignmentFlag.AlignCenter, elided)

        painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.SolidLine))
        painter.setFont(font_small)
        last_end = 0
        for b in blocks:
            x_s = offset_x + int(b["start"] * px_per_sec)
            x_e = offset_x + int(b["end"] * px_per_sec)
            
            if last_end > 0 and b["start"] > last_end:
                lx = offset_x + int(last_end * px_per_sec)
                painter.drawLine(lx, 25, x_s, 25)
                gap_sec = b["start"] - last_end
                painter.drawText(lx, 10, x_s - lx, 15, Qt.AlignmentFlag.AlignCenter, f"{gap_sec:.1f}s")
            
            painter.drawLine(x_s, 20, x_s, 30)
            painter.drawLine(x_e, 20, x_e, 30)
            painter.drawLine(x_s, 25, x_e, 25)
            painter.drawText(x_s, 10, x_e - x_s, 15, Qt.AlignmentFlag.AlignCenter, f"{b['end']-b['start']:.1f}s")
            last_end = b["end"]

        painter.setPen(QColor("#AAAAAA")); painter.setFont(font_header)
        painter.drawText(offset_x, 60, "1. 원본 음성 (정답 및 오답 믹스)")
        for b in blocks:
            draw_box(65, b["start"], b["end"], "#3A5A80", f"{b['text']} ({b['chars']}자)")

        painter.setPen(QColor("#AAAAAA")); painter.setFont(font_header)
        painter.drawText(offset_x, 155, "2. AI 필터 (환각, 중복, 랩핑, 노이즈 삭제)")
        for b in filtered:
            if b["reason"]: 
                draw_box(160, b["start"], b["end"], "#FF4444", f"❌ {b['reason']}", h_style=True)
            else:
                color = "#D35400" if b.get("is_skip") else "#4A90E2"
                draw_box(160, b["start"], b["end"], color, b["text"], is_skip=b.get("is_skip"))

        painter.setPen(QColor("#4AFF80")); painter.setFont(font_header)
        painter.drawText(offset_x, 250, "3. 최종 결과물 (타임라인 트랙 - 병합 및 간격 적용)")
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#222222")))
        painter.drawRect(offset_x, 255, int(max_time * px_per_sec), 38)
        
        for b in final_res:
            draw_box(255, b["start"], b["end"], "#4AFF80", b["text"], is_skip=b.get("is_skip"), is_final=True)

        painter.setPen(QPen(QColor("#666666"), 2, Qt.PenStyle.SolidLine))
        y_axis = 330
        painter.drawLine(offset_x, y_axis, int(offset_x + max_time * px_per_sec), y_axis)
        painter.setFont(font_small)
        painter.setPen(QColor("#AAAAAA"))
        for t in range(0, int(max_time) + 1, 2):
            tx = offset_x + int(t * px_per_sec)
            painter.drawLine(tx, y_axis - 4, tx, y_axis + 4)
            painter.drawText(tx - 15, y_axis + 8, 30, 20, Qt.AlignmentFlag.AlignCenter, f"{t}s")

    # 💡 [추가] 마우스 이동 감지하여 해당 영역의 툴팁 띄우기
    def mouseMoveEvent(self, event):
        pos = event.pos()
        for box_rect, text in self.hover_rects:
            if box_rect.contains(pos):
                QToolTip.showText(event.globalPosition().toPoint(), text, self)
                return
        QToolTip.hideText()
