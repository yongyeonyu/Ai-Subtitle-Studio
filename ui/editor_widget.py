# Version: 01.00.06
"""
ui/editor_widget.py
[v01.00.06 수정사항]
- btn_exit (종료 버튼) 제거 — 이전 버튼으로 기능 이전
- engine_lbl 폰트 13px → 11px (-2pt)
- 하단 버튼 전체 min-height: 40px 추가 (이전/다음 높이 통일)
"""
import re, os, sys, json, atexit, threading, shutil, time
from ui.undo_manager import UndoManager

def _mac_safe_exit():
    try: sys.stdout.flush(); sys.stderr.flush()
    except: pass
    os._exit(0)
atexit.register(_mac_safe_exit)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QPushButton, QLabel, QSizePolicy, QMessageBox, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QSettings
from PyQt6.QtGui import QKeySequence, QShortcut, QColor, QTextCursor, QIcon, QPixmap, QPainter
from PyQt6.QtMultimedia import QMediaPlayer

import config
from logger import get_logger
from core.data_manager import (
    load_settings as _dm_load_settings, save_settings as _dm_save_settings,
    load_corrections as _dm_load_corrections, save_correction as _dm_save_correction,
    cleanup_rules as _dm_cleanup_rules, load_subtitle_rules as _dm_load_rules
)
from core.state_manager import SubtitleStateManager
from ui.timeline_widget import TimelineWidget
from ui.editor_popup_qt import EditorPopup
from ui.video_player_widget import VideoPlayerWidget
from ui.subtitle_text_edit import SubtitleTextEdit, SubtitleHighlighter, SubtitleBlockData
from ui.editor_pipeline import EditorPipelineMixin
from ui.editor_segments import EditorSegmentsMixin
from ui.editor_timeline_video import EditorTimelineVideoMixin

DATASET_DIR   = "dataset"
SETTINGS_FILE = os.path.join(DATASET_DIR, "user_settings.json")


