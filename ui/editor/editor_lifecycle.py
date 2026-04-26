# Version: 02.03.00
# Phase: PHASE1-B
"""
ui/editor_lifecycle.py
MainWindow 에디터 열기/저장/닫기 Mixin
"""
import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor

import config
from logger import get_logger
from core.path_manager import get_srt_path
from core.project.project_manager import load_project


def _save_srt_impl(srt_path, segments):
    import os
    from logger import get_logger

    if not segments:
        get_logger().log('❌ 빈 세그먼트라 SRT 저장을 건너뜁니다.')
        return

    def _fmt(sec: float) -> str:
        total_ms = int(round(float(sec) * 1000.0))
        h = total_ms // 3600000
        m = (total_ms % 3600000) // 60000
        s = (total_ms % 60000) // 1000
        ms = total_ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    try:
        out_dir = os.path.dirname(srt_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        # 빈 텍스트 / gap 세그먼트 필터링
        filtered = [s for s in segments if not s.get('is_gap') and str(s.get('text', '') or '').strip()]
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(filtered, 1):
                f.write(f"{i}\n")
                f.write(f"{_fmt(seg.get('start', 0.0))} --> {_fmt(seg.get('end', 0.0))}\n")
                f.write(f"{str(seg.get('text', '') or '').strip()}\n\n")
        get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")
    except Exception as e:
        get_logger().log(f"❌ SRT 저장 실패: {e}")


class EditorLifecycleMixin:

    def _open_srt_in_editor(self, srt_path):
        from core.srt_parser import parse_srt
        segments = parse_srt(srt_path)
        from ui.editor.editor_widget import EditorWidget
        self._remove_old_editor()
        base_path = os.path.splitext(srt_path)[0]; media_extensions = ['.mp4', '.mov', '.MOV', '.MP4', '.wav', '.m4a', '.m2a', '.mp3', '.aac']
        media_path = next((base_path + ext for ext in media_extensions if os.path.exists(base_path + ext)), srt_path)
        editor = EditorWidget(video_name=os.path.basename(srt_path), segments=segments, media_path=media_path, parent=self)
        editor._project_clips = None
        def _save_and_home(segs=None):
            if segs is not None: _save_srt_impl(srt_path, segs)
            QTimer.singleShot(0, self.show_home)
        editor.sig_save.connect(lambda segs, p=srt_path: _save_srt_impl(p, segs)); editor.sig_auto_save.connect(lambda segs, p=srt_path: _save_srt_impl(p, segs)); editor.sig_next.connect(_save_and_home); editor.sig_exit.connect(lambda _: self.close())
        self._editor_widget = editor
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        if hasattr(editor, 'timeline') and self._project_boundary_times: editor.timeline.set_boundary_times(self._project_boundary_times)
        self.stack.insertWidget(1, editor); self.stack.setCurrentIndex(1)
        if self._current_project_path:
            self._restore_workspace(editor, self._current_project_path)
            from core.project.project_phase1b import apply_project_ui_state
            apply_project_ui_state(self, editor, self._current_project_path)

    def _finalize_reuse_completion(self, editor):
        """기존자막 reuse 완료 후 상태 전환"""
        try:
            if hasattr(editor, '_set_process_completed'):
                editor._set_process_completed()
            if hasattr(editor, '_redraw_timeline'):
                editor._redraw_timeline()
            if hasattr(editor, 'timeline'):
                editor.timeline.fit_to_view()
        except Exception as e:
            from logger import get_logger
            get_logger().log(f'⚠️ reuse 완료 상태 전환 실패: {e}')

    def _init_editor(self, target_file, is_batch=False):
        from ui.editor.editor_widget import EditorWidget
        vname = os.path.basename(target_file); self._remove_old_editor()
        editor = EditorWidget(video_name=vname, segments=[], media_path=target_file, parent=self)
        editor.is_auto_start = is_batch; self._editor_widget = editor

        editor._project_clips = None
        if self._current_project_path and self.backend:
            n_files = len(getattr(self.backend, 'files_to_process', []))
            if n_files > 1:
                pd = load_project(self._current_project_path)
                if pd and "timeline" in pd:
                    clips = pd["timeline"].get("tracks", [{}])[0].get("clips", [])
                    if len(clips) > 1: editor._project_clips = clips

        if is_batch: editor.sm.init_auto_state()
        else: editor.sm.init_state()
        if hasattr(editor, 'btn_start'): editor.btn_start.setText("🧠 시작")
        
        # 멀티클립 박스 전달
        if hasattr(self, '_multiclip_boundaries') and self._multiclip_boundaries:

            boxes = []
            for i, bd in enumerate(self._multiclip_boundaries):
                boxes.append({
                    "start": bd["start"],
                    "end": bd["end"],
                    "index": i + 1,
                    "name": bd.get("name", ""),
                    "file": bd.get("file", "")   # ← 추가
                })

            total_dur = self._multiclip_boundaries[-1]["end"]

            # 메인 캔버스
            editor.timeline.canvas._multiclip_boxes = boxes
            editor.timeline.canvas._active_clip_idx = 0
            editor.timeline.canvas.boundary_times = [bd["end"] for bd in self._multiclip_boundaries[:-1]]
            editor.timeline.canvas.total_duration = total_dur
            # 줌을 전체 클립이 딱 맞도록 설정
            scroll_w = max(200, self.width() - 40)
            editor.timeline.canvas.pps = scroll_w / total_dur
            editor.timeline.canvas.setMinimumWidth(int(total_dur * editor.timeline.canvas.pps) + 20)

            # 글로벌 캔버스
            gc = editor.timeline.global_canvas
            gc.total_duration = total_dur
            gc._multiclip_boxes = boxes
            gc._active_clip_idx = 0
            gc.segments = []
            try:
                self._active_clip_idx = 0
            except Exception:
                pass
            try:
                if boxes:
                    editor.timeline._selected_clip_idx = 0
                    editor.timeline._selected_clip_offset = float(boxes[0].get('start', 0.0))
                    editor.timeline._selected_clip_duration = max(0.001, float(boxes[0].get('end', 0.0)) - float(boxes[0].get('start', 0.0)))
                    editor.timeline._selected_clip_label = str(boxes[0].get('index', 1))
                    gc.set_clip_label(editor.timeline._selected_clip_label)
                else:
                    editor.timeline._selected_clip_label = ''
                    gc.set_clip_label('')
            except Exception:
                pass
            gc.update()

            editor.timeline.canvas.update()
            editor.timeline.load_multiclip_waveform(self._multiclip_boundaries)

            # PHASE1-B: 에디터 진입 직후 기존 자막 사전 로드
            # backend에서만 reuse flag 읽기 (stale self 값 무시)
            _reuse_flag = getattr(getattr(self, 'backend', None), '_reuse_existing_multiclip_subtitles', False)
            if _reuse_flag is True:
                for _ri, _bd in enumerate(self._multiclip_boundaries):
                    _rf = _bd.get('file', '')
                    _rsrt = os.path.splitext(_rf)[0] + '.srt' if _rf else ''
                    if _rsrt and os.path.exists(_rsrt):
                        try:
                            from core.srt_parser import parse_srt
                            _rsegs = parse_srt(_rsrt)
                            if _rsegs:
                                _roff = float(_bd.get('start', 0.0))
                                for _s in _rsegs:
                                    _s['start'] = float(_s.get('start', 0.0)) + _roff
                                    _s['end'] = float(_s.get('end', 0.0)) + _roff
                                    _s['_clip_idx'] = _ri
                                    if 'speaker' not in _s:
                                        _s['speaker'] = _s.get('spk_id', '00')
                                editor.append_segments(_rsegs)
                                try:
                                    _backend = getattr(self, 'backend', None)
                                    if _backend is not None:
                                        if not hasattr(_backend, '_reuse_clip_indices'):
                                            _backend._reuse_clip_indices = set()
                                        _backend._reuse_clip_indices.add(_ri)
                                    if not hasattr(self, '_reuse_clip_indices'):
                                        self._reuse_clip_indices = set()
                                    self._reuse_clip_indices.add(_ri)
                                except Exception:
                                    pass
                                get_logger().log(f'  [PRE] 기존 자막 사전 로드: {os.path.basename(_rf)} ({len(_rsegs)}개)')
                                if hasattr(self, '_sig_update_queue'):
                                    self._sig_update_queue.emit(_ri, '✅기존자막', ' - ', '', '')
                        except Exception as _re:
                            get_logger().log(f'  [PRE] 기존 자막 사전 로드 실패: {os.path.basename(_rf)} / {_re}')
                # reuse 완료 → 완료 상태 전환 (버튼 "재시작"으로)
                try:
                    _reuse_count = len(getattr(self, '_reuse_clip_indices', set()) or set())
                    _total_count = len(self._multiclip_boundaries)
                    if _total_count > 0 and _reuse_count >= _total_count and hasattr(self, '_sig_update_queue_header'):
                        self._sig_update_queue_header.emit(_total_count, _total_count, 100, '')
                except Exception:
                    pass
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, lambda: self._finalize_reuse_completion(editor))
            
        if is_batch: QTimer.singleShot(600, lambda e=editor: e.btn_start.click() if hasattr(e, 'btn_start') else None)

        def safe_home(*args):
                        from PyQt6.QtCore import QTimer as _QT
                        _QT.singleShot(0, self.show_home)
        def force_exit_app(*args): self.close()
        def handle_prev(*args):
            if self._on_prev_cb: self._on_prev_cb()
            safe_home()

        if self._on_start_cb: editor.sig_start.connect(self._on_start_cb)
        editor.sig_prev.connect(handle_prev); editor.sig_exit.connect(force_exit_app)
        if self._on_save_cb: editor.sig_next.connect(self._on_save_cb)
        else: editor.sig_next.connect(safe_home)
        srt_save_path = get_srt_path(target_file)
        editor.sig_save.connect(lambda segs, p=srt_save_path: _save_srt_impl(p, segs))
        editor.sig_auto_save.connect(lambda segs, p=srt_save_path: _save_srt_impl(p, segs))
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        self.stack.insertWidget(1, editor)
        if hasattr(editor, 'timeline'): editor.timeline.set_boundary_times(self._project_boundary_times or [])
        self.stack.setCurrentIndex(1)
        if self._current_project_path:
            self._restore_workspace(editor, self._current_project_path)
            from core.project.project_phase1b import apply_project_ui_state
            apply_project_ui_state(self, editor, self._current_project_path)

    def _remove_old_editor(self):
        old = self.stack.widget(1)
        if not old:
            return
        if hasattr(old, '_cleanup'):
            try: old._cleanup()
            except: pass
        if hasattr(old, 'video_player'):
            try:
                vp = old.video_player
                if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                if hasattr(vp, '_worker') and getattr(vp, '_worker', None): vp._worker.stop(); vp._worker.wait(200)
            except: pass
        try:
            self.stack.removeWidget(old)
            old.hide()
        except RuntimeError:
            return
        if not hasattr(self, '_trash_bin'):
            self._trash_bin = []
        self._trash_bin.append(old)
        while len(self._trash_bin) > 3:
            widget = self._trash_bin.pop(0)
            try:
                widget.deleteLater()
            except (RuntimeError, AttributeError):
                pass


    def _backup_srt(self, srt_path, segments):
        try:
            from core.engine.subtitle_engine import save_srt; import datetime
            base = os.path.splitext(os.path.basename(srt_path))[0]; date_str = datetime.date.today().strftime("%Y%m%d"); num = self._backup_nums.get(srt_path, 1)
            backup_dir = os.path.join(os.path.dirname(srt_path), "자막백업"); os.makedirs(backup_dir, exist_ok=True)
            save_srt(segments, os.path.join(backup_dir, f"{base}_{date_str}_{num:03d}.srt"), apply_offset=False)
        except Exception as e: get_logger().log(f"⚠️ 백업 저장 실패: {e}")

    def closeEvent(self, event):
        if self._editor_widget and self.stack.currentIndex() == 1:
            if hasattr(self._editor_widget, 'sm') and self._editor_widget.sm.is_locked:
                if hasattr(self._editor_widget, '_stop_pipeline'):
                    self._editor_widget._stop_pipeline()

            if getattr(self._editor_widget, '_skip_prev_confirm_once', False):
                self._editor_widget._skip_prev_confirm_once = False
                event.accept()
            else:
                is_dirty = False
                try:
                    if hasattr(self._editor_widget, 'sm'):
                        is_dirty = bool(self._editor_widget.sm.is_dirty)
                except Exception:
                    pass

                if is_dirty:
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("종료 확인")
                    msg_box.setText("저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?")
                    msg_box.setStandardButtons(
                        QMessageBox.StandardButton.Yes |
                        QMessageBox.StandardButton.No |
                        QMessageBox.StandardButton.Cancel
                    )
                    msg_box.button(QMessageBox.StandardButton.Yes).setText("예")
                    msg_box.button(QMessageBox.StandardButton.No).setText("아니요")
                    msg_box.button(QMessageBox.StandardButton.Cancel).setText("취소")
                    reply = msg_box.exec()

                    if reply == QMessageBox.StandardButton.Yes:
                        if hasattr(self._editor_widget, '_on_save'):
                            self._editor_widget._on_save()
                        event.accept()
                    elif reply == QMessageBox.StandardButton.No:
                        event.accept()
                    else:
                        event.ignore()
                        return
                else:
                    event.accept()
        else:
            event.accept()

        get_logger().clear_ui_callback()
        self.blockSignals(True)
        if self._editor_widget and hasattr(self._editor_widget, 'video_player'):
            try:
                vp = self._editor_widget.video_player
                if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                if hasattr(vp, '_worker') and vp._worker:
                    vp._worker.stop()
                    vp._worker.wait(200)
            except: pass
        if self.backend: self.backend.stop()
        QTimer.singleShot(100, lambda: os._exit(0))


