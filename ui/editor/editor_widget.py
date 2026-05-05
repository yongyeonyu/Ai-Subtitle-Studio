# Version: 03.14.31
# Phase: PHASE2
"""Editor widget and function-preserving PHASE1-C layout."""
import re, os, sys, atexit, time
from ui.editor.undo_manager import UndoManager

def _mac_safe_exit():
    try: sys.stdout.flush(); sys.stderr.flush()
    except: pass
    os._exit(0)
atexit.register(_mac_safe_exit)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QPushButton, QLabel, QMessageBox, QLineEdit, QComboBox,
    QToolButton, QCheckBox, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor, QIcon

from core.runtime import config
from core.runtime.logger import get_logger
from core.project.data_manager import (
    load_settings as _dm_load_settings, load_corrections as _dm_load_corrections, cleanup_rules as _dm_cleanup_rules, load_subtitle_rules as _dm_load_rules
)
from core.state_manager import SubtitleStateManager
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_constants import FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH
from ui.timeline.speaker_labels import current_speaker_settings
from ui.style import button_style, label_style, line_icon, tool_button_style
from ui.editor.editor_popup_qt import EditorPopup
from ui.editor.video_player_widget import VideoPlayerWidget
from ui.editor.subtitle_text_edit import SubtitleTextEdit, SubtitleHighlighter, SubtitleBlockData
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.editor_video_controls import EditorVideoControlsMixin
from ui.editor.editor_multiclip_context import EditorMulticlipContextMixin
from ui.editor.editor_speaker_ops import EditorSpeakerOpsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin
from ui.editor.editor_stt_mode import EditorSTTModeMixin

DATASET_DIR   = "dataset"
SETTINGS_FILE = os.path.join(DATASET_DIR, "user_settings.json")


