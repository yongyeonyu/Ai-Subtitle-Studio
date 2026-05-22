# Version: 03.14.31
# Phase: PHASE2
"""Editor widget and function-preserving PHASE1-C layout."""
import re, os, sys, atexit, time
from ui.editor.undo_manager import UndoManager

def _mac_safe_exit():
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (AttributeError, BrokenPipeError, OSError, ValueError):
        pass
    os._exit(0)
atexit.register(_mac_safe_exit)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QPushButton, QLabel, QMessageBox, QLineEdit, QComboBox,
    QToolButton, QCheckBox, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QEvent, QEventLoop
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor, QIcon

from core.runtime import config
from core.audio.audio_display import audio_filter_display_name
from core.runtime.logger import get_logger
from core.project.data_manager import (
    load_settings as _dm_load_settings, load_corrections as _dm_load_corrections, cleanup_rules as _dm_cleanup_rules, load_subtitle_rules as _dm_load_rules
)
from core.state_manager import SubtitleStateManager
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_constants import FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH
from ui.timeline.speaker_labels import current_speaker_settings
from core.speaker_profile_settings import visible_speaker_slots
from ui.responsive_profile import responsive_profile_for_size
from ui.style import COLORS, button_style, label_style, line_icon, tool_button_style
from ui.editor.ux.editor_popup_qt import EditorPopup
from ui.editor.video_player_widget import VideoPlayerWidget
from ui.editor.stable_render_frame import StableRenderFrame
from ui.editor.ux.subtitle_text_edit import (
    SubtitleTextEdit,
    SubtitleHighlighter,
    SubtitleBlockData,
    subtitle_block_data_from_meta,
    subtitle_block_data_to_meta,
)
from ui.editor.editor_automation import EditorAutomationMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_save_manager import EditorSaveManagerMixin
from ui.editor.editor_canvas_state import EditorCanvasStateMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.ux.editor_tab_timing import EditorTabTimingMixin
from ui.editor.ux.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.ux.editor_video_controls import EditorVideoControlsMixin
from ui.editor.ux.editor_subtitle_assist import EditorSubtitleAssistMixin
from ui.editor.editor_multiclip_context import EditorMulticlipContextMixin
from ui.editor.editor_speaker_ops import EditorSpeakerOpsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin
from ui.editor.editor_stt_mode import EditorSTTModeMixin

DATASET_DIR   = "dataset"
SETTINGS_FILE = os.path.join(DATASET_DIR, "user_settings.json")
DEFAULT_EDITOR_AUTO_SAVE_INTERVAL_SEC = 300
EDITOR_VIDEO_PLAYER_FIXED_HEIGHT = 420
EDITOR_VIDEO_PLAYER_MIN_WIDTH = 320
EDITOR_VIDEO_PLAYER_16_9_ASPECT = 16 / 9
EDITOR_VIDEO_PLAYER_16_9_TOLERANCE = 0.035
QT_WIDGETSIZE_MAX = 16777215


