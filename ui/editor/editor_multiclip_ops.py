# Version: 03.14.05
# Phase: PHASE2
"""
EditorWidget 멀티클립 파일 추가/삭제/리매핑 Mixin.
"""
import os


class EditorMulticlipOpsMixin:
    def _normalize_multiclip_segment_order(self, segs):
        ordered = sorted(
            (dict(seg) for seg in (segs or [])),
            key=lambda s: (
                float(s.get('start', 0.0) or 0.0),
                float(s.get('end', 0.0) or 0.0),
            ),
        )
        for i, seg in enumerate(ordered):
            seg['line'] = i
        return ordered

    def _collect_existing_clip_segments(self, file_path, offset, clip_idx=None):
        segs = []
        base = os.path.splitext(file_path)[0]
        srt_path = base + '.srt'
        if os.path.exists(srt_path):
            try:
                from core.srt_parser import parse_srt
                for seg in parse_srt(srt_path):
                    item = {
                        'start': float(seg.get('start', 0.0)) + offset,
                        'end': float(seg.get('end', 0.0)) + offset,
                        'text': seg.get('text', ''),
                        'speaker': seg.get('speaker', '00'),
                        '_clip_file': file_path,
                    }
                    if clip_idx is not None:
                        item['_clip_idx'] = int(clip_idx)
                    segs.append(item)
            except Exception:
                pass
        return self._normalize_multiclip_segment_order(segs)

    def _recompute_multiclip_boundaries(self, files):
        from core.media_info import probe_media
        boundaries = []
        cumulative = 0.0
        for path in files:
            try:
                dur = float(probe_media(path).get('duration', 0.0) or 0.0)
            except Exception:
                dur = 0.0
            boundaries.append({'start': cumulative, 'end': cumulative + dur, 'file': path, 'name': os.path.basename(path)})
            cumulative += dur
        return boundaries

    def _remap_segments_for_multiclip_files(self, new_files):
        owner = self.window()
        old_bounds = list(getattr(owner, '_multiclip_boundaries', []) or [])
        old_by_file = {b.get('file'): b for b in old_bounds}
        new_bounds = self._recompute_multiclip_boundaries(new_files)
        new_by_file = {b.get('file'): b for b in new_bounds}
        current = self._get_current_segments()
        remapped = []
        for seg in current:
            file_path = seg.get('_clip_file')
            if not file_path:
                sec = float(seg.get('start', 0.0))
                for b in old_bounds:
                    if b['start'] <= sec < b['end'] + 0.001:
                        file_path = b.get('file')
                        break
            if not file_path or file_path not in new_by_file or file_path not in old_by_file:
                continue
            old_off = float(old_by_file[file_path]['start'])
            new_off = float(new_by_file[file_path]['start'])
            shifted = dict(seg)
            shifted['start'] = round(float(seg.get('start', 0.0)) - old_off + new_off, 3)
            shifted['end'] = round(float(seg.get('end', 0.0)) - old_off + new_off, 3)
            shifted['_clip_file'] = file_path
            remapped.append(shifted)
        remapped = self._normalize_multiclip_segment_order(remapped)
        return remapped, new_bounds

    def _apply_multiclip_state_from_owner(self):
        owner = self.window()
        if not owner or not getattr(owner, '_multiclip_boundaries', None):
            return
        boxes = []
        for i, bd in enumerate(owner._multiclip_boundaries):
            boxes.append({'start': bd['start'], 'end': bd['end'], 'index': i + 1, 'name': bd.get('name', ''), 'file': bd.get('file', '')})
        total_dur = owner._multiclip_boundaries[-1]['end'] if owner._multiclip_boundaries else 0.0
        self.timeline.canvas._multiclip_boxes = boxes
        self.timeline.canvas._active_clip_idx = 0
        self.timeline.canvas.boundary_times = [bd['end'] for bd in owner._multiclip_boundaries[:-1]]
        self.timeline.canvas.total_duration = total_dur
        try:
            owner._active_clip_idx = 0
        except Exception:
            pass
        gc = self.timeline.global_canvas
        gc.total_duration = total_dur
        gc._multiclip_boxes = boxes
        gc._active_clip_idx = 0
        try:
            if boxes:
                self.timeline._selected_clip_idx = 0
                self.timeline._selected_clip_offset = float(boxes[0].get('start', 0.0))
                self.timeline._selected_clip_duration = max(0.001, float(boxes[0].get('end', 0.0)) - float(boxes[0].get('start', 0.0)))
                self.timeline._selected_clip_label = str(boxes[0].get('index', 1))
                gc.set_clip_label(self.timeline._selected_clip_label)
            else:
                self.timeline._selected_clip_label = ''
                gc.set_clip_label('')
        except Exception:
            pass
        self.timeline.canvas.update()
        gc.update()
        try:
            self.timeline.load_multiclip_waveform(owner._multiclip_boundaries)
        except Exception:
            pass

    def _reload_segments_from_list(self, segs, *, preserve_view: bool = False):
        segs = self._normalize_multiclip_segment_order(segs)
        try:
            if getattr(self, "_queue_timer", None) is not None:
                self._queue_timer.stop()
        except Exception:
            pass
        if hasattr(self, "_segment_queue"):
            self._segment_queue.clear()
        for attr, value in (
            ("_live_editor_preview_queue", []),
            ("_live_editor_preview_segments", []),
            ("_live_editor_preview_keys", set()),
        ):
            if hasattr(self, attr):
                setattr(self, attr, value.copy() if hasattr(value, "copy") else value)
        self._is_initial_load = (True if segs else False) and not bool(preserve_view)
        prev_suspend_autoseek = bool(getattr(self, "_suspend_append_segments_autoseek", False))
        if preserve_view:
            self._suspend_append_segments_autoseek = True
        self.text_edit.clear()
        try:
            self.append_segments(segs)
            if preserve_view and hasattr(self, "_flush_queue"):
                self._flush_queue()
                try:
                    if getattr(self, "_queue_timer", None) is not None:
                        self._queue_timer.stop()
                except Exception:
                    pass
            if hasattr(self, "_rebuild_subtitle_memory_cache"):
                self._rebuild_subtitle_memory_cache(segs)
            else:
                self._cached_segs = segs
            total_dur = segs[-1]['end'] if segs else 0.0
            if hasattr(self, 'video_player') and self.video_player.total_time > 0:
                total_dur = max(total_dur, self.video_player.total_time)
            self.timeline.update_segments(segs, self._active_seg_start, total_dur)
            self._mark_dirty()
            self._schedule_timeline()
        finally:
            self._suspend_append_segments_autoseek = prev_suspend_autoseek

    def _on_clip_delete_requested(self, clip_idx):
        owner = self.window()
        files = list(getattr(owner, '_multiclip_files', []) or [])
        if clip_idx < 0 or clip_idx >= len(files):
            return
        self._undo_mgr.push_immediate()
        files.pop(clip_idx)
        remapped, new_bounds = self._remap_segments_for_multiclip_files(files)
        owner._multiclip_files = files
        owner._multiclip_boundaries = new_bounds
        owner._project_boundary_times = [b['end'] for b in new_bounds[:-1]] if len(new_bounds) > 1 else []
        owner._active_clip_idx = max(0, min(clip_idx, len(files) - 1)) if files else 0
        self._reload_segments_from_list(remapped)
        self._apply_multiclip_state_from_owner()
        try:
            self._auto_save_project(self._get_current_segments())
        except Exception:
            pass

    def _on_clip_add_requested(self):
        owner = self.window()
        from ui.project.multiclip_panel import MultiClipEditor
        files = list(getattr(owner, '_multiclip_files', []) or [])
        if not files and getattr(self, 'media_path', None):
            files = [self.media_path]
            owner._multiclip_files = list(files)
            owner._multiclip_boundaries = self._recompute_multiclip_boundaries(files)
            owner._project_boundary_times = []
        dlg = MultiClipEditor(files, owner, reorder_only=True, show_multiclip=False)
        if not dlg.exec():
            return
        self._undo_mgr.push_immediate()
        old_files = list(getattr(owner, '_multiclip_files', []) or [])
        new_files = list(dlg.sorted_files)
        remapped, new_bounds = self._remap_segments_for_multiclip_files(new_files)
        added_files = [f for f in new_files if f not in old_files]
        use_existing = False
        if added_files:
            has_existing = any(os.path.exists(os.path.splitext(f)[0] + '.srt') for f in added_files)
            if has_existing:
                from ui.dialogs.message_box import ask_yes_no
                use_existing = ask_yes_no(self, "기존 자막 사용", "기존 자막을 사용하시겠습니까?")
        owner._multiclip_files = new_files
        owner._multiclip_boundaries = new_bounds
        owner._project_boundary_times = [b['end'] for b in new_bounds[:-1]] if len(new_bounds) > 1 else []
        owner._active_clip_idx = int(getattr(owner, '_active_clip_idx', 0) or 0)
        if use_existing:
            for f in added_files:
                bd = next((b for b in new_bounds if b.get('file') == f), None)
                if bd:
                    clip_idx = next((i for i, b in enumerate(new_bounds) if b.get('file') == f), None)
                    remapped.extend(self._collect_existing_clip_segments(f, float(bd['start']), clip_idx))
        remapped = self._normalize_multiclip_segment_order(remapped)
        self._reload_segments_from_list(remapped)
        self._apply_multiclip_state_from_owner()
        try:
            self._auto_save_project(self._get_current_segments())
        except Exception:
            pass
