# Version: 02.03.00
# Phase: PHASE1-B
"""
export_dialog.py  ─ SRT → 투명 자막 동영상 출력 (Qt 네이티브 렌더링 & 미리보기 복구본)
[추가] 투명도 확인을 위한 회색 체커보드 미리보기 배경 적용
[추가] 텍스트 배경 여백(마진) 조절 슬라이더 추가
[개선] iCloud 자동 복사 시 터미널에 상세 로그를 출력하여 실패 원인(보안 권한 등) 추적
[개선] iCloud 폴더 내에서 직접 작업 시 발생하는 SameFileError(자아분열) 방지 및 자동 덮어쓰기 적용
"""
import os, re, json, subprocess, tempfile, shutil, traceback

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QCheckBox, QColorDialog,
    QProgressDialog, QSlider, QGroupBox, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui  import QColor, QPixmap, QImage, QFont, QPainter, QPen, QBrush, QPainterPath, QFontMetrics
import config
from core.engine.subtitle_engine import save_srt
from logger import get_logger

# ── 설정 저장 로직 ──
_SETTINGS_PATH = os.path.join(config.DATASET_DIR, "user_settings.json")
def _load_es()->dict:
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH,"r",encoding="utf-8") as f:
                d = json.load(f).get("export_dialog",{})
                # Windows에서 iCloud 옵션 강제 비활성화
                if not getattr(config, "IS_MAC", False):
                    d["icloud"] = False
                return d
    except: pass
    return {}

def _save_es(d:dict):
    try:
        all_s={}
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH,"r",encoding="utf-8") as f: all_s=json.load(f)
        all_s["export_dialog"]=d
        with open(_SETTINGS_PATH,"w",encoding="utf-8") as f:
            json.dump(all_s,f,ensure_ascii=False,indent=2)
    except: pass

# ── 한글 지원 글꼴 ──
_KOREAN_FONTS = {
    "Apple SD Gothic Neo": "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "AppleGothic":         "/System/Library/Fonts/AppleGothic.ttf",
    "Nanum Gothic":        "/Library/Fonts/NanumGothic.ttf",
    "Nanum Gothic Bold":   "/Library/Fonts/NanumGothicBold.ttf",
    "Nanum Myeongjo":      "/Library/Fonts/NanumMyeongjo.ttf",
    "Noto Sans KR":        "/opt/homebrew/share/fonts/noto-sans-kr/NotoSansKR-Regular.ttf",
    # Pretendard 굵기별 개별 등록
    "Pretendard Regular":   "/Library/Fonts/Pretendard-Regular.ttf",
    "Pretendard Bold":      "/Library/Fonts/Pretendard-Bold.ttf",
    "Pretendard SemiBold":  "/Library/Fonts/Pretendard-SemiBold.ttf",
    "Pretendard Medium":    "/Library/Fonts/Pretendard-Medium.ttf",
    "Pretendard Light":     "/Library/Fonts/Pretendard-Light.ttf",
    "Pretendard ExtraBold": "/Library/Fonts/Pretendard-ExtraBold.ttf",
    "Pretendard Black":     "/Library/Fonts/Pretendard-Black.ttf",
    "Pretendard Thin":      "/Library/Fonts/Pretendard-Thin.ttf",
    "Pretendard ExtraLight":"/Library/Fonts/Pretendard-ExtraLight.ttf",
    "PretendardVariable":   "/Library/Fonts/PretendardVariable.ttf",
}

def _avail_fonts() -> dict:
    """하드코딩 경로 폰트 + QFontDatabase Korean WritingSystem으로 한글 폰트 자동 스캔."""
    result = {k: v for k, v in _KOREAN_FONTS.items() if os.path.exists(v)}
    try:
        from PyQt6.QtGui import QFontDatabase
        # [크PD] WritingSystem.Korean으로 한글 지원 폰트만 정확히 필터링
        for family in sorted(QFontDatabase.families(QFontDatabase.WritingSystem.Korean)):
            if family in result:
                continue
            if any(s in family for s in [".internal", "LastResort", "Apple Color Emoji"]):
                continue
            result[family] = ""   # 시스템 폰트: 경로 없어도 Qt가 직접 렌더링
    except Exception:
        pass
    return result