class EditorWidget(EditorPipelineMixin, EditorSegmentsMixin, EditorTimelineVideoMixin, QWidget):
    sig_start     = pyqtSignal()
    sig_prev      = pyqtSignal()
    sig_save      = pyqtSignal(list)
    sig_auto_save = pyqtSignal(list)
    sig_exit      = pyqtSignal(list)
    sig_next      = pyqtSignal(list)

    _JUNK_TS_RE               = re.compile(r'[\[{(<\[【（《]\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*[\]})>\]】）》]\s*')
    _JUNK_NO_BRACKET_3PART    = re.compile(r'(?<!\S)\d{1,3}[:\.]\d{2}[:\.]\d{2,3}(?!\S)')
    _JUNK_NO_BRACKET_3PART_END= re.compile(r'\d{1,3}[:\.]\d{2}[:\.]\d{2,3}\s*$')
    _JUNK_START_RE            = re.compile(r'^\s*\d{1,3}[:\.]\d{2}(?:[:\.]\d+)?\s+')
    _auto_start_next = False

    def __init__(self, video_name: str, segments: list[dict], media_path: str | None = None, parent=None):
        super().__init__(parent)
        self._has_auto_started = False
        self._process_start_time = None
        self._vid_wait_cnt = 0
        self._is_initial_load = False
        self._backend_finished = False

        self.video_name     = video_name
        self.media_path     = media_path
        self.corrections    = _dm_load_corrections()
        self.subtitle_rules = _dm_load_rules()
        self.settings       = _dm_load_settings()
        self.selected_model = self.settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

        self.sm = SubtitleStateManager()
        self.sm.current_file = media_path or ""    # ✅ 여기로 이동
        self.sm.sig_ui_update.connect(self._on_state_machine_update)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._on_auto_save)
        self._auto_save_timer.start(30000)

        self._status_anim_idx = 0
        self._status_frames = {
            SubtitleStateManager.ST_EDITING:  ["✏️ 편집중",        "📝 편집중",        "✍️ 편집중"],
            SubtitleStateManager.ST_AUTOSAVE: ["⏳ 자동 저장 중..", "🔄 자동 저장 중..", "⌛ 자동 저장 중.."],
            SubtitleStateManager.ST_SAVED:    ["💾 저장완료",       "✨ 저장완료",       "✅ 저장완료"],
            SubtitleStateManager.ST_IDLE:     ["💤 대기중",         "☕ 대기중"],
        }

        self._status_anim_timer = QTimer(self)
        self._status_anim_timer.timeout.connect(self._animate_status)
        self._status_anim_timer.start(400)

        self.is_batch_mode = False
        self.is_auto_start = False  # 파이프라인 연동용 변수
        self._active_seg_start: float | None = None
        self._sync_lock          = False
        self._segment_queue: list[dict] = []
        self._inline_updating    = False

        self._queue_timer    = QTimer(); self._queue_timer.setSingleShot(True);    self._queue_timer.timeout.connect(self._flush_queue)
        self._timeline_timer = QTimer(); self._timeline_timer.setSingleShot(True); self._timeline_timer.timeout.connect(self._redraw_timeline)
        self._nav_timer      = QTimer(); self._nav_timer.setSingleShot(True)

        self.status_lbl = QLabel("대기 중...")
        self.engine_lbl = QLabel()
        self._update_engine_label_text()

        self._spinner_timer  = QTimer(); self._spinner_timer.setInterval(400); self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_frames = ["⏳", "⌛"]
        self._spinner_idx    = 0

        self.editor_popup = EditorPopup(self)
        
        # 💡 [핵심 복구] 이 줄이 지워져서 화면이 안 나왔던 것입니다!
        self._build_ui()   
        
        self._undo_mgr = UndoManager(self)

        self._highlighter = SubtitleHighlighter(self.text_edit.document())
        self._update_highlighter_colors()
        self.text_edit.setUndoRedoEnabled(True)

        # 단축키
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.undo_shortcut.activated.connect(self._route_undo)

        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_shortcut.activated.connect(self._route_redo)

        if not segments and media_path:
            base_path = os.path.splitext(media_path)[0]; srt_guess = base_path + ".srt"
            if not os.path.exists(srt_guess) and video_name.endswith('.srt'):
                srt_guess = os.path.join(os.path.dirname(media_path), video_name)
            if os.path.exists(srt_guess):
                segments = self._fallback_parse_srt(srt_guess)

        self._is_initial_load = True if segments else False
        if segments:
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
                self.timeline.canvas.segments = [dict(s) for s in segments]
            self.append_segments(segments)

        if media_path:
            QTimer.singleShot(200, lambda: self._load_video(media_path))

        self._playhead_timer = QTimer()
        self._playhead_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._playhead_timer.setInterval(33)   # [크PD] 10ms(100fps) → 33ms(30fps)
        self._playhead_timer.timeout.connect(self._sync_playhead)
        self._playhead_timer.start()

        self.space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.space_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.space_shortcut.activated.connect(self._on_space_pressed)

        self.text_edit.esc_pressed.connect(self._toggle_focus)
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.esc_shortcut.activated.connect(self._toggle_focus)

        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.save_shortcut.activated.connect(self._on_save)

        self.split_shortcut = QShortcut(QKeySequence("Ctrl+X"), self)
        self.split_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.split_shortcut.activated.connect(self._split_at_playhead_or_cut)

        self.start_shortcut = QShortcut(QKeySequence("Ctrl+["), self)
        self.start_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.start_shortcut.activated.connect(self._set_segment_start_to_playhead)

        self.end_shortcut = QShortcut(QKeySequence("Ctrl+]"), self)
        self.end_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.end_shortcut.activated.connect(self._set_segment_end_to_playhead)

        QTimer.singleShot(500, self._hook_backend_signals)
        if segments: self.sm.complete_ai()
        else:        self.sm.init_state()

        if EditorWidget._auto_start_next:
            EditorWidget._auto_start_next = False
            QTimer.singleShot(1000, self._trigger_auto_start)
    # ---------------------------------------------------------
    # 상태 머신 핸들러
    # ---------------------------------------------------------
    def _on_state_machine_update(self, mode, state, is_locked, is_dirty, lbl_txt, btn_txt, btn_en):
        self.current_mode      = mode
        self.current_state     = state
        self._is_ai_processing = is_locked
        self._is_dirty         = is_dirty

        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(lbl_txt)
        if hasattr(self, 'btn_start'):
            self.btn_start.setText(btn_txt)
            self.btn_start.setEnabled(btn_en)
        if hasattr(self, 'text_edit'):
            self.text_edit.setReadOnly(is_locked)
            self.text_edit.setStyleSheet(
                "QTextEdit { background-color: #1a1a1a; color: #888888; }" if is_locked else ""
            )

    def _animate_status(self):
        if self.sm.is_locked: return
        frames = self._status_frames.get(self.sm.state)
        if frames:
            self._status_anim_idx += 1
            self.sm.set_custom_status(frames[self._status_anim_idx % len(frames)])

    def _on_text_edited(self):
        if getattr(self, '_sync_lock', False): return
        if getattr(self, '_inline_updating', False): return
        if self.sm.is_locked: return
        if not hasattr(self, '_app_start_time'): self._app_start_time = time.time()
        if time.time() - self._app_start_time < 1.0: return
        self.sm.start_editing()

    def _on_auto_save(self):
        if self.sm.is_locked: return
        if self.sm.is_dirty:
            self.sig_auto_save.emit(self._get_current_segments())
            self.sm.start_autosave()
            QTimer.singleShot(2000, self.sm.complete_save)

    # ---------------------------------------------------------
    # UI 빌드
    # ---------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background: {config.BG3}; width: 4px; }}")
        editor_wrap = QWidget(); editor_wrap.setStyleSheet(f"background: {config.BG3}; border-radius: 4px;")
        ew_layout   = QVBoxLayout(editor_wrap); ew_layout.setContentsMargins(2, 2, 2, 2)

        self.text_edit = SubtitleTextEdit()
        self.text_edit._parent_widget = self
        self.text_edit.enter_pressed.connect(self._on_enter_pressed)
        self.text_edit.backspace_merged.connect(self._on_backspace_merged)
        self.text_edit.cursor_moved.connect(self._on_cursor_moved)
        self.text_edit.esc_pressed.connect(self._on_esc_pressed)
        self.text_edit.word_selected.connect(self._trigger_editor_popup)
        self.text_edit.tab_pressed.connect(self._trigger_magnet)
        self.text_edit.selectionChanged.connect(self._on_selection_changed)
        self.text_edit.document().contentsChanged.connect(self._on_text_edited)
        self.text_edit.document().contentsChanged.connect(self._schedule_timeline)
        self.text_edit.timestamp_clicked.connect(self._on_timeline_seg_clicked)
        self.text_edit.timestamp_deleted.connect(self._on_seg_to_gap)
        self.text_edit.speaker_circle_clicked.connect(self._show_speaker_circle_menu)
        self.text_edit.speaker_circle_dropped.connect(self._on_speaker_circle_dropped)

        ew_layout.addWidget(self.text_edit)
        self.splitter.addWidget(editor_wrap)
        self.video_player = VideoPlayerWidget()
        self.splitter.addWidget(self.video_player)
        self.splitter.setStretchFactor(0, 40); self.splitter.setStretchFactor(1, 60)
        self.splitter.setCollapsible(0, False); self.splitter.setCollapsible(1, False)
        root.addWidget(self.splitter, stretch=1)

        self.timeline = TimelineWidget()
        self.timeline.setStyleSheet(f"background: {config.BG3}; border-radius: 4px;")
        if hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.show_waveform = True
            self.timeline.canvas.update()

        # ✅ 여기 딱 한 번만 connect
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'sig_split_request'):
            self.timeline.canvas.sig_split_request.connect(self.split_segment_with_text)

        self.timeline.seg_clicked.connect(self._on_timeline_seg_clicked)
        self.timeline.seg_double_clicked.connect(self._on_timeline_seg_double_clicked)
        self.timeline.scrub_sec.connect(self._on_scrub)

        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'seg_right_clicked'):
            self.timeline.canvas.seg_right_clicked.connect(self._on_timeline_seg_right_clicked)

        if hasattr(self.timeline, 'seg_time_changed'): self.timeline.seg_time_changed.connect(self._on_seg_time_changed)
        if hasattr(self.timeline, 'seg_to_gap'):       self.timeline.seg_to_gap.connect(self._on_seg_to_gap)
        if hasattr(self.timeline, 'gap_activated'):    self.timeline.gap_activated.connect(self._on_gap_activated)
        if hasattr(self.timeline, 'gap_to_segs'):      self.timeline.gap_to_segs.connect(self._on_gap_to_segs)
        if hasattr(self.timeline, 'drag_started'):     self.timeline.drag_started.connect(self._on_drag_started)
        if hasattr(self.timeline, 'drag_finished'):    self.timeline.drag_finished.connect(self._on_drag_finished)
        if hasattr(self.timeline, 'step_frame'):       self.timeline.step_frame.connect(self._on_step_frame)
        if hasattr(self.timeline, 'lock_chk'):         self.timeline.lock_chk.toggled.connect(self._on_lock_changed)
        if hasattr(self.timeline, 'sig_inline_text_changed'): self.timeline.sig_inline_text_changed.connect(self._on_inline_text_changed)
        if hasattr(self.timeline, 'sig_editing_mode'):        self.timeline.sig_editing_mode.connect(self._on_seg_editing_mode)
        if hasattr(self.timeline, 'playhead_menu_requested'):
            self.timeline.playhead_menu_requested.connect(self._show_playhead_menu)

        root.addWidget(self.timeline)
        root.addWidget(self._build_buttons())

    def _on_inline_text_changed(self, line_num: int, new_text: str):
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid(): return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return
        if block.text() == new_text: return
        self._inline_updating = True
        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new_text)
        cur.block().setUserData(SubtitleBlockData(ud.spk_id, ud.start_sec, ud.is_gap))
        cur.endEditBlock()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._inline_updating = False
        self._schedule_timeline()

    def _on_lock_changed(self, locked: bool):
        self.text_edit.setReadOnly(locked)
        self.text_edit.setStyleSheet("background: #1a1a1a; color: #888888;" if locked else "")

    def _build_buttons(self) -> QWidget:
        w = QWidget(); w.setFixedHeight(65)
        grid = QGridLayout(w); grid.setContentsMargins(10, 2, 10, 2)

        # ── 좌측 ──
        left_w    = QWidget(); left_vbox = QVBoxLayout(left_w); left_vbox.setContentsMargins(0, 0, 0, 0); left_vbox.setSpacing(5)
        self.status_lbl.setStyleSheet(f"color: {config.YELLOW}; font-size: 13px; font-weight: bold;")
        left_vbox.addWidget(self.status_lbl, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        btn_row = QHBoxLayout(); btn_row.setSpacing(5)
        self.btn_ai  = QPushButton("⚙️ AI")
        self.btn_adv = QPushButton("🛠️ 상세설정")
        self.btn_spk = QPushButton("🗣️ 화자")
        self.btn_gap = QPushButton("⏱️ 간격")
        self.btn_vid = QPushButton("🎬 비디오")
        self._top_btns = [
            (self.btn_ai,  "⚙️ AI",      "AI",      self._show_settings),
            (self.btn_adv, "🛠️ 상세설정", "상세설정", self._show_adv_settings),
            (self.btn_spk, "🗣️ 화자",    "화자",     self._show_speaker_settings),
            (self.btn_gap, "⏱️ 간격",    "간격",     self._show_gap_settings),
            (self.btn_vid, "🎬 비디오",  "비디오",   self._toggle_video),
        ]
        _top_style = (f"QPushButton {{ background: {config.BG3}; color: {config.FG}; border: none; "
                      f"padding: 6px 10px; font-size: 11px; border-radius: 3px; }} "
                      f"QPushButton:hover {{ background: #444444; }}")
        for btn, _, _, slot in self._top_btns:
            btn.setStyleSheet(_top_style); btn.clicked.connect(slot); btn_row.addWidget(btn)
        btn_row.addStretch(); left_vbox.addLayout(btn_row)

        # ── 중앙 (btn_exit 제거) ──
        center_w = QWidget(); center_hbox = QHBoxLayout(center_w)
        center_hbox.setContentsMargins(0, 0, 0, 0); center_hbox.setSpacing(5)
        self.btn_prev  = QPushButton("◀ 이전")
        self.btn_start = QPushButton("🧠 시작")
        self.btn_save  = QPushButton("💾 저장")
        self.btn_exp   = QPushButton("🎥 자막출력")
        self.btn_next  = QPushButton("다음 ▶")
        self._bot_btns = [
            (self.btn_prev,  "◀ 이전",     "이전", self._on_prev),
            (self.btn_start, "🧠 시작",    "시작", self._on_start_clicked),
            (self.btn_save,  "💾 저장",    "저장", self._on_save),
            (self.btn_exp,   "🎥 자막출력", "출력", self._show_export_dialog),
            (self.btn_next,  "다음 ▶",    "다음",  self._on_next),
        ]
        # [v01.00.06] min-height: 40px — 이전/다음 높이 통일
        _bot_style = (f"QPushButton {{ background: #444444; color: #FFFFFF; border: none; "
                      f"padding: 10px 18px; font-size: 13px; font-weight: bold; "
                      f"border-radius: 4px; min-height: 40px; }} "
                      f"QPushButton:hover {{ background: {config.ACCENT}; color: #000000; }}")
        for btn, _, _, slot in self._bot_btns:
            btn.setStyleSheet(_bot_style); btn.clicked.connect(slot); center_hbox.addWidget(btn)

        # ── 우측 (engine_lbl 11px) ──
        right_w = QWidget(); right_vbox = QVBoxLayout(right_w); right_vbox.setContentsMargins(0, 0, 15, 0)
        self.engine_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.engine_lbl.setStyleSheet(
            f"color: {config.ACCENT}; font-size: 11px; font-weight: bold; line-height: 1.2;"
        )
        right_vbox.addWidget(self.engine_lbl)

        grid.addWidget(left_w,   0, 0, Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(center_w, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(right_w,  0, 2, Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 0); grid.setColumnStretch(2, 1)
        return w

    def resizeEvent(self, event):
        super().resizeEvent(event)
        is_compact = self.width() < 1100
        top_font = "10px" if is_compact else "11px"
        top_style = (f"QPushButton {{ background: {config.BG3}; color: {config.FG}; border: none; "
                     f"padding: 6px 8px; font-size: {top_font}; border-radius: 3px; }} "
                     f"QPushButton:hover {{ background: #444444; }}")
        for btn, full_t, comp_t, _ in getattr(self, '_top_btns', []):
            btn.setText(comp_t if is_compact else full_t); btn.setStyleSheet(top_style)
        bot_font = "11px" if is_compact else "13px"
        bot_pad  = "8px 10px" if is_compact else "10px 18px"
        bot_style = (f"QPushButton {{ background: #444444; color: #FFFFFF; border: none; "
                     f"padding: {bot_pad}; font-size: {bot_font}; font-weight: bold; "
                     f"border-radius: 4px; min-height: 40px; }} "
                     f"QPushButton:hover {{ background: {config.ACCENT}; color: #000000; }}")
        for btn, full_t, comp_t, _ in getattr(self, '_bot_btns', []):
            if btn != getattr(self, 'btn_start', None):
                btn.setText(comp_t if is_compact else full_t)
            btn.setStyleSheet(bot_style)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _update_highlighter_colors(self):
        cmap = {
            self.settings.get("spk1_id", "00"): self.settings.get("spk1_color", "#FFFFFF"),
            self.settings.get("spk2_id", "01"): self.settings.get("spk2_color", "#FFFF00"),
            self.settings.get("spk3_id", "02"): self.settings.get("spk3_color", "#00FFFF"),
        }
        self._highlighter.speaker_colors = cmap; self._highlighter.rehighlight()

    def set_vad_segments(self, vad_segs):
        if hasattr(self, 'timeline'): self.timeline.set_vad_segments(vad_segs)

    def set_terminal_visible_layout(self, is_visible: bool):
        if not hasattr(self, 'splitter'): return
        self.splitter.setSizes([6500, 3500] if is_visible else [4000, 6000])

    def _force_ui_log(self, msg: str): get_logger().log(msg)

    def _fallback_parse_srt(self, srt_path: str) -> list[dict]:
        segments = []; content = ""
        for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
            try:
                with open(srt_path, "r", encoding=enc) as f: content = f.read(); break
            except Exception: continue
        if not content: return segments
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        pattern = re.compile(
            r'(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\n(.*?)(?=\n(?:\s*\d+\s*\n)?\s*\d{2}:\d{2}:\d{2}[,.]|\Z)',
            re.DOTALL
        )
        def _ts(ts): h, mn, s = ts.replace(',', '.').split(':'); return int(h)*3600+int(mn)*60+float(s)
        for m in pattern.finditer(content):
            try: segments.append({"start": _ts(m.group(1)), "end": _ts(m.group(2)),
                                   "text": m.group(3).strip(), "is_gap": False})
            except Exception: continue
        return segments

    def _update_engine_label_text(self):
        short_w = self.settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "")).replace("mlx-community/", "").replace("-mlx", "") or "기본"
        audio_ai  = {"deepfilter": "DeepFilter", "demucs": "Demucs", "none": "미사용"}.get(self.settings.get("selected_audio_ai", "demucs"), "Demucs")
        vad_model = {"silero": "Silero", "webrtc": "WebRTC", "pyannote": "Pyannote", "none": "미사용(30초)"}.get(self.settings.get("selected_vad", "none"), "미사용(30초)")
        llm_model = self.selected_model
        llm_model = "미사용" if "사용 안함" in llm_model else llm_model.split(":")[0].upper()
        self.engine_lbl.setText(f"[VAD] : {vad_model}\n[음성] : {audio_ai}\n[STT] : {short_w}\n[LLM] : {llm_model}")

    def _cleanup(self):
        # 💡 누락되었던 자동저장/상태 애니메이션 타이머까지 완벽하게 정지시킵니다.
        timers = [
            '_playhead_timer', '_queue_timer', '_timeline_timer', 
            '_spinner_timer', '_nav_timer', '_auto_save_timer', '_status_anim_timer'
        ]
        for attr in timers:
            t = getattr(self, attr, None)
            if t and t.isActive(): 
                t.stop()
                
        if hasattr(self, 'video_player'): 
            try: self.video_player.pause_video()
            except Exception: pass
            
        self.corrections, self.subtitle_rules, self.settings = _dm_cleanup_rules(
            self.corrections, self.subtitle_rules, self.settings, self._get_current_segments
        )

        # ✅ 추가: 시그널 안전 해제
        try:
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
                self.timeline.canvas.sig_split_request.disconnect()
                self.timeline.canvas.sig_inline_text_changed.disconnect()
        except (TypeError, RuntimeError):
            pass

    def _toggle_focus(self):
        if self.text_edit.hasFocus():
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'): self.timeline.canvas.setFocus()
            elif hasattr(self, 'timeline'): self.timeline.setFocus()
        else: self.text_edit.setFocus()

    def _route_undo(self):
        from PyQt6.QtWidgets import QApplication
        fw = QApplication.focusWidget()
        if hasattr(fw, 'undo') and fw.hasFocus(): fw.undo()
        else: self._undo_mgr.undo()

    def _route_redo(self):
        from PyQt6.QtWidgets import QApplication
        fw = QApplication.focusWidget()
        if hasattr(fw, 'redo') and fw.hasFocus(): fw.redo()
        else: self._undo_mgr.redo()