class EditorWidget(
    EditorSaveManagerMixin,
    EditorActionsMixin,
    EditorPipelineMixin,
    EditorCanvasStateMixin,
    EditorSegmentsMixin,
    EditorAutomationMixin,
    EditorTimelineVideoMixin,
    EditorTabTimingMixin,
    EditorVideoControlsMixin,
    EditorSubtitleAssistMixin,
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
    sig_subtitle_assist_runtime_override_ready = pyqtSignal(object)

    _JUNK_TS_RE               = re.compile(r'[\[{(<\[【（《]\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*[\]})>\]】）》]\s*')
    _JUNK_NO_BRACKET_3PART    = re.compile(r'(?<!\S)\d{1,3}[:\.]\d{2}[:\.]\d{2,3}(?!\S)')
    _JUNK_NO_BRACKET_3PART_END= re.compile(r'\d{1,3}[:\.]\d{2}[:\.]\d{2,3}\s*$')
    _JUNK_START_RE            = re.compile(r'^\s*\d{1,3}[:\.]\d{2}(?:[:\.]\d+)?\s+')
    _auto_start_next = False

    def _auto_save_interval_ms(self) -> int:
        return EditorSaveManagerMixin._auto_save_interval_ms(self)

    def __init__(
        self,
        video_name: str,
        segments: list[dict],
        media_path: str | None = None,
        parent=None,
        defer_media_load: bool = False,
        hydrate_existing_srt_on_empty: bool = True,
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
        self._auto_quality_review_pending = False
        self._auto_quality_review_scheduled = False
        self._auto_quality_review_defer_logged = False
        self._snapshot_undo_revision = None
        self._snapshot_redo_revision = None
        self._home_compact_mode = False
        self._home_compact_timer_state: dict[str, object] = {}
        self.selected_model = self.settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
        self._autosave_requires_manual_save = False

        self.sm = SubtitleStateManager()
        self.sm.current_file = media_path or ""    # ✅ 여기로 이동
        self.sm.sig_ui_update.connect(self._on_state_machine_update)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._on_auto_save)

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
        self._video_context_refresh_timer = QTimer(self)
        self._video_context_refresh_timer.setSingleShot(True)
        self._video_context_refresh_timer.timeout.connect(self._refresh_video_subtitle_context)
        self._cursor_video_seek_timer = QTimer(self)
        self._cursor_video_seek_timer.setSingleShot(True)
        self._cursor_video_seek_timer.timeout.connect(self._flush_cursor_video_seek)
        self._pending_cursor_video_seek_sec: float | None = None
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
        self._init_subtitle_assist_state()
        self.sig_subtitle_assist_runtime_override_ready.connect(self._apply_subtitle_assist_runtime_override)
        self._refresh_subtitle_assist_ui(allow_sync_override=False)
        QTimer.singleShot(120, self._schedule_subtitle_assist_runtime_refresh)
        if hasattr(self, "video_player"):
            self.video_player._repeat_play_prepare_callback = self._prepare_repeat_playback_start
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_app_focus_changed)
        QTimer.singleShot(0, self._hook_multiclip_clip_signals)
        
        self._undo_mgr = UndoManager(self)

        self._highlighter = SubtitleHighlighter(self.text_edit.document())
        self._update_highlighter_colors()
        if hasattr(self.text_edit, "_refresh_gpu_document_overlay_mode"):
            self.text_edit._refresh_gpu_document_overlay_mode()
        self.text_edit.setUndoRedoEnabled(True)

        # 단축키
        self.undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.undo_shortcut.activated.connect(self._route_undo)

        self.redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.redo_shortcut.activated.connect(self._route_redo)

        if not segments and media_path and hydrate_existing_srt_on_empty:
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

        self._segment_cache_valid = False
        self._last_segment_cache_block_count = 0
        self._subtitle_context_window_index_cache = {}
        self._subtitle_context_index_epoch = 0

        self._is_initial_load = True if segments else False
        self._initial_open_view_mode = "window" if segments else "fit"
        if segments:
            self.apply_loaded_canvas_state(
                segments,
                preserve_view=False,
                mark_dirty=False,
            )
            self._schedule_initial_open_layout((0, 160, 360))
            QTimer.singleShot(350, self._mark_initial_segments_saved)

        if media_path and not defer_media_load:
            QTimer.singleShot(200, lambda: self._load_video(media_path))

        self._playhead_timer = QTimer()
        self._playhead_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._playhead_timer.setInterval(self._playhead_active_interval_ms())
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
        was_processing = bool(getattr(self, "_is_ai_processing", False))
        self.current_mode      = mode
        self.current_state     = state
        self._is_ai_processing = is_locked
        self._is_dirty         = is_dirty

        if not is_locked and hasattr(self, "_spinner_timer"):
            try:
                self._spinner_timer.stop()
            except RuntimeError:
                pass
            except Exception:
                pass

        cleaned_btn_txt = self._clean_action_label(btn_txt)
        if hasattr(self, 'status_lbl') and self.status_lbl.text() != lbl_txt:
            self.status_lbl.setText(lbl_txt)
        if hasattr(self, 'btn_start'):
            last_button_signature = getattr(self, "_last_start_button_signature", None)
            button_signature = (cleaned_btn_txt, bool(btn_en))
            if last_button_signature != button_signature:
                self.btn_start.setText(cleaned_btn_txt)
                self.btn_start.setEnabled(btn_en)
                self._last_start_button_signature = button_signature
        main_w = self.window()
        if is_locked and not was_processing and hasattr(main_w, "_lock_workspace_sidebar_width"):
            try:
                main_w._lock_workspace_sidebar_width()
            except Exception:
                pass
        elif not is_locked and was_processing and hasattr(main_w, "_unlock_workspace_sidebar_width"):
            try:
                main_w._unlock_workspace_sidebar_width()
            except Exception:
                pass
        menu_signature = (mode, state, bool(is_locked), bool(is_dirty), cleaned_btn_txt, bool(btn_en))
        if hasattr(main_w, "sync_menu_from_editor") and menu_signature != getattr(self, "_last_menu_sync_signature", None):
            main_w.sync_menu_from_editor(self)
            self._last_menu_sync_signature = menu_signature
        saved_status_signature = (
            bool(is_dirty),
            bool(is_locked),
            bool(state == SubtitleStateManager.ST_SAVED),
        )
        if (
            hasattr(main_w, "_refresh_saved_status_label")
            and saved_status_signature != getattr(self, "_last_saved_status_signature", None)
        ):
            main_w._refresh_saved_status_label(
                is_dirty=is_dirty,
                touch_saved_time=(not is_dirty and state == SubtitleStateManager.ST_SAVED),
            )
            self._last_saved_status_signature = saved_status_signature
        self._apply_text_editor_lock_state()
        self._apply_processing_canvas_lock_state()

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
        doc = getattr(getattr(self, "text_edit", None), "document", lambda: None)()
        current_block_count = int(doc.blockCount()) if doc is not None else 0
        previous_block_count = int(getattr(self, "_last_segment_cache_block_count", current_block_count) or current_block_count)
        text_only_cache_refresh = False
        text_changed = False
        edited_line_num = -1
        if current_block_count == previous_block_count and getattr(self, "_cached_segs", None):
            try:
                block = self.text_edit.textCursor().block()
                data = block.userData()
                if block.isValid() and isinstance(data, SubtitleBlockData):
                    edited_line_num = int(block.blockNumber())
                    text_changed = bool(self._update_subtitle_memory_line_text(edited_line_num, block.text()))
                    if text_changed and hasattr(self, "_apply_manual_confirmed_quality_to_line"):
                        self._apply_manual_confirmed_quality_to_line(
                            edited_line_num,
                            reason="manual_text_edit",
                        )
                    text_only_cache_refresh = bool(getattr(self, "_segment_cache_valid", False))
                else:
                    self._segment_cache_valid = False
            except Exception:
                self._segment_cache_valid = False
        else:
            self._segment_cache_valid = False
        self._last_segment_cache_block_count = current_block_count
        if text_only_cache_refresh and not text_changed:
            try:
                if getattr(self.sm, "is_dirty", False) and hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
                    if hasattr(self, "_mark_save_completed"):
                        self._mark_save_completed(touch_saved_time=False)
                return
            except Exception:
                return
        if not text_only_cache_refresh and hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            if getattr(self.sm, "is_dirty", False) and hasattr(self, "_mark_save_completed"):
                self._mark_save_completed(touch_saved_time=False)
            return
        self._skip_prev_confirm_once = False
        self.sm.start_editing()
        if hasattr(self, "_note_editor_foreground_activity"):
            self._note_editor_foreground_activity()
        if text_only_cache_refresh:
            if text_changed and edited_line_num >= 0 and hasattr(self, "_update_timeline_segment_text_line"):
                self._update_timeline_segment_text_line(edited_line_num, self.text_edit.textCursor().block().text())
            if bool(getattr(self, "_subtitle_text_visibility_changed", False)):
                self._schedule_timeline()
            else:
                self._schedule_video_context_refresh(32)
        else:
            self._schedule_timeline()

    def _schedule_video_context_refresh(self, delay_ms: int = 90):
        timer = getattr(self, "_video_context_refresh_timer", None)
        if timer is None:
            try:
                self._refresh_video_subtitle_context()
            except Exception:
                pass
            return
        timer.start(max(0, int(delay_ms)))

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

    def _apply_initial_open_editor_layout(self):
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return
        prev_sync_lock = bool(getattr(self, "_sync_lock", False))
        try:
            self._sync_lock = True
            doc = text_edit.document()
            first_block = doc.findBlockByNumber(0)
            if first_block.isValid():
                cur = QTextCursor(first_block)
                cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                text_edit.setTextCursor(cur)
        except Exception:
            pass
        finally:
            self._sync_lock = prev_sync_lock
        try:
            bar = text_edit.verticalScrollBar()
            bar.setValue(int(bar.minimum()))
        except Exception:
            pass

    def _schedule_initial_open_layout(self, delays: tuple[int, ...] = (80, 220, 420)):
        timeline = getattr(self, "timeline", None)
        mode = str(getattr(self, "_initial_open_view_mode", "window") or "window").strip().lower()
        normalized_delays = tuple(int(delay) for delay in delays)
        if mode == "fit":
            final_delay = max(normalized_delays[-1] if normalized_delays else 0, 760)
            if final_delay not in normalized_delays:
                normalized_delays = normalized_delays + (final_delay,)
        try:
            if timeline is not None and hasattr(timeline, "schedule_initial_open_view"):
                preferred_seconds = (
                    timeline.preferred_edit_window_seconds()
                    if hasattr(timeline, "preferred_edit_window_seconds")
                    else float(getattr(timeline, "_preferred_edit_window_seconds", 10.0) or 10.0)
                )
                timeline.schedule_initial_open_view(
                    delays=normalized_delays,
                    mode=mode,
                    seconds=preferred_seconds,
                    start_sec=0.0,
                )
            elif timeline is not None and hasattr(timeline, "schedule_time_window_seconds"):
                preferred_seconds = (
                    timeline.preferred_edit_window_seconds()
                    if hasattr(timeline, "preferred_edit_window_seconds")
                    else float(getattr(timeline, "_preferred_edit_window_seconds", 10.0) or 10.0)
                )
                timeline.schedule_time_window_seconds(
                    preferred_seconds,
                    start_sec=0.0,
                    delays=normalized_delays,
                )
        except Exception:
            pass

        def _apply_top_layout():
            try:
                self._apply_initial_open_editor_layout()
            except RuntimeError:
                return

        for delay in tuple(int(delay) for delay in delays):
            QTimer.singleShot(delay, _apply_top_layout)

    def _editor_auto_save_allowed(self) -> bool:
        return EditorSaveManagerMixin._editor_auto_save_allowed(self)

    def _on_auto_save(self):
        return EditorSaveManagerMixin._on_auto_save(self)

    # ---------------------------------------------------------
    # UI 빌드
    # ---------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(2, 2, 2, 2); root.setSpacing(2)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(3)
        self.splitter.setStyleSheet("QSplitter::handle { background: #2D3942; width: 1px; margin: 0 1px; }")
        editor_wrap = StableRenderFrame(
            "EditorTextFrame",
            render_feature="editor",
            min_width=260,
            min_height=260,
        )
        editor_wrap.setStyleSheet("QFrame#EditorTextFrame { background: #151C20; border: none; border-radius: 0px; }")
        self._editor_wrap = editor_wrap
        self.editor_frame = editor_wrap
        editor_wrap.installEventFilter(self)
        ew_layout = editor_wrap.content_layout
        ew_layout.setContentsMargins(8, 8, 8, 8)
        ew_layout.setSpacing(6)

        self.text_edit = SubtitleTextEdit(editor_wrap)
        self.text_edit._parent_widget = self
        self.text_edit.enter_pressed.connect(self._on_enter_pressed)
        self.text_edit.backspace_merged.connect(self._on_backspace_merged)
        self.text_edit.cursor_moved.connect(self._on_cursor_moved)
        self.text_edit.esc_pressed.connect(self._on_esc_pressed)
        self.text_edit.word_selected.connect(self._trigger_editor_popup)
        self.text_edit.tab_pressed.connect(self._trigger_magnet)
        self.text_edit.selectionChanged.connect(self._on_selection_changed)
        self.text_edit.document().contentsChanged.connect(self._on_text_edited)
        self.text_edit.timestamp_clicked.connect(self._on_timeline_seg_clicked)
        self.text_edit.timestamp_deleted.connect(self._on_seg_to_gap)
        self.text_edit.speaker_circle_clicked.connect(self._show_speaker_circle_menu)
        self.text_edit.speaker_circle_dropped.connect(self._on_speaker_circle_dropped)
        try:
            self.text_edit.installEventFilter(self)
            self.text_edit.viewport().installEventFilter(self)
        except Exception:
            pass

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
        # UI LOCK: keep the video player at a fixed editor height. Do not grow
        # this slot to fill spare vertical space or crop/zoom the preview.
        # For 16:9 sources, width is derived from the current preview height
        # below. Do not change this back to splitter-fill behavior.
        video_fixed_height = EDITOR_VIDEO_PLAYER_FIXED_HEIGHT
        self.video_frame = StableRenderFrame(
            "EditorVideoFrame",
            render_feature="video",
            min_width=EDITOR_VIDEO_PLAYER_MIN_WIDTH,
            min_height=video_fixed_height,
            fixed_height=True,
        )
        self.video_frame.setStyleSheet("QFrame#EditorVideoFrame { background: #000000; border: none; border-radius: 0px; }")
        self.video_player = VideoPlayerWidget(self.video_frame)
        self.video_player.setFixedHeight(video_fixed_height)
        if hasattr(self.video_player, "set_subtitle_provider"):
            self.video_player.set_subtitle_provider(self._video_subtitle_context_for_player)
        if hasattr(self.video_player, "frame_step_requested"):
            self.video_player.frame_step_requested.connect(self._on_step_frame)
        if hasattr(self.video_player, "scan_cut_requested"):
            self.video_player.scan_cut_requested.connect(self._on_scan_cut_requested)
        self.video_player.setStyleSheet("background: #000000; border: none; border-radius: 0px;")
        self.video_frame.add_content(self.video_player)
        for widget in (
            self.video_frame,
            self.video_player,
            getattr(self.video_player, "video_container", None),
            getattr(self.video_player, "video_stack", None),
            getattr(self.video_player, "video_widget", None),
            getattr(self.video_player, "thumb_label", None),
            getattr(self.video_player, "_control_bar_widget", None),
            getattr(self.video_player, "time_label", None),
            getattr(self.video_player, "frame_count_label", None),
            getattr(self.video_player, "info_label", None),
            getattr(self.video_player, "source_name_label", None),
        ):
            try:
                if widget is not None:
                    widget.installEventFilter(self)
            except Exception:
                pass
        self.splitter.addWidget(self.video_frame)
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
        QTimer.singleShot(0, self._apply_fixed_video_preview_width)
        QTimer.singleShot(150, self._apply_fixed_video_preview_width)

        self.timeline = TimelineWidget()
        self.timeline.setStyleSheet("background: #151C20; border: 1px solid #2D3942; border-radius: 7px;")
        if hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.show_waveform = True
            self.timeline.canvas.update()
        timeline_scroll = getattr(self.timeline, "scroll", None)
        timeline_scroll_viewport = None
        timeline_scroll_bar = None
        try:
            if timeline_scroll is not None:
                timeline_scroll_viewport = timeline_scroll.viewport()
                timeline_scroll_bar = timeline_scroll.horizontalScrollBar()
        except Exception:
            timeline_scroll_viewport = None
            timeline_scroll_bar = None
        for widget in (
            self.timeline,
            getattr(self.timeline, "canvas", None),
            getattr(self.timeline, "global_canvas", None),
            timeline_scroll,
            timeline_scroll_viewport,
            timeline_scroll_bar,
            getattr(self.timeline, "lock_chk", None),
            getattr(self.timeline, "magnet_btn", None),
            getattr(self.timeline, "repeat_chk", None),
        ):
            try:
                if widget is not None:
                    widget.installEventFilter(self)
            except Exception:
                pass

        # ✅ 여기 딱 한 번만 connect
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'sig_split_request'):
            self.timeline.canvas.sig_split_request.connect(self.split_segment_with_text)
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'sig_speaker_split_request'):
            self.timeline.canvas.sig_speaker_split_request.connect(self.split_speaker_segment_with_text)

        self.timeline.seg_clicked.connect(self._on_timeline_seg_clicked)
        if hasattr(self.timeline, 'stt_candidate_selected'):
            self.timeline.stt_candidate_selected.connect(self.select_stt_candidate_as_subtitle)
        self.timeline.seg_double_clicked.connect(self._on_timeline_seg_double_clicked)
        self.timeline.scrub_sec.connect(self._on_scrub)
        if hasattr(self.timeline, 'drag_preview_sec'): self.timeline.drag_preview_sec.connect(self._on_timing_drag_preview)

        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'seg_right_clicked'):
            self.timeline.canvas.seg_right_clicked.connect(self._on_timeline_seg_right_clicked)
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'speaker_changed'):
            self.timeline.canvas.speaker_changed.connect(self._change_speaker_for_line)
                
        # 멀티클립 전환
        if hasattr(self.timeline, 'sig_clip_selected'): self.timeline.sig_clip_selected.connect(self._on_clip_selected)
        if hasattr(self.timeline, 'seg_time_changed'): self.timeline.seg_time_changed.connect(self._on_seg_time_changed)
        if hasattr(self.timeline, 'seg_timing_confirm_requested'): self.timeline.seg_timing_confirm_requested.connect(self._on_timeline_timing_confirm_requested)
        if hasattr(self.timeline, 'seg_to_gap'):       self.timeline.seg_to_gap.connect(self._on_seg_to_gap)
        if hasattr(self.timeline, 'gap_activated'):    self.timeline.gap_activated.connect(self._on_gap_activated)
        if hasattr(self.timeline, 'gap_to_segs'):      self.timeline.gap_to_segs.connect(self._on_gap_to_segs)
        if hasattr(self.timeline, 'gap_generate_requested'): self.timeline.gap_generate_requested.connect(self._on_gap_generate_requested)
        if hasattr(self.timeline, 'drag_started'):     self.timeline.drag_started.connect(self._on_drag_started)
        if hasattr(self.timeline, 'drag_finished'):    self.timeline.drag_finished.connect(self._on_drag_finished)
        if hasattr(self.timeline, 'step_frame'):       self.timeline.step_frame.connect(self._on_step_frame)
        if hasattr(self.timeline, 'lock_chk'):         self.timeline.lock_chk.toggled.connect(self._on_lock_changed)
        if hasattr(self.timeline, 'repeat_chk'):       self.timeline.repeat_chk.toggled.connect(self._on_repeat_segment_toggled)
        if hasattr(self.timeline, 'subtitle_magnet_requested'): self.timeline.subtitle_magnet_requested.connect(self._on_subtitle_magnet_requested)
        if hasattr(self.timeline, 'tab_timing_requested'): self.timeline.tab_timing_requested.connect(self._trigger_magnet)
        if hasattr(self.timeline, 'diamond_merge'):    self.timeline.diamond_merge.connect(self._on_diamond_merge_requested)
        if hasattr(self.timeline, 'sig_inline_text_changed'): self.timeline.sig_inline_text_changed.connect(self._on_inline_text_changed)
        if hasattr(self.timeline, 'sig_editing_mode'):        self.timeline.sig_editing_mode.connect(self._on_seg_editing_mode)
        if hasattr(self.timeline, 'playhead_menu_requested'): self.timeline.playhead_menu_requested.connect(self._show_playhead_menu)
        if hasattr(self.timeline, 'provisional_cut_boundary_requested'): self.timeline.provisional_cut_boundary_requested.connect(self._on_provisional_cut_boundary_requested)
        if hasattr(self.timeline, 'provisional_cut_boundary_delete_requested'): self.timeline.provisional_cut_boundary_delete_requested.connect(self._on_provisional_cut_boundary_delete_requested)
        if hasattr(self.timeline, 'roughcut_llm_run_requested'): self.timeline.roughcut_llm_run_requested.connect(self._run_manual_roughcut_llm_from_global_canvas)
        if hasattr(self.timeline, 'sig_smart_split'):         self.timeline.sig_smart_split.connect(self._on_smart_split)
            
        timeline_height = max(1, self.timeline.minimumSizeHint().height(), self.timeline.sizeHint().height())
        self._timeline_base_height = timeline_height
        self._timeline_height_bonus = 0
        self._vertical_rebalance_scheduled = False
        self.timeline_frame = StableRenderFrame(
            "EditorTimelineFrame",
            render_feature="timeline",
            min_width=1,
            min_height=timeline_height,
            fixed_height=True,
        )
        self.timeline_frame.setStyleSheet("QFrame#EditorTimelineFrame { background: transparent; border: none; }")
        self.timeline_frame.add_content(self.timeline)
        root.addWidget(self.timeline_frame)
        QTimer.singleShot(0, self._schedule_vertical_rebalance)
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

    def _pause_active_video_playback(self) -> None:
        if not self._is_video_playback_active():
            return
        pause_video = getattr(getattr(self, "video_player", None), "pause_video", None)
        if callable(pause_video):
            try:
                pause_video()
            except Exception:
                pass

    def _pause_playback_for_mouse_press(self) -> None:
        self._pause_active_video_playback()

    def _pause_playback_for_keyboard_edit(self) -> None:
        self._pause_active_video_playback()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and getattr(self, "_scan_cut_state", None):
            video_player = getattr(self, "video_player", None)
            scan_buttons = {
                getattr(video_player, "btn_scan_prev_cut", None),
                getattr(video_player, "btn_scan_next_cut", None),
            }
            if obj not in scan_buttons:
                cancel_scan = getattr(self, "_cancel_scan_cut", None)
                if callable(cancel_scan):
                    cancel_scan("mouse-click-stop")
                    return True
        if event.type() == QEvent.Type.MouseButtonPress:
            self._pause_playback_for_mouse_press()
        if obj is getattr(self, "_editor_wrap", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._sync_editor_focus_border)
        if obj is getattr(self, "_editor_wrap", None) and event.type() == QEvent.Type.Wheel:
            handler = getattr(getattr(self, "text_edit", None), "apply_wheel_scroll_event", None)
            if callable(handler) and handler(event):
                return True
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
        meta = subtitle_block_data_to_meta(ud)
        previous_quality = dict(meta.get("quality") or {})
        next_quality, quality_changed = self._manual_confirmed_quality_for_user_edit(
            previous_quality,
            reason="manual_text_edit",
        )
        history = list(meta.get("quality_history") or [])
        if quality_changed and previous_quality and previous_quality != next_quality:
            history.append(dict(previous_quality))
        meta["quality"] = next_quality
        meta["quality_history"] = history
        if hasattr(self, "_segment_quality_signature"):
            current_seg = self._segment_for_line(int(line_num)) if hasattr(self, "_segment_for_line") else {}
            meta["quality_signature"] = self._segment_quality_signature(
                {
                    "start": meta.get("start_sec", getattr(ud, "start_sec", 0.0)),
                    "end": meta.get("end_sec", (current_seg or {}).get("end", getattr(ud, "start_sec", 0.0))),
                    "text": str(new_text or "").replace("\u2028", "\n"),
                    "speaker": meta.get("spk_id", getattr(ud, "spk_id", "")),
                }
            )
        cur.block().setUserData(subtitle_block_data_from_meta(meta))
        cur.endEditBlock()
        if old_text.count("\u2028") != str(new_text or "").count("\u2028"):
            self.text_edit.update_margins()
            if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._inline_updating = False
        if hasattr(self, "_update_subtitle_memory_line_text"):
            self._update_subtitle_memory_line_text(line_num, new_text)
            if hasattr(self, "_update_subtitle_memory_line_quality"):
                self._update_subtitle_memory_line_quality(
                    line_num,
                    meta.get("quality") or {},
                    quality_history=meta.get("quality_history") or [],
                    quality_signature=meta.get("quality_signature"),
                )
            if hasattr(self, "_update_timeline_segment_quality_line"):
                self._update_timeline_segment_quality_line(
                    line_num,
                    meta.get("quality") or {},
                    quality_signature=meta.get("quality_signature"),
                )
        else:
            cached = getattr(self, "_cached_segs", None)
            visible_text = str(new_text or "").replace("\u2028", "\n")
            if cached is not None:
                for seg in cached:
                        if int(seg.get("line", -999999)) == int(line_num):
                            seg["text"] = visible_text
                            break
        if hasattr(self, "_refresh_visible_quality_map"):
            self._refresh_visible_quality_map()
        self._schedule_video_context_refresh(24)

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
        editor_locked = bool(timeline_locked or processing_locked)
        if hasattr(text_edit, "set_selection_locked"):
            text_edit.set_selection_locked(editor_locked)
        else:
            text_edit.setReadOnly(editor_locked)
        if not timeline_locked and processing_locked and not hasattr(text_edit, "set_selection_locked"):
            text_edit.setReadOnly(True)
            text_edit.setStyleSheet("QTextEdit { background-color: #1a1a1a; color: #888888; }")

    def _apply_processing_canvas_lock_state(self):
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        if canvas is None:
            return
        try:
            processing_locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except RuntimeError:
            return
        except Exception:
            processing_locked = False
        try:
            canvas._editor_processing_input_locked = processing_locked
            canvas.setProperty("editor_processing_input_locked", processing_locked)
        except Exception:
            pass

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
        header.setStyleSheet(f"background: {COLORS['surface_alt']}; border: 1px solid {COLORS['separator']}; border-radius: 6px;")
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
            lbl.setStyleSheet(f"color: {COLORS['muted']}; font-size: 11px; font-weight: 600; background: transparent; border-right: 1px solid {COLORS['separator']};")
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
        bar.setStyleSheet(f"background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; border-radius: 7px;")
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
        self.btn_subtitle_why = QPushButton("근거")
        self.btn_subtitle_why.setToolTip("현재 자막의 LoRA/STT/LLM/컷 경계 선택 근거")
        self.btn_subtitle_why.setStyleSheet(button_style("toolbar", font_size="11px", padding="5px 9px"))
        self.btn_subtitle_why.clicked.connect(self._show_subtitle_why_for_current_line)
        row.addWidget(self.btn_subtitle_why)
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
        self._quality_review_running = bool(running)
        if hasattr(self, "btn_quality_review"):
            self.btn_quality_review.setEnabled(not running)
            self.btn_quality_review.setText("검사 중" if running else "검사")
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText("에디터 | 검사 중" if running else "에디터 | 검사 완료")

    def _is_video_playback_active(self) -> bool:
        try:
            player = getattr(getattr(self, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _schedule_auto_quality_review(self, delay_ms: int = 900) -> None:
        self._auto_quality_review_pending = True
        if bool(getattr(self, "_auto_quality_review_scheduled", False)):
            return
        self._auto_quality_review_scheduled = True
        QTimer.singleShot(max(0, int(delay_ms)), self._run_scheduled_auto_quality_review)

    def _run_scheduled_auto_quality_review(self) -> None:
        self._auto_quality_review_scheduled = False
        if not bool(getattr(self, "_auto_quality_review_pending", False)):
            return
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        try:
            recent_activity_at = float(getattr(self, "_last_editor_foreground_activity_at", 0.0) or 0.0)
            defer_after_edit_sec = float(self.settings.get("subtitle_quality_defer_after_edit_sec", 4.0) or 4.0)
            recent_editor_activity = recent_activity_at > 0.0 and (time.monotonic() - recent_activity_at) < max(0.25, defer_after_edit_sec)
        except Exception:
            recent_editor_activity = False
        playback_active = self._is_video_playback_active()
        if locked or playback_active or recent_editor_activity:
            if playback_active and not bool(getattr(self, "_auto_quality_review_defer_logged", False)):
                self._auto_quality_review_defer_logged = True
                get_logger().log("[자막 품질] 재생 중이라 자동 품질 검사를 잠시 미룹니다.")
            self._auto_quality_review_scheduled = True
            delay_ms = 1800 if playback_active else 1200 if recent_editor_activity else 700
            QTimer.singleShot(delay_ms, self._run_scheduled_auto_quality_review)
            return
        self._auto_quality_review_pending = False
        self._auto_quality_review_defer_logged = False
        self._run_quality_review(auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False)))

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
            self._auto_quality_review_pending = False
            self._auto_quality_review_defer_logged = False
            try:
                restorer = getattr(self.window(), "_restore_normal_cursor", None)
                if callable(restorer):
                    restorer(self)
            except Exception:
                pass
            try:
                if bool(getattr(self, "_generation_completion_autosave_pending", False)):
                    scheduler = getattr(self, "_schedule_generation_completion_autosave", None)
                    if callable(scheduler):
                        scheduler(delay_ms=0)
            except Exception:
                pass

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

    def _show_subtitle_why_for_current_line(self):
        from ui.editor.subtitle_why_dialog import SubtitleWhyDialog

        line = self.text_edit.textCursor().blockNumber()
        seg = self._segment_for_line(line)
        if not seg:
            QMessageBox.information(self, "생성 근거", "현재 줄에서 확인할 자막을 찾지 못했습니다.")
            return
        dialog = SubtitleWhyDialog(seg, index=line, parent=self)
        if dialog.exec() == 1 and getattr(dialog, "selected_action", ""):
            self._handle_one_click_fix_action(line, str(dialog.selected_action))

    def _handle_one_click_fix_action(self, line: int, action: str):
        from core.engine.subtitle_one_click_fix import (
            build_one_click_fix_request,
            reapply_similar_subtitle_style,
            subtitle_source_text_without_llm,
        )

        seg = self._segment_for_line(int(line)) or {}
        if not seg:
            return
        if action == "restore_source_no_llm":
            restored = subtitle_source_text_without_llm(seg)
            if not restored:
                QMessageBox.information(self, "원문 복구", "복구할 원문/STT 후보가 없습니다.")
                return
            self._replace_segment_text_by_line(
                int(line),
                restored,
                {"candidate_id": action, "source": "one_click_fix", "reason": "LLM 없이 원문 기준 복구"},
            )
            return
        if action == "reapply_similar_style":
            updated, meta = reapply_similar_subtitle_style(str(seg.get("text", "") or ""), getattr(self, "settings", {}) or {})
            if not updated or updated == str(seg.get("text", "") or ""):
                QMessageBox.information(self, "스타일 재적용", str(meta.get("reason") or "적용할 유사 스타일을 찾지 못했습니다."))
                return
            self._replace_segment_text_by_line(
                int(line),
                updated,
                {"candidate_id": action, "source": "one_click_fix", "reason": str(meta.get("reason") or "비슷한 자막 스타일 재적용")},
            )
            return
        request = build_one_click_fix_request(action, seg, reason="one_click_fix")
        if action == "re_recognize_region" and hasattr(self, "_re_recognize_segment"):
            self._re_recognize_segment(float(seg.get("start", 0.0) or 0.0))
            return
        if action == "recheck_cut_only":
            try:
                if hasattr(self, "video_player") and hasattr(self.video_player, "seek"):
                    self.video_player.seek(float(seg.get("start", 0.0) or 0.0))
                if hasattr(self, "_on_scan_cut_requested"):
                    self._on_scan_cut_requested(1)
                    return
            except Exception:
                pass
        self._mark_one_click_fix_request(int(line), request)
        QMessageBox.information(self, "빠른 수정", f"{request.get('label')} 요청을 현재 자막에 표시했습니다.")

    def _mark_one_click_fix_request(self, line: int, request: dict):
        for seg in list(getattr(self, "_cached_segs", []) or []):
            if int(seg.get("line", -1) or -1) == int(line):
                seg["_one_click_fix_request"] = dict(request)
                quality = dict(seg.get("quality") or {})
                flags = list(quality.get("flags") or [])
                if "one_click_fix_requested" not in flags:
                    flags.append("one_click_fix_requested")
                quality["flags"] = flags
                quality["one_click_fix_request"] = dict(request)
                seg["quality"] = quality
                break
        self._mark_dirty()

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
        previous_quality = dict(quality)
        flags = list(quality.get("flags") or [])
        if "candidate_applied" not in flags:
            flags.append("candidate_applied")
        quality["flags"] = flags
        quality["candidate_applied_reason"] = str((candidate or {}).get("reason", "") or "")
        quality, quality_changed = self._manual_confirmed_quality_for_user_edit(
            quality,
            reason="manual_text_edit",
        )
        history = list(getattr(data, "quality_history", []) or [])
        if quality_changed and previous_quality and previous_quality != quality:
            history.append(dict(previous_quality))
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
                quality_history=history,
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
        for idx, row_data in enumerate(visible_speaker_slots(speaker_settings), start=1):
            color = str(row_data.get("color", colors[min(idx - 1, len(colors) - 1)]) or colors[min(idx - 1, len(colors) - 1)])
            name = str(row_data.get("name", "") or f"화자 {idx}")
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
        self._top_btns = [
            ("ai",      self.btn_ai,  "⚙️ AI",      "AI",      self._show_settings),
            ("speaker", self.btn_spk, "🗣️ 화자",    "화자",     self._show_speaker_settings),
            ("gap",     self.btn_gap, "⏱️ 간격",    "간격",     self._show_gap_settings),
            ("video",   self.btn_vid, "🎬 비디오",  "비디오",   self._toggle_video),
        ]
        self._footer_menu_buttons = {menu_id: btn for menu_id, btn, *_rest in self._top_btns}
        self._active_footer_menu_id = ""
        for menu_id, btn, _full_t, _comp_t, slot in self._top_btns:
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.clicked.connect(
                lambda _checked=False, item_id=menu_id, action=slot: self._invoke_footer_menu_action(
                    item_id,
                    action,
                    transient=(item_id != "video"),
                )
            )
            btn_row.addWidget(btn)
        self._apply_footer_menu_button_styles(force=True)
        self._sync_footer_menu_button_states()
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

    def _footer_menu_button_style(self, *, font_size: str = "11px", padding: str = "6px 8px") -> str:
        return (
            "QPushButton { "
            f"background: {COLORS['control']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['separator']}; padding: {padding}; "
            f"font-size: {font_size}; border-radius: 8px; min-height: 28px; min-width: 64px; "
            "} "
            f"QPushButton:hover {{ background: {COLORS['control_hover']}; border-color: #5A6A76; color: #FFFFFF; }} "
            f"QPushButton:checked {{ background: #1F3A56; border-color: {COLORS['primary']}; color: #D7EBFF; }} "
            "QPushButton:hover:checked { background: #24496B; border-color: #74A9FF; color: #F5FBFF; } "
            "QPushButton:pressed { background: #182830; border-color: #D7EBFF; padding-top: 6px; padding-bottom: 6px; } "
            "QPushButton:disabled { color: #6F767D; background: #151A1E; border-color: #222A31; }"
        )

    def _apply_footer_menu_button_styles(self, *, force: bool = False):
        profile = responsive_profile_for_size(self.width(), self.height())
        is_compact = self.width() < profile.editor_compact_width
        top_font = "10px" if is_compact else "11px"
        signature = (bool(is_compact), str(top_font))
        if not force and signature == getattr(self, "_last_footer_menu_style_signature", None):
            return

        style = self._footer_menu_button_style(font_size=top_font, padding="6px 8px")
        for _menu_id, btn, full_t, comp_t, _slot in getattr(self, "_top_btns", []):
            btn.setText(comp_t if is_compact else full_t)
            btn.setStyleSheet(style)
        for btn, full_t, comp_t, _slot in getattr(self, "_bot_btns", []):
            if btn != getattr(self, "btn_start", None):
                btn.setText(comp_t if is_compact else full_t)
        self._last_footer_menu_style_signature = signature

    def _sync_footer_menu_button_states(self):
        buttons = dict(getattr(self, "_footer_menu_buttons", {}) or {})
        if not buttons:
            return
        active_id = str(getattr(self, "_active_footer_menu_id", "") or "")
        video_player = getattr(self, "video_player", None)
        try:
            video_visible = bool(video_player is not None and video_player.isVisible())
        except Exception:
            video_visible = False
        for menu_id, btn in buttons.items():
            checked = bool(menu_id == active_id)
            if menu_id == "video" and video_visible:
                checked = True
            try:
                if btn.isChecked() != checked:
                    btn.setChecked(checked)
                btn.update()
            except Exception:
                pass

    def _invoke_footer_menu_action(self, menu_id: str, callback, *, transient: bool = True):
        if transient:
            self._active_footer_menu_id = str(menu_id or "")
            self._sync_footer_menu_button_states()
            try:
                btn = (getattr(self, "_footer_menu_buttons", {}) or {}).get(menu_id)
                if btn is not None:
                    btn.repaint()
                QApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                    | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers,
                    1,
                )
            except Exception:
                pass
        try:
            return callback()
        finally:
            if transient:
                self._active_footer_menu_id = ""
                self._sync_footer_menu_button_states()

    def _clean_action_label(self, text: str) -> str:
        label = str(text or "")
        for token in ("🧠", "▶", "🔄", "⏳", "⌛", "💾", "🎥", "■"):
            label = label.replace(token, "")
        return label.strip() or "시작"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_video_expand_button)
        QTimer.singleShot(0, self._apply_fixed_video_preview_width)
        QTimer.singleShot(0, self._sync_editor_focus_border)
        QTimer.singleShot(0, self._schedule_vertical_rebalance)
        self._apply_footer_menu_button_styles()

    def _position_video_expand_button(self):
        return

    def _apply_fixed_video_preview_width(self):
        frame = getattr(self, "video_frame", None)
        player = getattr(self, "video_player", None)
        if frame is None or player is None:
            return

        if not self._video_source_is_16_9():
            self._set_video_preview_width_lock(None)
            return

        preview_height = self._video_fixed_height()
        layout_margin_width = 0
        try:
            margins = player.layout().contentsMargins()
            layout_margin_width = int(margins.left()) + int(margins.right())
        except Exception:
            layout_margin_width = 0
        target_width = max(
            EDITOR_VIDEO_PLAYER_MIN_WIDTH,
            int(round(preview_height * EDITOR_VIDEO_PLAYER_16_9_ASPECT)) + layout_margin_width,
        )
        self._set_video_preview_width_lock(target_width)

    def _video_source_aspect(self):
        player = getattr(self, "video_player", None)
        if player is None:
            return EDITOR_VIDEO_PLAYER_16_9_ASPECT
        try:
            source_width = int(getattr(player, "_source_width", 0) or 0)
            source_height = int(getattr(player, "_source_height", 0) or 0)
            if source_width > 0 and source_height > 0:
                return source_width / source_height
        except Exception:
            pass
        try:
            return float(getattr(player, "_source_aspect", EDITOR_VIDEO_PLAYER_16_9_ASPECT) or EDITOR_VIDEO_PLAYER_16_9_ASPECT)
        except Exception:
            return EDITOR_VIDEO_PLAYER_16_9_ASPECT

    def _video_source_is_16_9(self):
        aspect = self._video_source_aspect()
        return abs(aspect - EDITOR_VIDEO_PLAYER_16_9_ASPECT) <= EDITOR_VIDEO_PLAYER_16_9_TOLERANCE

    def _set_video_preview_width_lock(self, target_width):
        frame = getattr(self, "video_frame", None)
        player = getattr(self, "video_player", None)
        if frame is None or player is None:
            return

        if target_width is None:
            if not bool(getattr(self, "_video_width_locking", False)):
                return
            self._video_width_locking = False
            self._video_width_lock_value = 0
            for widget in (frame, player):
                try:
                    widget.setMinimumWidth(EDITOR_VIDEO_PLAYER_MIN_WIDTH)
                    widget.setMaximumWidth(QT_WIDGETSIZE_MAX)
                    policy = widget.sizePolicy()
                    widget.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())
                    widget.updateGeometry()
                except Exception:
                    pass
            return

        target_width = max(EDITOR_VIDEO_PLAYER_MIN_WIDTH, int(target_width))
        if (
            bool(getattr(self, "_video_width_locking", False))
            and int(getattr(self, "_video_width_lock_value", 0) or 0) == target_width
        ):
            return
        self._video_width_locking = True
        self._video_width_lock_value = target_width

        # UI LOCK: 16:9 video preview is height-owned. The editor keeps the
        # current fixed preview height and derives width as height * 16:9.
        # Do not change this to auto-fill/auto-zoom; it reintroduces the
        # oversized player regression marked in live UI QA.
        for widget in (frame, player):
            try:
                widget.setFixedWidth(target_width)
                policy = widget.sizePolicy()
                widget.setSizePolicy(QSizePolicy.Policy.Fixed, policy.verticalPolicy())
                widget.updateGeometry()
            except Exception:
                pass
        try:
            self.updateGeometry()
        except Exception:
            pass

    def _video_fixed_height(self):
        try:
            return max(1, self.video_player.video_container.height())
        except Exception:
            return max(1, self.video_player.height() - 56)

    def _schedule_vertical_rebalance(self):
        if bool(getattr(self, "_vertical_rebalance_scheduled", False)):
            return
        self._vertical_rebalance_scheduled = True
        QTimer.singleShot(0, self._rebalance_video_timeline_heights)

    def _rebalance_video_timeline_heights(self):
        self._vertical_rebalance_scheduled = False
        # UI LOCK: video/timeline heights are fixed; do not auto-redistribute
        # letterbox space by enlarging or shrinking the video preview.
        self._timeline_height_bonus = 0
        self._vertical_rebalance_followups = 0
        timeline = getattr(self, "timeline", None)
        timeline_frame = getattr(self, "timeline_frame", None)
        if timeline is None or timeline_frame is None:
            return
        try:
            if hasattr(timeline, "set_canvas_height_bonus"):
                timeline.set_canvas_height_bonus(0)
        except Exception:
            pass
        timeline.updateGeometry()
        timeline_frame.updateGeometry()
        self.updateGeometry()

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _update_highlighter_colors(self):
        cmap = {
            self.settings.get("spk1_id", "00"): self.settings.get("spk1_color", "#FFFFFF"),
            self.settings.get("spk2_id", "01"): self.settings.get("spk2_color", COLORS["warning"]),
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

    def _force_ui_log(self, msg: str): get_logger().log(msg)

    def enter_home_compact_mode(self) -> None:
        if bool(getattr(self, "_home_compact_mode", False)):
            return
        self._home_compact_mode = True
        self._home_compact_timer_state = {
            "auto_save_active": bool(getattr(self._auto_save_timer, "isActive", lambda: False)()),
            "status_anim_active": bool(getattr(self._status_anim_timer, "isActive", lambda: False)()),
            "playhead_active": bool(getattr(self._playhead_timer, "isActive", lambda: False)()),
            "video_context_refresh_active": bool(getattr(self._video_context_refresh_timer, "isActive", lambda: False)()),
        }
        for attr in (
            "_playhead_timer",
            "_queue_timer",
            "_timeline_timer",
            "_spinner_timer",
            "_nav_timer",
            "_auto_save_timer",
            "_status_anim_timer",
            "_video_context_refresh_timer",
            "_live_editor_preview_timer",
            "_cursor_video_seek_timer",
            "_roughcut_draft_timer",
        ):
            timer = getattr(self, attr, None)
            try:
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
        timeline = getattr(self, "timeline", None)
        compact_timeline = getattr(timeline, "compact_for_home_navigation", None) if timeline is not None else None
        if callable(compact_timeline):
            compact_timeline()
        video_player = getattr(self, "video_player", None)
        compact_video = getattr(video_player, "compact_for_home_navigation", None) if video_player is not None else None
        if callable(compact_video):
            compact_video()

    def leave_home_compact_mode(self) -> None:
        state = dict(getattr(self, "_home_compact_timer_state", {}) or {})
        if not bool(getattr(self, "_home_compact_mode", False)) and not state:
            return
        self._home_compact_mode = False
        self._home_compact_timer_state = {}
        owner = self.window()
        multiclip_boundaries = list(getattr(owner, "_multiclip_boundaries", []) or []) if owner is not None else []
        timeline = getattr(self, "timeline", None)
        restore_timeline = getattr(timeline, "restore_after_home_navigation", None) if timeline is not None else None
        if callable(restore_timeline):
            restore_timeline(
                waveform_path=str(getattr(self, "media_path", "") or ""),
                multiclip_boundaries=multiclip_boundaries,
            )
        video_player = getattr(self, "video_player", None)
        restore_video = getattr(video_player, "restore_after_navigation", None) if video_player is not None else None
        if callable(restore_video):
            restore_video()
        try:
            if bool(state.get("auto_save_active", False)):
                self._auto_save_timer.start(self._auto_save_interval_ms())
        except Exception:
            pass
        try:
            if bool(state.get("status_anim_active", False)):
                self._status_anim_timer.start(400)
        except Exception:
            pass
        try:
            if bool(state.get("playhead_active", False)):
                self._playhead_timer.start(self._playhead_active_interval_ms())
        except Exception:
            pass
        try:
            if bool(state.get("video_context_refresh_active", False)):
                self._video_context_refresh_timer.start(0)
        except Exception:
            pass

    def _update_engine_label_text(self):
        short_w = self.settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "")).replace("mlx-community/", "").replace("-mlx", "") or "기본"
        if self.settings.get("stt_ensemble_enabled"):
            short_w2 = str(self.settings.get("selected_whisper_model_secondary", "") or "").replace("mlx-community/", "").replace("-mlx", "")
            if short_w2 and short_w2 != short_w:
                short_w = f"{short_w} + {short_w2}"
        audio_ai = audio_filter_display_name(self.settings)
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
            '_spinner_timer', '_nav_timer', '_auto_save_timer', '_status_anim_timer',
            '_video_context_refresh_timer'
        ]
        for attr in timers:
            t = getattr(self, attr, None)
            if t and t.isActive(): 
                t.stop()
                
        if hasattr(self, 'video_player'): 
            try:
                self.video_player.pause_video()
            except (AttributeError, RuntimeError, TypeError) as exc:
                get_logger().log(f"⚠️ 에디터 cleanup 중 비디오 정지 실패: {exc}")
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
                self.timeline.canvas.sig_split_request.disconnect(self.split_segment_with_text)
            if hasattr(self, 'timeline'):
                self.timeline.sig_inline_text_changed.disconnect(self._on_inline_text_changed)
        except (TypeError, RuntimeError):
            pass

    def _toggle_focus(self):
        if self.text_edit.hasFocus():
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'): self.timeline.canvas.setFocus()
            elif hasattr(self, 'timeline'): self.timeline.setFocus()
        else: self.text_edit.setFocus()