def _parse_srt(path:str)->list:
    try:
        with open(path,"r",encoding="utf-8") as f: content=f.read()
        pat=re.compile(
            r"\d+\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
            r"(.*?)(?=\n\d+\s*\n|\Z)",re.DOTALL)
        def ts(s):
            h,m,rest=s.split(":"); sec,ms=rest.split(",")
            return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
            
        # 💡 [여기서부터 수정됨] 기존에 저장된 투명 글자(\u200B)를 렌더링 전에 완벽하게 닦아냅니다!
        return [{"start":ts(m.group(1)),"end":ts(m.group(2)), "text":m.group(3).replace('\u200B', '').strip()}
                for m in pat.finditer(content) if m.group(3).replace('\u200B', '').strip()]
        # ----------------------------------
    except: return []

# ── PNG 렌더링 (네이티브 Qt 렌더링) ──
def _make_png(dest, text:str, width:int, height:int, style:dict):
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent) 
    
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    
    fs = style.get("font_size", 60)
    res_scale = style.get("res_scale", 1.0)
    
    font = QFont(style.get("font_family", "Apple SD Gothic Neo"))
    font.setPixelSize(fs)
    if style.get("bold", False):
        font.setWeight(QFont.Weight.Bold)
        
    painter.setFont(font)
    fm = QFontMetrics(font)
    
    lsp = style.get("line_spacing", 6)
    lines = text.split('\n')
    text_w = max((fm.horizontalAdvance(line) for line in lines), default=0)
    line_h = fm.height()
    text_h = (line_h * len(lines)) + (lsp * (len(lines) - 1))
    
    align = style.get("align", "center")
    if align == "left":   x = int(width * 0.04)
    elif align == "right":x = width - text_w - int(width * 0.04)
    else:                 x = (width - text_w) // 2
    y = (height - text_h) // 2
    
    # 1. 텍스트 배경 그리기
    if style.get("bg_rgba"):
        r, g, b, a = style["bg_rgba"]
        painter.setBrush(QBrush(QColor(r, g, b, a)))
        painter.setPen(Qt.PenStyle.NoPen)
        
        margin = style.get("bg_margin", int(18 * res_scale))
        pad_x = margin
        pad_y = max(4, margin // 2)
        radius = style.get("bg_radius", int(6 * res_scale))
        
        if style.get("bg_full_width"):
            painter.drawRect(QRectF(0, y - pad_y, width, text_h + pad_y * 2))
        else:
            painter.drawRoundedRect(QRectF(x - pad_x, y - pad_y, text_w + pad_x * 2, text_h + pad_y * 2), radius, radius)
            
    # 2. 그림자 그리기
    shd = style.get("shadow_rgba")
    sx = style.get("shadow_x", 3)
    sy = style.get("shadow_y", 3)
    
    if shd:
        sr, sg, sb, sa = shd
        painter.setPen(QColor(sr, sg, sb, sa))
        temp_y = y
        for line in lines:
            lw = fm.horizontalAdvance(line)
            if align == "left": lx = x
            elif align == "right": lx = x + text_w - lw
            else: lx = x + (text_w - lw) // 2
            painter.drawText(QPointF(lx + sx, temp_y + fm.ascent() + sy), line)
            temp_y += line_h + lsp
            
    # 3. 테두리 그리기
    bw = style.get("border_w", 0)
    bc = style.get("border_rgba")
    if bw > 0 and bc:
        br, bg, bb, ba = bc
        painter.setPen(QColor(br, bg, bb, ba))
        for dx in range(-bw, bw + 1):
            for dy in range(-bw, bw + 1):
                if dx == 0 and dy == 0: continue
                temp_y = y
                for line in lines:
                    lw = fm.horizontalAdvance(line)
                    if align == "left": lx = x
                    elif align == "right": lx = x + text_w - lw
                    else: lx = x + (text_w - lw) // 2
                    painter.drawText(QPointF(lx + dx, temp_y + dy + fm.ascent()), line)
                    temp_y += line_h + lsp
                    
    # 4. 텍스트 본체 그리기
    tc = style.get("txt_rgba")
    painter.setPen(QColor(tc[0], tc[1], tc[2], tc[3]))
    curr_y = y
    for line in lines:
        lw = fm.horizontalAdvance(line)
        if align == "left": lx = x
        elif align == "right": lx = x + text_w - lw
        else: lx = x + (text_w - lw) // 2
        painter.drawText(QPointF(lx, curr_y + fm.ascent()), line)
        curr_y += line_h + lsp
        
    painter.end()
    
    if dest:
        img.save(dest, "PNG")
    return img

class _RenderWorker(QThread):
    progress=pyqtSignal(int); done=pyqtSignal(bool,str)
    def __init__(self,p): super().__init__(); self.p=p
    def run(self):
        try: self._render()
        except: self.done.emit(False,traceback.format_exc())
    def _render(self):
        p=self.p; wd=tempfile.mkdtemp(prefix="sub_exp_")
        try:
            segs=p["segs"]; width,height=p["width"],p["height"]
            style=dict(p["style"]); output=p["output"]; total_dur=p["total_dur"]

            pts=sorted({0.0,total_dur}|{s["start"] for s in segs}|{s["end"] for s in segs})
            events=[]
            for i in range(len(pts)-1):
                t0,t1=pts[i],pts[i+1]
                if t1-t0<0.001: continue
                txt=next((s["text"] for s in segs if s["start"]<=t0 and s["end"]>=t1),None)
                events.append((t0,t1,txt))

            blank=os.path.join(wd,"blank.png")
            bg_img = QImage(width, height, QImage.Format.Format_ARGB32)
            bg_img.fill(Qt.GlobalColor.transparent)
            bg_img.save(blank, "PNG")
            
            txt_png={}
            unique={e[2] for e in events if e[2]}
            for i,text in enumerate(unique):
                p2=os.path.join(wd,f"s{i:04d}.png"); _make_png(p2,text,width,height,style)
                txt_png[text]=p2; self.progress.emit(int((i+1)/max(len(unique),1)*50))

            concat=os.path.join(wd,"c.txt")
            with open(concat,"w",encoding="utf-8") as f:
                for t0,t1,txt in events:
                    f.write(f"file '{txt_png.get(txt,blank) if txt else blank}'\nduration {t1-t0:.6f}\n")
                if events: f.write(f"file '{txt_png.get(events[-1][2],blank) if events[-1][2] else blank}'\n")
            
            enc=["-c:v","prores_ks","-profile:v","4444","-pix_fmt","yuva444p10le"]
            if p.get("fast", False):
                enc.extend(["-q:v", "15"])
                
            cmd=["ffmpeg","-y","-f","concat","-safe","0","-i",concat,"-vf",f"format=yuva444p10le"]+enc+[output]
            subprocess.run(cmd, capture_output=True)
            self.done.emit(True,output)
        finally: shutil.rmtree(wd,ignore_errors=True)

# ── 콤보박스 + +/- 버튼 헬퍼 ──
def _combo_pm(values:list, default, step:int=1):
    combo=QComboBox()
    combo.setEditable(True) 
    combo.addItems([str(v) for v in values])
    combo.setCurrentText(str(default))
    combo.setStyleSheet(f"background:{config.BG3};color:{config.FG};padding:3px;")
    combo.setFixedWidth(85)

    def go(delta):
        try:
            cur_val = int(combo.currentText())
            combo.setCurrentText(str(cur_val + (delta * step)))
        except: pass

    btn_s=f"background:{config.BG3};color:{config.FG};padding:2px 8px;font-weight:bold;border-radius:2px;"
    m=QPushButton("−"); m.setFixedWidth(28); m.setStyleSheet(btn_s)
    p2=QPushButton("+"); p2.setFixedWidth(28); p2.setStyleSheet(btn_s)
    
    m.clicked.connect(lambda *args, d=-1: go(d))
    p2.clicked.connect(lambda *args, d=1: go(d))
    
    h=QHBoxLayout(); h.setSpacing(2); h.setContentsMargins(0,0,0,0)
    h.addWidget(combo); h.addWidget(m); h.addWidget(p2); h.addStretch()
    return combo, h

class ExportDialog(QDialog):
    def __init__(self, segments, video_name, parent=None):
        super().__init__(parent)
        self.segments=segments; self.video_name=video_name
        self._srt_dir=os.path.expanduser("~")
        if parent and hasattr(parent,"media_path"):
            d=os.path.dirname(parent.media_path)
            if d and os.path.exists(d): self._srt_dir=d
        self._txt_c=QColor(config.ACCENT); self._bdr_c=QColor("#FFFFFF"); self._shd_c=QColor("#000000"); self._bg_c=QColor("#000000")
        self._fonts=_avail_fonts()
        self.setWindowTitle("자막 동영상 출력"); self.setMinimumWidth(560); self.setStyleSheet(f"background:{config.BG};color:{config.FG};font-size:13px;")
        self._build_ui(); self._load(); self._refresh_preview()

    def _build_ui(self):
        root=QVBoxLayout(self); root.setSpacing(8)
        tabs=QTabWidget(); tabs.setStyleSheet(f"QTabBar::tab{{background:{config.BG2};padding:8px 15px;}} QTabBar::tab:selected{{background:{config.BG3};}}")
        root.addWidget(tabs)

        def lrow(lbl,w,lw=130):
            h=QHBoxLayout(); lb=QLabel(lbl); lb.setFixedWidth(lw); h.addWidget(lb)
            if isinstance(w,QHBoxLayout): h.addLayout(w)
            else: h.addWidget(w)
            return h

        # ── 탭1: 출력 ──
        t1=QWidget(); l1=QVBoxLayout(t1); tabs.addTab(t1,"📁 출력")
        self.res_combo=QComboBox(); self.res_combo.addItems(["4K (3840px)","FHD (1920px)"]); l1.addLayout(lrow("가로 해상도:",self.res_combo))
        self.quality_combo=QComboBox(); self.quality_combo.addItems(["빠른 렌더링 (Proxy)","고품질 (ProRes 4444)"]); l1.addLayout(lrow("렌더링 품질:",self.quality_combo))
        
        # 💡 iCloud 자동 업로드 체크박스 추가
        self.icloud_chk = QCheckBox("렌더링 완료 후 iCloud로 자동 복사")
        self.icloud_chk.setStyleSheet("font-weight: bold; color: #4AFF80; padding-top: 8px;")
        l1.addWidget(self.icloud_chk)
        if not getattr(config, "IS_MAC", False):
            self.icloud_chk.setVisible(False)

        # ── 탭2: 텍스트 ──
        t2=QWidget(); l2=QVBoxLayout(t2); tabs.addTab(t2,"✏️ 텍스트")
        self.font_combo=QComboBox(); self.font_combo.addItems(sorted(self._fonts.keys())); self.font_combo.currentIndexChanged.connect(self._refresh_preview); l2.addLayout(lrow("글꼴:",self.font_combo))
        self.sz_combo,sz_h=_combo_pm([10,20,40,60,80,100],60); self.sz_combo.currentTextChanged.connect(self._refresh_preview); l2.addLayout(lrow("텍스트 크기:",sz_h))
        self.align_combo=QComboBox(); self.align_combo.addItems(["가운데","왼쪽","오른쪽"]); self.align_combo.currentIndexChanged.connect(self._refresh_preview); l2.addLayout(lrow("텍스트 정렬:",self.align_combo))
        self.lsp_combo,lsp_h=_combo_pm(list(range(0,51)),6); self.lsp_combo.currentTextChanged.connect(self._refresh_preview); l2.addLayout(lrow("줄 간격:",lsp_h))
        self.bold_chk=QCheckBox("굵게 (Bold)"); self.bold_chk.setChecked(True); self.bold_chk.toggled.connect(self._refresh_preview); l2.addWidget(self.bold_chk)
        self._txt_btn=QPushButton(); self._txt_btn.clicked.connect(lambda *a: self._pick("txt")); l2.addLayout(lrow("텍스트 색상:",self._txt_btn))
        l2.addStretch()

        # ── 탭3: 효과 ──
        t3=QWidget(); l3=QVBoxLayout(t3); tabs.addTab(t3,"💫 효과")
        self.no_bdr_chk=QCheckBox("테두리 없음"); self.no_bdr_chk.toggled.connect(self._refresh_preview); l3.addWidget(self.no_bdr_chk)
        self._bdr_btn=QPushButton(); self._cb(self._bdr_btn, self._bdr_c); self._bdr_btn.clicked.connect(lambda *a: self._pick("bdr")); l3.addLayout(lrow("테두리 색상:",self._bdr_btn))
        self.bdr_w_combo,bdr_h=_combo_pm(list(range(0,21)),2); self.bdr_w_combo.currentTextChanged.connect(self._refresh_preview); l3.addLayout(lrow("테두리 두께:",bdr_h))
        
        self.shd_chk=QCheckBox("그림자 활성화"); self.shd_chk.toggled.connect(self._refresh_preview); l3.addWidget(self.shd_chk)
        self._shd_btn=QPushButton(); self._cb(self._shd_btn, self._shd_c); self._shd_btn.clicked.connect(lambda *a: self._pick("shd")); l3.addLayout(lrow("그림자 색상:",self._shd_btn))
        self.shdx_combo,shdx_h=_combo_pm(list(range(-20,21)),3); self.shdx_combo.currentTextChanged.connect(self._refresh_preview); l3.addLayout(lrow("그림자 X:",shdx_h))
        self.shdy_combo,shdy_h=_combo_pm(list(range(-20,21)),3); self.shdy_combo.currentTextChanged.connect(self._refresh_preview); l3.addLayout(lrow("그림자 Y:",shdy_h))
        l3.addStretch()

        # ── 탭4: 배경 ──
        t4=QWidget(); l4=QVBoxLayout(t4); tabs.addTab(t4,"🎨 배경")
        self.bg_chk=QCheckBox("배경 사용"); self.bg_chk.toggled.connect(self._refresh_preview); l4.addWidget(self.bg_chk)
        self.bg_full_chk=QCheckBox("전체 너비 배경"); self.bg_full_chk.toggled.connect(self._refresh_preview); l4.addWidget(self.bg_full_chk)
        self.bg_col_btn=QPushButton(); self._cb(self.bg_col_btn, self._bg_c); self.bg_col_btn.clicked.connect(lambda *a: self._pick("bg")); l4.addLayout(lrow("배경 색상:",self.bg_col_btn))
        
        self.bg_rd_sl=QSlider(Qt.Orientation.Horizontal); self.bg_rd_sl.setRange(0,80); self.bg_rd_sl.setValue(10)
        self.bg_rd_lbl=QLabel("10px"); self.bg_rd_sl.valueChanged.connect(lambda v: (self.bg_rd_lbl.setText(f"{v}px"), self._refresh_preview()))
        rd_h=QHBoxLayout(); rd_h.addWidget(self.bg_rd_sl); rd_h.addWidget(self.bg_rd_lbl); l4.addLayout(lrow("배경 라운드:",rd_h))
        
        self.bg_mg_sl=QSlider(Qt.Orientation.Horizontal); self.bg_mg_sl.setRange(0,100); self.bg_mg_sl.setValue(18)
        self.bg_mg_lbl=QLabel("18px"); self.bg_mg_sl.valueChanged.connect(lambda v: (self.bg_mg_lbl.setText(f"{v}px"), self._refresh_preview()))
        mg_h=QHBoxLayout(); mg_h.addWidget(self.bg_mg_sl); mg_h.addWidget(self.bg_mg_lbl); l4.addLayout(lrow("배경 여백(마진):",mg_h))
        
        self.bg_op_sl=QSlider(Qt.Orientation.Horizontal); self.bg_op_sl.setRange(0,100); self.bg_op_sl.setValue(50)
        self.bg_op_lbl=QLabel("50%"); self.bg_op_sl.valueChanged.connect(lambda v: (self.bg_op_lbl.setText(f"{v}%"), self._refresh_preview()))
        op_h=QHBoxLayout(); op_h.addWidget(self.bg_op_sl); op_h.addWidget(self.bg_op_lbl); l4.addLayout(lrow("배경 투명도:",op_h))
        l4.addStretch()

        # ── 미리보기 ──
        grp=QGroupBox("미리보기 (회색 체커보드 = 투명 영역)"); gv=QVBoxLayout(grp); gv.setSpacing(6)
        
        line_row=QHBoxLayout()
        line_row.addWidget(QLabel("미리보기 모드:")); 
        self.prev_1_btn=QPushButton("1줄"); self.prev_2_btn=QPushButton("2줄")
        for b in [self.prev_1_btn, self.prev_2_btn]:
            b.setCheckable(True); b.setFixedWidth(60)
            b.setStyleSheet(f"QPushButton{{background:{config.BG3};padding:4px;}} QPushButton:checked{{background:{config.ACCENT};color:#000;}}")
        self.prev_1_btn.setChecked(True)
        self.prev_1_btn.clicked.connect(self._on_prev1); self.prev_2_btn.clicked.connect(self._on_prev2)
        line_row.addWidget(self.prev_1_btn); line_row.addWidget(self.prev_2_btn); line_row.addStretch()
        gv.addLayout(line_row)

        self.prev_lbl=QLabel(); self.prev_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_lbl.setMinimumHeight(120); self.prev_lbl.setStyleSheet("background:#222;border-radius:4px;"); gv.addWidget(self.prev_lbl)
        root.addWidget(grp)

        # [ui/export_dialog.py] _build_ui 함수 맨 아래 버튼부 교체
        br = QHBoxLayout()

        # 1. 저장 버튼 (상세설정창의 Cyan 컬러 & 이모지 적용)
        btn_save = QPushButton("💾 저장")
        btn_save.setStyleSheet("background-color: #4fc3f7; color: #000000; padding: 8px 16px; font-size: 13px; font-weight: bold; border-radius: 4px;")
        btn_save.setToolTip("설정 저장 (창 유지)")
        btn_save.clicked.connect(self._save)
        br.addWidget(btn_save)

        # 💡 상세설정창처럼 왼쪽(저장)과 오른쪽(취소/확인)을 분리하는 투명한 여백 추가
        br.addStretch()

        # 2. 취소 버튼 (상세설정창의 Dark Gray 컬러)
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background-color: #444444; color: #FFFFFF; padding: 8px 16px; font-size: 13px; font-weight: bold; border-radius: 4px;")
        btn_cancel.setToolTip("저장하지 않고 닫기")
        btn_cancel.clicked.connect(self.reject)
        br.addWidget(btn_cancel)

        # 3. 확인 버튼 (상세설정창의 Bright Green 컬러)
        btn_ok = QPushButton("확인")
        btn_ok.setStyleSheet("background-color: #4AFF80; color: #000000; padding: 8px 16px; font-size: 13px; font-weight: bold; border-radius: 4px;")
        btn_ok.setToolTip("설정 저장 후 닫기")
        btn_ok.clicked.connect(self._ok)
        br.addWidget(btn_ok)

        # 4. 렌더링 시작 버튼 (강조를 위해 높이와 여백을 살짝 더 줌)
        self.render_btn = QPushButton("🚀 렌더링 시작")
        self.render_btn.setFixedHeight(36)
        self.render_btn.setStyleSheet(f"background-color: {config.ACCENT}; color: #000000; padding: 8px 24px; font-size: 14px; font-weight: bold; border-radius: 4px;")
        self.render_btn.clicked.connect(self._render)
        br.addWidget(self.render_btn)

        root.addLayout(br)

    def _on_prev1(self): self.prev_2_btn.setChecked(False); self.prev_1_btn.setChecked(True); self._refresh_preview()
    def _on_prev2(self): self.prev_1_btn.setChecked(False); self.prev_2_btn.setChecked(True); self._refresh_preview()

    def _cb(self,btn,c): btn.setStyleSheet(f"background:{c.name()};color:{'#000' if c.lightness()>128 else '#fff'};padding:5px;border:1px solid #555;"); btn.setText(c.name().upper())
    
    def _pick(self,w):
        cur={"txt":self._txt_c,"bdr":self._bdr_c,"shd":self._shd_c,"bg":self._bg_c}[w]
        c=QColorDialog.getColor(cur,self)
        if c.isValid():
            if w=="txt": self._txt_c=c; self._cb(self._txt_btn,c)
            elif w=="bdr": self._bdr_c=c; self._cb(self._bdr_btn,c)
            elif w=="shd": self._shd_c=c; self._cb(self._shd_btn,c)
            else: self._bg_c=c; self._cb(self.bg_col_btn,c)
            self._refresh_preview()

    def _style(self, font_size=None, effect_scale=1.0):
        try: fs = font_size or int(self.sz_combo.currentText())
        except: fs = 60
        am={"가운데":"center","왼쪽":"left","오른쪽":"right"}
        bg_rgba = (self._bg_c.red(),self._bg_c.green(),self._bg_c.blue(),int(self.bg_op_sl.value()*2.55)) if self.bg_chk.isChecked() else None
        
        try: bdr_w = int(self.bdr_w_combo.currentText() or 2)
        except: bdr_w = 2
        bdr_w = max(1, int(bdr_w * effect_scale)) if bdr_w > 0 and not self.no_bdr_chk.isChecked() else 0

        try: lsp = int(self.lsp_combo.currentText() or 6)
        except: lsp = 6
        lsp = int(lsp * effect_scale)

        try: shdx = int(self.shdx_combo.currentText() or 3)
        except: shdx = 3
        shdx = int(shdx * effect_scale)
        
        try: shdy = int(self.shdy_combo.currentText() or 3)
        except: shdy = 3
        shdy = int(shdy * effect_scale)
        
        bg_radius = int(self.bg_rd_sl.value() * effect_scale)
        bg_margin = int(self.bg_mg_sl.value() * effect_scale)

        return dict(
            font_path=self._fonts.get(self.font_combo.currentText(),""), 
            font_family=self.font_combo.currentText(),
            font_size=fs, res_scale=effect_scale, bold=self.bold_chk.isChecked(),
            align=am.get(self.align_combo.currentText(),"center"),
            line_spacing=lsp,
            txt_rgba=(self._txt_c.red(),self._txt_c.green(),self._txt_c.blue(),255),
            border_w=bdr_w,
            border_rgba=(self._bdr_c.red(),self._bdr_c.green(),self._bdr_c.blue(),255),
            shadow_rgba=(self._shd_c.red(),self._shd_c.green(),self._shd_c.blue(),200) if self.shd_chk.isChecked() else None,
            shadow_x=shdx, shadow_y=shdy,
            bg_rgba=bg_rgba, bg_radius=bg_radius, bg_margin=bg_margin, bg_full_width=self.bg_full_chk.isChecked()
        )

    def _refresh_preview(self):
        try:
            pw = max(self.prev_lbl.width(), 480)
            sample = "소설가유모씨 채널 ABC 123\n이것은 2줄 자막 미리보기입니다" if self.prev_2_btn.isChecked() else "소설가유모씨 채널 ABC 123 자막 미리보기"
            try: real_fs = int(self.sz_combo.currentText())
            except: real_fs = 60
            
            scale = min(1.0, 90 / (real_fs * 2.5))
            ps = max(8, int(real_fs * scale))
            ph = max(110, int(ps * 4.5))
            
            st = self._style(font_size=ps, effect_scale=scale)
            
            text_img = _make_png(None, sample, pw, ph, st)
            
            bg_img = QImage(pw, ph, QImage.Format.Format_ARGB32)
            bg_img.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(bg_img)
            
            sq = 15
            for r in range(0, ph, sq):
                for c in range(0, pw, sq):
                    color = QColor("#888888") if (r//sq + c//sq) % 2 == 0 else QColor("#666666")
                    painter.fillRect(c, r, sq, sq, color)
                    
            painter.drawImage(0, 0, text_img)
            painter.end()
            
            self.prev_lbl.setPixmap(QPixmap.fromImage(bg_img))
        except Exception as e:
            self.prev_lbl.setText(f"미리보기 오류: {e}")

    def _collect(self)->dict:
        return dict(
            res=self.res_combo.currentText(), quality=self.quality_combo.currentText(), 
            font=self.font_combo.currentText(), size=self.sz_combo.currentText(),
            align=self.align_combo.currentText(), lsp=self.lsp_combo.currentText(),
            txt_c=self._txt_c.name(), no_bdr=self.no_bdr_chk.isChecked(), bdr_c=self._bdr_c.name(), bdr_w=self.bdr_w_combo.currentText(),
            shadow=self.shd_chk.isChecked(), shd_c=self._shd_c.name(), shdx=self.shdx_combo.currentText(), shdy=self.shdy_combo.currentText(),
            bg=self.bg_chk.isChecked(), bg_full=self.bg_full_chk.isChecked(), bg_c=self._bg_c.name(), 
            bg_op=self.bg_op_sl.value(), bg_radius=self.bg_rd_sl.value(), bg_margin=self.bg_mg_sl.value(), bold=self.bold_chk.isChecked(),
            icloud=self.icloud_chk.isChecked()
        )

    def _save(self):
        """설정을 user_settings.json에 저장 (창 유지)."""
        try:
            _save_es(self._collect())
            orig = self.render_btn.text()
            self.render_btn.setText("✅ 저장됨")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.render_btn.setText(orig))
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 오류:\n{e}")

    def _ok(self):
        """설정 저장 후 창 닫기."""
        try:
            _save_es(self._collect())
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 오류:\n{e}")
        self.accept()

    def _load(self):
        s=_load_es()
        if not s: return
        try:
            self.res_combo.setCurrentText(s.get("res","4K (3840px)")); self.quality_combo.setCurrentText(s.get("quality","빠른 렌더링 (Proxy)"))
            self.font_combo.setCurrentText(s.get("font","Apple SD Gothic Neo")); self.sz_combo.setCurrentText(str(s.get("size",60)))
            self.align_combo.setCurrentText(s.get("align","가운데")); self.lsp_combo.setCurrentText(str(s.get("lsp",6)))
            self._txt_c=QColor(s.get("txt_c","#FFFFFF")); self._cb(self._txt_btn,self._txt_c)
            self.no_bdr_chk.setChecked(s.get("no_bdr",False)); self._bdr_c=QColor(s.get("bdr_c","#FFFFFF")); self._cb(self._bdr_btn,self._bdr_c)
            self.bdr_w_combo.setCurrentText(str(s.get("bdr_w",2)))
            self.shd_chk.setChecked(s.get("shadow",False)); self._shd_c=QColor(s.get("shd_c","#000000")); self._cb(self._shd_btn,self._shd_c)
            self.shdx_combo.setCurrentText(str(s.get("shdx",3))); self.shdy_combo.setCurrentText(str(s.get("shdy",3)))
            self.bg_chk.setChecked(s.get("bg",False)); self.bg_full_chk.setChecked(s.get("bg_full",False))
            self._bg_c=QColor(s.get("bg_c","#000000")); self._cb(self.bg_col_btn,self._bg_c)
            self.bg_op_sl.setValue(s.get("bg_op",50)); self.bg_rd_sl.setValue(s.get("bg_radius",10)); self.bg_mg_sl.setValue(s.get("bg_margin",18)); self.bold_chk.setChecked(s.get("bold",True))
            self.icloud_chk.setChecked(s.get("icloud", False))
        except: pass

    def _render(self):
        tmp=tempfile.NamedTemporaryFile(suffix=".srt",delete=False,mode="w",encoding="utf-8"); tmp.close()
        save_srt(self.segments,tmp.name,apply_offset=False); segs=_parse_srt(tmp.name)
        try: os.remove(tmp.name)
        except: pass
        if not segs: return
        _save_es(self._collect())
        
        safe_v = re.sub(r'[\\/:*?"<>|]', '_', self.video_name)
        out_p = os.path.join(self._srt_dir, f"{safe_v}_자막소스.mov")
        
        width=3840 if "4K" in self.res_combo.currentText() else 1920
        fs=int(self.sz_combo.currentText()); res_scale=4.0 if width==3840 else 2.0
        scaled_fs=int(fs*res_scale); height=int(scaled_fs*3.5); height+=height%2
        st=self._style(font_size=scaled_fs, effect_scale=res_scale)
        
        self._prog=QProgressDialog("렌더링 중...",None,0,100,self); self._prog.show()
        self._worker=_RenderWorker(dict(segs=segs,width=width,height=height,style=st,output=out_p,total_dur=max(s["end"] for s in segs)+0.5,fast="빠른" in self.quality_combo.currentText()))
        self._worker.progress.connect(self._prog.setValue); self._worker.done.connect(self._on_done); self._worker.start()

    # 💡 [핵심] iCloud 자동 업로드 처리 로직 및 터미널 로그 출력
    def _on_done(self, ok, msg):
        self._prog.close()
        if ok:
            get_logger().log(f"✅ 로컬 렌더링 완료: {msg}")
            result_msg = f"로컬 저장완료:\n{msg}"
            
            if self.icloud_chk.isChecked():
                get_logger().log("☁️ iCloud 자동 복사를 시작합니다...")
                try:
                    dest_dir = getattr(config, "ICLOUD_DROPZONE", os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT"))
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_file = os.path.join(dest_dir, os.path.basename(msg))
                    
                    # 💡 [핵심 교정] 출발지(현재 로컬 경로)와 목적지(iCloud 폴더)가 완전히 같으면 복사 생략!
                    if os.path.abspath(msg) != os.path.abspath(dest_file):
                        shutil.copy2(msg, dest_file) # 이름이 같으면 기본적으로 덮어쓰기 작동!
                        get_logger().log(f"✅ iCloud 복사(덮어쓰기) 성공: {dest_file}")
                    else:
                        get_logger().log(f"ℹ️ 이미 iCloud 드롭존 내에서 작업 중입니다. (복사 생략)")
                        
                    result_msg += f"\n\n☁️ iCloud 백업 완료:\n{dest_dir}"
                except Exception as e:
                    err_msg = f"⚠️ iCloud 복사 실패 (권한 또는 용량 문제): {e}"
                    get_logger().log(err_msg)
                    result_msg += f"\n\n{err_msg}"
            else:
                get_logger().log("ℹ️ iCloud 자동 복사 옵션이 꺼져있어 로컬에만 저장되었습니다.")

            QMessageBox.information(self, "완료", result_msg)
            self.accept()
        else: 
            get_logger().log(f"❌ 렌더링 실패: {msg}")
            QMessageBox.critical(self, "실패", msg)