class EditorWidget(
    EditorActionsMixin,
    EditorPipelineMixin,
    EditorSegmentsMixin,
    EditorTimelineVideoMixin,
    EditorVideoControlsMixin,
    EditorMulticlipContextMixin,
    EditorSpeakerOpsMixin,
    EditorMulticlipOpsMixin,
    EditorSTTModeMixin,
    QWidget,
):
    sig_start     = pyqtSignal()
    sig_prev      = pyqtSignal()
    sig_save      = pyqtSignal(list)
    sig_auto_save = pyqtSignal(list)
    sig_exit      = pyqtSignal(list)
    sig_next      = pyqtSignal(list)
    sig_live_stt_result = pyqtSignal(str)
    sig_stt_vad_segments = pyqtSignal(list)
    sig_roughcut_draft_ready = pyqtSignal(object, list, dict)

    _JUNK_TS_RE               = re.compile(r'[\[{(<\[【（《]\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*[\]})>\]】）》]\s*')
    _JUNK_NO_BRACKET_3PART    = re.compile(r'(?<!\S)\d{1,3}[:\.]\d{2}[:\.]\d{2,3}(?!\S)')
    _JUNK_NO_BRACKET_3PART_END= re.compile(r'\d{1,3}[:\.]\d{2}[:\.]\d{2,3}\s*$')
    _JUNK_START_RE            = re.compile(r'^\s*\d{1,3}[:\.]\d{2}(?:[:\.]\d+)?\s+')
    _auto_start_next = False

    def __init__(
        self,
        video_name: str,
        segments: list[dict],
        media_path: str | None = None,
        parent=None,
        defer_media_load: bool = False,
    ):
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
        self._quality_filter_key = "all"
        self._quality_summary = None
        self.selected_model = self.settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

        self.sm = SubtitleStateManager()
        self.sm.current_file = media_path or ""    # ✅ 여기로 이동
        self.sm.sig_ui_update.connect(self._on_state_machine_update)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._on_auto_save)
        self._auto_save_timer.start(60000)

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
        self._live_editor_preview_queue: list[dict] = []
        self._live_editor_preview_segments: list[dict] = []
        self._live_editor_preview_keys: set[tuple] = set()
        self._live_editor_preview_pending = False
        self._inline_updating    = False
        self._init_stt_mode_state()
        self.sig_live_stt_result.connect(self._apply_stt_text_to_current)
        self.sig_stt_vad_segments.connect(self._apply_stt_vad_segments)

        self._queue_timer    = QTimer(); self._queue_timer.setSingleShot(True);    self._queue_timer.timeout.connect(self._flush_queue)
        self._live_editor_preview_timer = QTimer(self)
        self._live_editor_preview_timer.setSingleShot(True)
        self._live_editor_preview_timer.timeout.connect(self._flush_live_editor_preview_queue)
        self._timeline_timer = QTimer(); self._timeline_timer.setSingleShot(True); self._timeline_timer.timeout.connect(self._redraw_timeline)
        self._nav_timer      = QTimer(); self._nav_timer.setSingleShot(True)
        self._roughcut_draft_timer = QTimer(self)
        self._roughcut_draft_timer.setSingleShot(True)
        self._roughcut_draft_timer.timeout.connect(self._run_post_generation_roughcut_draft)
        self._roughcut_draft_thread = None
        self._roughcut_draft_pending = False
        self._roughcut_draft_generation = 0
        self._roughcut_draft_status = "idle"
        self._last_roughcut_draft_major_count = None
        self.sig_roughcut_draft_ready.connect(self._apply_post_generation_roughcut_draft)

        self.status_lbl = QLabel("대기 중...")
        self.engine_lbl = QLabel()
        self._update_engine_label_text()

        self._spinner_timer  = QTimer(); self._spinner_timer.setInterval(400); self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_frames = ["⏳", "⌛"]
        self._spinner_idx    = 0

        self.editor_popup = EditorPopup(self)
        
        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_app_focus_changed)
        QTimer.singleShot(0, self._hook_multiclip_clip_signals)
        
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
                from core.srt_parser import parse_srt
                from core.subtitle_existing import backup_existing_srt, validate_srt_duration
                ok, reason = validate_srt_duration(srt_guess, media_path)
                if ok:
                    segments = parse_srt(srt_guess)
                else:
                    QMessageBox.warning(self, "기존 자막 오류", reason)
                    backup_existing_srt(srt_guess)
                    segments = []

        self._is_initial_load = True if segments else False
        if segments:
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
                self.timeline.canvas.segments = [dict(s) for s in segments]
                if hasattr(self.timeline.canvas, "_invalidate_render_cache"):
                    self.timeline.canvas._invalidate_render_cache()
            self.append_segments(segments)
            QTimer.singleShot(350, self._mark_initial_segments_saved)

        if media_path and not defer_media_load:
            QTimer.singleShot(200, lambda: self._load_video(media_path))

        self._playhead_timer = QTimer()
        self._playhead_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._playhead_timer.setInterval(16)
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
        self.save_shortcut.activated.connect(lambda: self._on_save(skip_auto_next=True))

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
        
        # 💡 [핵심 교정부] 시작 시점에 is_auto_start인지 확인 후 올바른 모드로 초기화합니다.
        if segments: 
            self.sm.complete_ai()
        else:
            if getattr(self, 'is_auto_start', False):
                self.sm.init_auto_state()
            else:
                self.sm.init_state()

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
            self.btn_start.setText(self._clean_action_label(btn_txt))
            self.btn_start.setEnabled(btn_en)
        main_w = self.window()
        if hasattr(main_w, "sync_menu_from_editor"):
            main_w.sync_menu_from_editor(self)
        if hasattr(main_w, "_refresh_saved_status_label"):
            main_w._refresh_saved_status_label(
                is_dirty=is_dirty,
                touch_saved_time=(not is_dirty and state == SubtitleStateManager.ST_SAVED),
            )
        self._apply_text_editor_lock_state()

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
        if hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            if getattr(self.sm, "is_dirty", False) and hasattr(self, "_mark_save_completed"):
                self._mark_save_completed(touch_saved_time=False)
            return
        self.sm.start_editing()

    def _mark_initial_segments_saved(self):
        if getattr(self, "_segment_queue", None):
            QTimer.singleShot(150, self._mark_initial_segments_saved)
            return
        if not hasattr(self, "_remember_saved_segments"):
            return
        try:
            self._remember_saved_segments(self._get_current_segments())
            if hasattr(self, "_remember_saved_project_file"):
                self._remember_saved_project_file()
            if hasattr(self, "sm") and self.sm.state != SubtitleStateManager.ST_PROC:
                self.sm.complete_save()
        except Exception:
            pass

    def _on_auto_save(self):
        if self.sm.is_locked: return
        if hasattr(self, "_has_unsaved_changes"):
            try:
                self._has_unsaved_changes()
            except Exception:
                pass
        if self.sm.is_dirty:
            segs = self._get_current_segments()
            if not segs:
                return
            self.sm.start_autosave()
            try:
                self.sig_auto_save.emit(segs)
            except Exception as e:
                get_logger().log(f"⚠️ 자동 저장 실패: {e}")
                return
            self._on_save(skip_auto_next=True)

    # ---------------------------------------------------------
    # UI 빌드
    # ---------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(2, 2, 2, 2); root.setSpacing(2)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(3)
        self.splitter.setStyleSheet("QSplitter::handle { background: #2D3942; width: 1px; margin: 0 1px; }")
        editor_wrap = QWidget(); editor_wrap.setMinimumWidth(260); editor_wrap.setStyleSheet("background: #151C20; border: none; border-radius: 0px;")
        self._editor_wrap = editor_wrap
        editor_wrap.installEventFilter(self)
        ew_layout   = QVBoxLayout(editor_wrap); ew_layout.setContentsMargins(8, 8, 8, 8); ew_layout.setSpacing(6)

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
        self._editor_focus_border = QWidget(editor_wrap)
        self._editor_focus_border.setObjectName("EditorFocusBorder")
        self._editor_focus_border.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._editor_focus_border.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._editor_focus_border.setStyleSheet(
            "QWidget#EditorFocusBorder {"
            " background: transparent;"
            f" border: {FOCUS_BORDER_WIDTH}px solid {FOCUS_BORDER_COLOR};"
            " border-radius: 0px;"
            "}"
        )
        self._editor_focus_border.hide()
        self._sync_editor_focus_border()
        self.splitter.addWidget(editor_wrap)
        self.video_player = VideoPlayerWidget()
        if hasattr(self.video_player, "set_subtitle_provider"):
            self.video_player.set_subtitle_provider(self._video_subtitle_context_for_player)
        if hasattr(self.video_player, "frame_step_requested"):
            self.video_player.frame_step_requested.connect(self._on_step_frame)
        if hasattr(self.video_player, "scan_cut_requested"):
            self.video_player.scan_cut_requested.connect(self._on_scan_cut_requested)
        self.video_player.setStyleSheet("background: #000000; border: none; border-radius: 0px;")
        self.splitter.addWidget(self.video_player)
        self.splitter.setStretchFactor(0, 63); self.splitter.setStretchFactor(1, 37)
        self.splitter.setCollapsible(0, False); self.splitter.setCollapsible(1, False)
        root.addWidget(self.splitter, stretch=1)
        self.external_menu_host = QWidget()
        self.external_menu_host.setObjectName("EditorExternalMenuHost")
        self.external_menu_host.setStyleSheet("QWidget#EditorExternalMenuHost { background: transparent; border: none; }")
        self.external_menu_host_layout = QVBoxLayout(self.external_menu_host)
        self.external_menu_host_layout.setContentsMargins(0, 0, 0, 0)
        self.external_menu_host_layout.setSpacing(0)
        self.external_menu_host.setFixedHeight(0)
        self.external_menu_host.hide()
        root.addWidget(self.external_menu_host)
        self._video_width_locking = False
        QTimer.singleShot(0, self._position_video_expand_button)
        QTimer.singleShot(150, self._position_video_expand_button)

        self.timeline = TimelineWidget()
        self.timeline.setStyleSheet("background: #151C20; border: 1px solid #2D3942; border-radius: 7px;")
        if hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.show_waveform = True
            self.timeline.canvas.update()

        # ✅ 여기 딱 한 번만 connect
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'sig_split_request'):
            self.timeline.canvas.sig_split_request.connect(self.split_segment_with_text)

        self.timeline.seg_clicked.connect(self._on_timeline_seg_clicked)
        if hasattr(self.timeline, 'stt_candidate_selected'):
            self.timeline.stt_candidate_selected.connect(self.select_stt_candidate_as_subtitle)
        self.timeline.seg_double_clicked.connect(self._on_timeline_seg_double_clicked)
        self.timeline.scrub_sec.connect(self._on_scrub)

        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'seg_right_clicked'):
            self.timeline.canvas.seg_right_clicked.connect(self._on_timeline_seg_right_clicked)
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'speaker_changed'):
            self.timeline.canvas.speaker_changed.connect(self._change_speaker_for_line)
                
        # 멀티클립 전환
        if hasattr(self.timeline, 'sig_clip_selected'): self.timeline.sig_clip_selected.connect(self._on_clip_selected)
        if hasattr(self.timeline, 'seg_time_changed'): self.timeline.seg_time_changed.connect(self._on_seg_time_changed)
        if hasattr(self.timeline, 'seg_to_gap'):       self.timeline.seg_to_gap.connect(self._on_seg_to_gap)
        if hasattr(self.timeline, 'gap_activated'):    self.timeline.gap_activated.connect(self._on_gap_activated)
        if hasattr(self.timeline, 'gap_to_segs'):      self.timeline.gap_to_segs.connect(self._on_gap_to_segs)
        if hasattr(self.timeline, 'gap_generate_requested'): self.timeline.gap_generate_requested.connect(self._on_gap_generate_requested)
        if hasattr(self.timeline, 'drag_started'):     self.timeline.drag_started.connect(self._on_drag_started)
        if hasattr(self.timeline, 'drag_finished'):    self.timeline.drag_finished.connect(self._on_drag_finished)
        if hasattr(self.timeline, 'step_frame'):       self.timeline.step_frame.connect(self._on_step_frame)
        if hasattr(self.timeline, 'lock_chk'):         self.timeline.lock_chk.toggled.connect(self._on_lock_changed)
        if hasattr(self.timeline, 'diamond_merge'):    self.timeline.diamond_merge.connect(self._on_diamond_merge)
        if hasattr(self.timeline, 'sig_inline_text_changed'): self.timeline.sig_inline_text_changed.connect(self._on_inline_text_changed)
        if hasattr(self.timeline, 'sig_editing_mode'):        self.timeline.sig_editing_mode.connect(self._on_seg_editing_mode)
        if hasattr(self.timeline, 'playhead_menu_requested'): self.timeline.playhead_menu_requested.connect(self._show_playhead_menu)
        if hasattr(self.timeline, 'provisional_cut_boundary_requested'): self.timeline.provisional_cut_boundary_requested.connect(self._on_provisional_cut_boundary_requested)
        if hasattr(self.timeline, 'provisional_cut_boundary_delete_requested'): self.timeline.provisional_cut_boundary_delete_requested.connect(self._on_provisional_cut_boundary_delete_requested)
        if hasattr(self.timeline, 'sig_smart_split'):         self.timeline.sig_smart_split.connect(self._on_smart_split)
            
        root.addWidget(self.timeline)
        self._internal_button_bar = self._build_buttons()
        self._internal_button_bar.setFixedHeight(0)
        self._internal_button_bar.setVisible(False)
        root.addWidget(self._internal_button_bar)

    def set_external_menu_bar(self, menu_widget):
        if menu_widget is None:
            return
        host = getattr(self, "external_menu_host", None)
        layout = getattr(self, "external_menu_host_layout", None)
        if host is None or layout is None:
            return
        try:
            old_parent = menu_widget.parentWidget()
            if old_parent is host and layout.indexOf(menu_widget) >= 0:
                host.show()
                host.setFixedHeight(max(74, menu_widget.sizeHint().height()))
                return
            menu_widget.setParent(host)
            layout.addWidget(menu_widget)
            menu_widget.show()
            host.show()
            host.setFixedHeight(max(74, menu_widget.sizeHint().height()))
        except RuntimeError:
            return

    def detach_external_menu_bar(self):
        host = getattr(self, "external_menu_host", None)
        layout = getattr(self, "external_menu_host_layout", None)
        if host is None or layout is None:
            return None
        if layout.count() <= 0:
            return None
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
        host.setFixedHeight(0)
        host.hide()
        return widget

    def _widget_is_inside_editor_panel(self, widget) -> bool:
        panel = getattr(self, "_editor_wrap", None)
        while widget is not None:
            if widget is panel:
                return True
            widget = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        return False

    def _editor_panel_has_focus(self) -> bool:
        return self._widget_is_inside_editor_panel(QApplication.focusWidget())

    def _sync_editor_focus_border(self):
        border = getattr(self, "_editor_focus_border", None)
        panel = getattr(self, "_editor_wrap", None)
        if border is None or panel is None:
            return
        border.setGeometry(0, 0, max(1, panel.width()), max(1, panel.height()))
        visible = self._editor_panel_has_focus() and not self._timeline_lock_edit_enabled()
        border.setVisible(visible)
        if visible:
            border.raise_()

    def _on_app_focus_changed(self, old, now):
        if self._widget_is_inside_editor_panel(old) or self._widget_is_inside_editor_panel(now):
            QTimer.singleShot(0, self._sync_editor_focus_border)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_editor_wrap", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._sync_editor_focus_border)
        return False

    def _on_inline_text_changed(self, line_num: int, new_text: str):
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid(): return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        live_canvas_edit = bool(
            canvas is not None
            and getattr(canvas, "_edit_active", False)
            and not getattr(canvas, "_inline_commit_in_progress", False)
        )
        if live_canvas_edit:
            if hasattr(self, "_update_subtitle_memory_line_text"):
                self._update_subtitle_memory_line_text(line_num, new_text)
            else:
                cached = getattr(self, "_cached_segs", None)
                visible_text = str(new_text or "").replace("\u2028", "\n")
                if cached is not None:
                    for seg in cached:
                        if int(seg.get("line", -999999)) == int(line_num):
                            seg["text"] = visible_text
                            break
            return
        if block.text() == new_text: return
        old_text = block.text()
        self._inline_updating = True
        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new_text)
        cur.block().setUserData(SubtitleBlockData(ud.spk_id, ud.start_sec, ud.is_gap))
        cur.endEditBlock()
        if old_text.count("\u2028") != str(new_text or "").count("\u2028"):
            self.text_edit.update_margins()
            if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._inline_updating = False
        if hasattr(self, "_update_subtitle_memory_line_text"):
            self._update_subtitle_memory_line_text(line_num, new_text)
        else:
            cached = getattr(self, "_cached_segs", None)
            visible_text = str(new_text or "").replace("\u2028", "\n")
            if cached is not None:
                for seg in cached:
                    if int(seg.get("line", -999999)) == int(line_num):
                        seg["text"] = visible_text
                        break
        self._refresh_video_subtitle_context()

    def _on_lock_changed(self, locked: bool):
        self._apply_text_editor_lock_state()
        if locked and hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.setFocus()
        self._sync_editor_focus_border()

    def _timeline_lock_edit_enabled(self) -> bool:
        lock_box = getattr(getattr(self, "timeline", None), "lock_chk", None)
        try:
            return bool(lock_box is not None and lock_box.isChecked())
        except RuntimeError:
            return False

    def _apply_text_editor_lock_state(self):
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return
        timeline_locked = self._timeline_lock_edit_enabled()
        processing_locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        if hasattr(text_edit, "set_selection_locked"):
            text_edit.set_selection_locked(timeline_locked)
        else:
            text_edit.setReadOnly(timeline_locked or processing_locked)
        if not timeline_locked and processing_locked:
            text_edit.setReadOnly(True)
            text_edit.setStyleSheet("QTextEdit { background-color: #1a1a1a; color: #888888; }")

    def _build_editor_header(self) -> QWidget:
        header = QWidget()
        lay = QHBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title = QLabel("Subtitle Editor")
        title.setStyleSheet(label_style("text", 14, bold=True))
        media = QLabel(str(getattr(self, "video_name", "") or "Untitled"))
        media.setStyleSheet(label_style("muted", 11))
        title_box.addWidget(title)
        title_box.addWidget(media)
        lay.addLayout(title_box, stretch=1)

        quick = QLineEdit()
        quick.setObjectName("quickFind")
        quick.setFixedWidth(76)
        quick.setPlaceholderText("검색")
        quick.setToolTip("빠른 자막 검색")
        quick.setStyleSheet(
            "QLineEdit { background: #0F1518; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 8px; padding: 5px 8px; font-size: 11px; }"
        )
        quick.returnPressed.connect(lambda q=quick: self._search_subtitle_text(q.text()))
        lay.addWidget(quick)
        add_mock = QPushButton("+")
        add_mock.setToolTip("현재 위치에 새 자막 추가")
        add_mock.setStyleSheet(button_style("toolbar", font_size="12px", padding="5px 9px"))
        add_mock.clicked.connect(self._split_at_playhead_or_cut)
        lay.addWidget(add_mock)
        lay.addWidget(self._build_speaker_strip())
        return header

    def _build_table_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("subtitleTableHeader")
        header.setFixedHeight(30)
        header.setStyleSheet("background: #1B2429; border: 1px solid #2D3942; border-radius: 6px;")
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(0)
        cols = [
            ("#", 58),
            ("시작 시간", 150),
            ("종료 시간", 150),
            ("화자", 110),
            ("자막", 0),
        ]
        for text, width in cols:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter if text != "자막" else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("color: #A9B0B7; font-size: 11px; font-weight: 600; background: transparent; border-right: 1px solid #2D3942;")
            if width:
                lbl.setFixedWidth(width)
                row.addWidget(lbl)
            else:
                row.addWidget(lbl, stretch=1)
        return header

    def _build_editor_mode_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("subtitleEditorModeBar")
        bar.setVisible(False)
        bar.setFixedHeight(0)
        bar.setStyleSheet("background: #151C20; border: 1px solid #2D3942; border-radius: 7px;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)
        for label in ("편집 모드", "작성", "시간", "검수"):
            btn = QPushButton(label)
            btn.setToolTip("UI placeholder: 표 기반 자막 편집 모드")
            active = label == "작성"
            btn.setStyleSheet(
                "QPushButton { "
                f"background: {'#252D33' if active else 'transparent'}; color: {'#FFFFFF' if active else '#A9B0B7'}; "
                "border: 1px solid #303A42; border-radius: 6px; padding: 5px 11px; font-size: 11px; "
                "} QPushButton:hover { background: #252D33; color: #FFFFFF; }"
            )
            row.addWidget(btn)
        self.btn_quality_review = QPushButton("검사")
        self.btn_quality_review.setToolTip("현재 자막 품질 검사")
        self.btn_quality_review.setIcon(self._make_line_icon("check", "#D7EBFF", 18))
        self.btn_quality_review.setStyleSheet(button_style("primary", font_size="11px", padding="5px 10px"))
        self.btn_quality_review.clicked.connect(lambda: self._run_quality_review(auto_correct=False))
        row.addWidget(self.btn_quality_review)
        self.chk_quality_auto = QCheckBox("자동 교정")
        self.chk_quality_auto.setToolTip("낮은 점수 구간만 안전 후보를 자동 적용")
        self.chk_quality_auto.setChecked(bool(self.settings.get("subtitle_quality_auto_correct_enabled", False)))
        self.chk_quality_auto.setStyleSheet(
            "QCheckBox { color: #A9B0B7; font-size: 11px; background: transparent; spacing: 5px; } "
            "QCheckBox::indicator { width: 14px; height: 14px; }"
        )
        row.addWidget(self.chk_quality_auto)
        self.quality_filter_combo = QComboBox()
        self.quality_filter_combo.setToolTip("품질 표시 필터")
        self.quality_filter_combo.addItem("전체", "all")
        self.quality_filter_combo.addItem("확인 필요", "needs_review")
        self.quality_filter_combo.addItem("red", "red")
        self.quality_filter_combo.addItem("gray", "gray")
        self.quality_filter_combo.addItem("자동 교정됨", "auto_corrected")
        self.quality_filter_combo.currentIndexChanged.connect(self._on_quality_filter_changed)
        self.quality_filter_combo.setStyleSheet(
            "QComboBox { background: #11181C; color: #F5F7FA; border: 1px solid #303A42; "
            "border-radius: 6px; padding: 4px 8px; font-size: 11px; }"
        )
        row.addWidget(self.quality_filter_combo)
        self.btn_quality_candidates = QPushButton("후보")
        self.btn_quality_candidates.setToolTip("현재 자막의 품질 후보 비교")
        self.btn_quality_candidates.setStyleSheet(button_style("toolbar", font_size="11px", padding="5px 9px"))
        self.btn_quality_candidates.clicked.connect(self._show_quality_candidates_for_current_line)
        row.addWidget(self.btn_quality_candidates)
        row.addStretch()
        self.quality_summary_lbl = QLabel("품질 미검사")
        self.quality_summary_lbl.setToolTip("전체 품질 요약")
        self.quality_summary_lbl.setStyleSheet(label_style("muted", 11, bold=True))
        row.addWidget(self.quality_summary_lbl)
        sort_lbl = QLabel("정렬")
        sort_lbl.setStyleSheet(label_style("muted", 11, bold=True))
        row.addWidget(sort_lbl)
        sort_combo = QComboBox()
        sort_combo.addItems(["시작 시간", "종료 시간", "화자"])
        sort_combo.setToolTip("UI placeholder: 자막 행 정렬")
        sort_combo.setStyleSheet(
            "QComboBox { background: #11181C; color: #F5F7FA; border: 1px solid #303A42; "
            "border-radius: 6px; padding: 4px 8px; font-size: 11px; }"
        )
        row.addWidget(sort_combo)
        search = QLineEdit()
        search.setPlaceholderText("검색")
        search.setToolTip("자막 검색")
        search.setFixedWidth(260)
        search.setStyleSheet(
            "QLineEdit { background: #11181C; color: #F5F7FA; border: 1px solid #303A42; "
            "border-radius: 6px; padding: 5px 8px; font-size: 11px; }"
        )
        search.returnPressed.connect(lambda q=search: self._search_subtitle_text(q.text()))
        row.addWidget(search)
        more = QPushButton("···")
        more.setToolTip("UI placeholder: 추가 보기 옵션")
        more.setStyleSheet(button_style("toolbar", font_size="11px", padding="5px 8px"))
        row.addWidget(more)
        return bar

    def _quality_vad_segments(self) -> list[dict]:
        try:
            return list(getattr(self.timeline.canvas, "vad_segments", []) or [])
        except Exception:
            return []

    def _set_quality_running(self, running: bool):
        if hasattr(self, "btn_quality_review"):
            self.btn_quality_review.setEnabled(not running)
            self.btn_quality_review.setText("검사 중" if running else "검사")
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText("에디터 | 검사 중" if running else "에디터 | 검사 완료")

    def _run_quality_review(self, auto_correct: bool | None = None):
        from core.subtitle_quality.quality_pipeline import run_subtitle_quality_pipeline

        auto_checkbox = getattr(self, "chk_quality_auto", None)
        auto = bool(auto_checkbox.isChecked()) if auto_correct is None and auto_checkbox is not None else bool(auto_correct)
        if auto:
            self.settings["subtitle_quality_auto_correct_enabled"] = True
        self.settings["subtitle_quality_enabled"] = True
        segs = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        if not segs:
            QMessageBox.information(self, "품질 검사", "검사할 자막이 없습니다.")
            return
        self._set_quality_running(True)
        try:
            result = run_subtitle_quality_pipeline(
                segs,
                vad_segments=self._quality_vad_segments(),
                settings=self.settings,
                auto_correct=auto,
                context={
                    "clip_boundaries": list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or []),
                },
            )
            self._apply_quality_result(result, auto_correct=auto)
            summary = result.summary
            score = "-" if summary.overall_score is None else f"{summary.overall_score:.1f}"
            get_logger().log(
                f"[자막 품질] 검사 완료: 전체 {score}점, 확인 필요 {summary.needs_review_count}개, 자동 교정 {summary.auto_corrected_count}개"
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 자막 품질 검사 오류: {exc}")
            QMessageBox.warning(self, "품질 검사 오류", str(exc))
        finally:
            self._set_quality_running(False)

    def _apply_quality_result(self, result, *, auto_correct: bool = False):
        self._quality_summary = getattr(result, "summary", None)
        result_by_line = {}
        for idx, seg in enumerate(getattr(result, "segments", []) or []):
            line = int(seg.get("line", idx) if seg.get("line") is not None else idx)
            result_by_line[line] = dict(seg)

        if auto_correct and hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()

        doc = self.text_edit.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        quality_map: dict[int, dict] = {}
        for line, seg in result_by_line.items():
            block = doc.findBlockByNumber(int(line))
            if not block.isValid():
                continue
            data = block.userData()
            if not isinstance(data, SubtitleBlockData) or data.is_gap:
                continue
            new_text = str(seg.get("text", "") or "")
            if auto_correct and new_text and new_text != block.text():
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(new_text)
                block = cursor.block()
            quality = dict(seg.get("quality") or {})
            quality_map[int(line)] = quality
            seg_for_sig = {
                "start": data.start_sec,
                "end": seg.get("end", data.start_sec),
                "text": block.text(),
                "speaker": data.spk_id,
            }
            block.setUserData(
                SubtitleBlockData(
                    data.spk_id,
                    data.start_sec,
                    data.is_gap,
                    stt_mode=getattr(data, "stt_mode", False),
                    stt_pending=getattr(data, "stt_pending", False),
                    original_text=getattr(data, "original_text", ""),
                    dictated_text=getattr(data, "dictated_text", ""),
                    quality=quality,
                    quality_history=list(seg.get("quality_history") or []),
                    quality_candidates=list(seg.get("quality_candidates") or []),
                    quality_signature=self._segment_quality_signature(seg_for_sig),
                )
            )
        cursor.endEditBlock()

        if hasattr(self, "_highlighter"):
            self._highlighter.set_quality_map(quality_map)
            self._highlighter.set_quality_filter(self._quality_filter_key)
        self._update_quality_summary_label()
        self._schedule_timeline()
        self._refresh_video_subtitle_context()
        if auto_correct:
            self._mark_dirty()

    def _update_quality_summary_label(self):
        summary = self._quality_summary
        if not hasattr(self, "quality_summary_lbl"):
            return
        if summary is None:
            self.quality_summary_lbl.setText("품질 미검사")
            return
        score = "-" if summary.overall_score is None else f"{summary.overall_score:.1f}"
        before_after = ""
        if summary.before_score is not None and summary.after_score is not None and summary.before_score != summary.after_score:
            delta = summary.after_score - summary.before_score
            before_after = f" · {summary.before_score:.1f}→{summary.after_score:.1f} ({delta:+.1f})"
        self.quality_summary_lbl.setText(
            f"품질 {score}점{before_after} · 확인 {summary.needs_review_count} · 교정 {summary.auto_corrected_count}"
        )

    def _on_quality_filter_changed(self, *_args):
        combo = getattr(self, "quality_filter_combo", None)
        self._quality_filter_key = str(combo.currentData() if combo else "all") or "all"
        if hasattr(self, "_highlighter"):
            self._highlighter.set_quality_filter(self._quality_filter_key)
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.quality_filter = self._quality_filter_key
            self.timeline.canvas.update()

    def _segment_for_line(self, line: int) -> dict | None:
        for seg in self._get_current_segments():
            if int(seg.get("line", -1) or -1) == int(line):
                return seg
        return None

    def _show_quality_candidates_for_current_line(self):
        from ui.editor.quality_candidate_dialog import QualityCandidateDialog

        line = self.text_edit.textCursor().blockNumber()
        seg = self._segment_for_line(line)
        if not seg or not seg.get("quality"):
            QMessageBox.information(self, "후보 비교", "현재 줄에 품질 검사 결과가 없습니다.")
            return
        dialog = QualityCandidateDialog(seg, self)
        if dialog.exec() != 1 or not dialog.selected_candidate:
            return
        candidate = dict(dialog.selected_candidate)
        text = str(candidate.get("text", "") or "")
        if not text:
            return
        old_seg = self._segment_for_line(line) or {}
        self._replace_segment_text_by_line(line, text, candidate)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                str(old_seg.get("text", "") or ""),
                text,
                source="quality_candidate",
                context=str(candidate.get("reason", "") or ""),
            )
        except Exception:
            pass

    def _replace_segment_text_by_line(self, line: int, text: str, candidate: dict | None = None):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        current_seg = self._segment_for_line(line) or {}
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(text)
        quality = dict(getattr(data, "quality", {}) or {})
        flags = list(quality.get("flags") or [])
        if "candidate_applied" not in flags:
            flags.append("candidate_applied")
        quality["flags"] = flags
        quality["candidate_applied_reason"] = str((candidate or {}).get("reason", "") or "")
        cur.block().setUserData(
            SubtitleBlockData(
                data.spk_id,
                data.start_sec,
                data.is_gap,
                stt_mode=getattr(data, "stt_mode", False),
                stt_pending=getattr(data, "stt_pending", False),
                original_text=getattr(data, "original_text", ""),
                dictated_text=getattr(data, "dictated_text", ""),
                quality=quality,
                quality_history=list(getattr(data, "quality_history", []) or []),
                quality_candidates=list(getattr(data, "quality_candidates", []) or []),
                quality_signature=self._segment_quality_signature({
                    "start": data.start_sec,
                    "end": current_seg.get("end", data.start_sec),
                    "text": text,
                    "speaker": data.spk_id,
                }),
            )
        )
        cur.endEditBlock()
        self._mark_dirty()
        self._finalize_edit()

    def _search_subtitle_text(self, query: str):
        query = (query or "").strip()
        if not query:
            return
        doc = self.text_edit.document()
        start = self.text_edit.textCursor().position()
        cur = doc.find(query, start)
        if cur.isNull():
            cur = doc.find(query, 0)
        if cur.isNull():
            return
        self.text_edit.setTextCursor(cur)
        self.text_edit.ensureCursorVisible()

    def _build_speaker_strip(self) -> QWidget:
        strip = QWidget()
        self._speaker_strip = strip
        strip.setStyleSheet("background: #1B2429; border: 1px solid #2D3942; border-radius: 10px;")
        row = QHBoxLayout(strip)
        self._speaker_strip_layout = row
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)
        self._populate_speaker_strip(row)
        return strip

    def _populate_speaker_strip(self, row: QHBoxLayout):
        while row.count():
            item = row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        colors = ["#007AFF", "#34C759", "#FF9500"]
        speaker_settings = current_speaker_settings(self.settings)
        max_spk = max(1, min(3, int(speaker_settings.get("max_speakers", self.settings.get("max_speakers", 1)) or 1)))
        for idx in range(1, max_spk + 1):
            color = speaker_settings.get(f"spk{idx}_color", colors[idx - 1])
            name = str(speaker_settings.get(f"spk{idx}_name", "") or f"화자 {idx}")
            btn = QPushButton(f"● {name}")
            btn.setToolTip(f"{name} 설정")
            btn.setStyleSheet(
                "QPushButton { "
                f"color: {color}; background: #0F1518; border: 1px solid #2D3942; "
                "border-radius: 9px; padding: 5px 9px; font-size: 11px; font-weight: bold; "
                "} QPushButton:hover { border: 1px solid #007AFF; }"
            )
            btn.clicked.connect(self._show_speaker_settings)
            row.addWidget(btn)
        add_btn = QPushButton("+")
        add_btn.setToolTip("화자 추가/관리")
        add_btn.setStyleSheet(button_style("toolbar", font_size="12px", padding="5px 9px"))
        add_btn.clicked.connect(self._show_speaker_settings)
        row.addWidget(add_btn)

    def _refresh_speaker_strip(self):
        row = getattr(self, "_speaker_strip_layout", None)
        if row is not None:
            self._populate_speaker_strip(row)
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.update()

    def _build_buttons(self) -> QWidget:
        w = QWidget(); w.setFixedHeight(72); w.setStyleSheet("background: #151C20; border-top: 1px solid #2D3942;")
        grid = QGridLayout(w); grid.setContentsMargins(10, 6, 10, 6)

        # ── 좌측 ──
        left_w    = QWidget(); left_vbox = QVBoxLayout(left_w); left_vbox.setContentsMargins(0, 0, 0, 0); left_vbox.setSpacing(5)
        self.status_lbl.setStyleSheet(label_style("warning", 13, bold=True))
        left_vbox.addWidget(self.status_lbl, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        btn_row = QHBoxLayout(); btn_row.setSpacing(5)
        self.btn_ai  = QPushButton("⚙️ AI")
        self.btn_spk = QPushButton("🗣️ 화자")
        self.btn_gap = QPushButton("⏱️ 간격")
        self.btn_vid = QPushButton("🎬 비디오")
        self.btn_log = QPushButton(self._terminal_log_button_text())
        self._top_btns = [
            (self.btn_ai,  "⚙️ AI",      "AI",      self._show_settings),
            (self.btn_spk, "🗣️ 화자",    "화자",     self._show_speaker_settings),
            (self.btn_gap, "⏱️ 간격",    "간격",     self._show_gap_settings),
            (self.btn_vid, "🎬 비디오",  "비디오",   self._toggle_video),
            (self.btn_log, "터미널 로그", "로그",     self._toggle_terminal_log),
        ]
        for btn, _, _, slot in self._top_btns:
            btn.setStyleSheet(button_style("toolbar")); btn.clicked.connect(slot); btn_row.addWidget(btn)
        btn_row.addStretch(); left_vbox.addLayout(btn_row)

        # ── 중앙 ──
        center_w = QWidget(); center_hbox = QHBoxLayout(center_w)
        center_hbox.setContentsMargins(0, 0, 0, 0); center_hbox.setSpacing(5)
        self.btn_start = self._make_action_toolbutton("시작", "restart")
        self.btn_save  = self._make_action_toolbutton("저장", "save")
        self.btn_exp   = self._make_action_toolbutton("자막출력", "export")
        self._bot_btns = [
            (self.btn_start, "시작",       "시작", self._on_start_clicked),
            (self.btn_save,  "💾 저장",    "저장", lambda: self._on_save(skip_auto_next=True)),
            (self.btn_exp,   "🎥 자막출력", "출력", self._show_export_dialog),
        ]
        for btn, _, _, slot in self._bot_btns:
            btn.clicked.connect(slot); center_hbox.addWidget(btn)

        # ── 우측 (engine_lbl 11px) ──
        right_w = QWidget(); right_vbox = QVBoxLayout(right_w); right_vbox.setContentsMargins(0, 0, 15, 0)
        self.engine_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.engine_lbl.setStyleSheet(
            "color: #6E6E73; font-size: 11px; font-weight: bold; line-height: 1.2;"
        )
        right_vbox.addWidget(self.engine_lbl)

        grid.addWidget(left_w,   0, 0, Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(center_w, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(right_w,  0, 2, Qt.AlignmentFlag.AlignRight  | Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 0); grid.setColumnStretch(2, 1)
        return w

    def _make_line_icon(self, name: str, color="#F5F7FA", size=28) -> QIcon:
        return line_icon(name, color, size)

    def _make_action_toolbutton(self, text: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(self._make_line_icon(icon_name))
        btn.setIconSize(QSize(24, 24))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedSize(92, 58)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setStyleSheet(tool_button_style("toolbar"))
        return btn

    def _clean_action_label(self, text: str) -> str:
        label = str(text or "")
        for token in ("🧠", "▶", "🔄", "⏳", "⌛", "💾", "🎥", "■"):
            label = label.replace(token, "")
        return label.strip() or "시작"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_video_expand_button)
        QTimer.singleShot(0, self._sync_editor_focus_border)
        is_compact = self.width() < 1100
        top_font = "10px" if is_compact else "11px"
        for btn, full_t, comp_t, _ in getattr(self, '_top_btns', []):
            btn.setText(comp_t if is_compact else full_t); btn.setStyleSheet(button_style("toolbar", font_size=top_font, padding="6px 8px"))
        for btn, full_t, comp_t, _ in getattr(self, '_bot_btns', []):
            if btn != getattr(self, 'btn_start', None):
                btn.setText(comp_t if is_compact else full_t)
        if hasattr(self, "btn_log"):
            self.btn_log.setText("로그" if is_compact else self._terminal_log_button_text())

    def _position_video_expand_button(self):
        return

    def _apply_fixed_video_preview_width(self):
        return

    def _video_fixed_height(self):
        try:
            return max(1, self.video_player.video_container.height())
        except Exception:
            return max(1, self.video_player.height() - 56)

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

    def set_voice_activity_segments(self, segments):
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'set_voice_activity_segments'):
            self.timeline.set_voice_activity_segments(segments)

    def set_terminal_visible_layout(self, is_visible: bool):
        if not hasattr(self, 'splitter'): return
        QTimer.singleShot(0, self._position_video_expand_button)
        timeline = getattr(self, "timeline", None)
        if timeline is not None and hasattr(timeline, "schedule_fit_to_view"):
            timeline.schedule_fit_to_view((0, 120, 260))
        if hasattr(self, "btn_log"):
            self.btn_log.setText(self._terminal_log_button_text())

    def _force_ui_log(self, msg: str): get_logger().log(msg)

    def _terminal_log_button_text(self):
        main_w = self.window()
        visible = bool(getattr(main_w, "_log_visible", True))
        return "사이드바 숨기기" if visible else "사이드바"

    def _toggle_terminal_log(self):
        main_w = self.window()
        if hasattr(main_w, "_toggle_log"):
            main_w._toggle_log()
            self.set_terminal_visible_layout(bool(getattr(main_w, "_log_visible", False)))

    def _update_engine_label_text(self):
        short_w = self.settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "")).replace("mlx-community/", "").replace("-mlx", "") or "기본"
        if self.settings.get("stt_ensemble_enabled"):
            short_w2 = str(self.settings.get("selected_whisper_model_secondary", "") or "").replace("mlx-community/", "").replace("-mlx", "")
            if short_w2 and short_w2 != short_w:
                short_w = f"{short_w} + {short_w2}"
        audio_ai = {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(self.settings.get("selected_audio_ai", "deepfilter"), "DeepFilter")
        vad_model = {"silero": "Silero", "ten_vad": "TEN VAD", "webrtc": "WebRTC", "pyannote": "Pyannote", "none": "미사용"}.get(self.settings.get("selected_vad", "none"), "미사용")
        if not self.settings.get("vad_pre_split_enabled", False):
            vad_model = "검수용" if vad_model != "미사용" else "미사용"
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
        if hasattr(self, 'timeline'):
            try:
                stop_waveform = getattr(self.timeline, "stop_waveform_workers", None)
                if callable(stop_waveform):
                    stop_waveform()
            except Exception:
                pass
            
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
