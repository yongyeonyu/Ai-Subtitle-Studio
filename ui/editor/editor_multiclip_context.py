# Version: 02.03.02
# Phase: PHASE1-B
"""
EditorWidget 멀티클립 활성 컨텍스트 / 클립 전환 / undo routing Mixin.
"""
import os

from core.frame_time import normalize_fps


class EditorMulticlipContextMixin:
    def _fps_for_media_path(self, path: str) -> float:
        try:
            from core.media_info import probe_media

            return normalize_fps(probe_media(path).get("fps", 0.0) or getattr(self, "video_fps", 30.0))
        except Exception:
            return normalize_fps(getattr(self, "video_fps", 30.0) or 30.0)

    def _hook_multiclip_clip_signals(self):
        try:
            canvas = self.timeline.canvas
            if hasattr(canvas, 'sig_clip_selected'):
                try:
                    canvas.sig_clip_selected.disconnect(self._on_clip_selected)
                except Exception:
                    pass
                # clip selected는 timeline.sig_clip_selected 단일 경로만 사용
                pass
            if hasattr(canvas, 'sig_clip_delete_requested'):
                try:
                    canvas.sig_clip_delete_requested.disconnect(self._on_clip_delete_requested)
                except Exception:
                    pass
                canvas.sig_clip_delete_requested.connect(self._on_clip_delete_requested)
            if hasattr(canvas, 'sig_clip_add_requested'):
                try:
                    canvas.sig_clip_add_requested.disconnect(self._on_clip_add_requested)
                except Exception:
                    pass
                canvas.sig_clip_add_requested.connect(self._on_clip_add_requested)
        except Exception:
            pass

    def _route_undo(self):
        from PyQt6.QtWidgets import QApplication
        fw = QApplication.focusWidget()
        if hasattr(fw, 'undo') and fw.hasFocus():
            fw.undo()
        else:
            self._undo_mgr.undo()

    def _route_redo(self):
        from PyQt6.QtWidgets import QApplication
        fw = QApplication.focusWidget()
        if hasattr(fw, 'redo') and fw.hasFocus():
            fw.redo()
        else:
            self._undo_mgr.redo()

    def _get_multiclip_clip_box(self, clip_idx: int):
        boxes = getattr(self.timeline.canvas, '_multiclip_boxes', []) or []
        if clip_idx < 0 or clip_idx >= len(boxes):
            return None
        return boxes[clip_idx]

    def _build_local_segments_for_clip(self, clip_idx: int, segs: list[dict] | None = None):
        box = self._get_multiclip_clip_box(clip_idx)
        if not box:
            return list(segs or self._get_current_segments())

        segs = list(segs or self._get_current_segments())
        clip_start = float(box.get('start', 0.0))
        clip_end = float(box.get('end', 0.0))
        out = []
        for seg in segs:
            if seg.get('is_gap'):
                continue
            text = str(seg.get('text', '') or '').strip()
            if not text:
                continue
            gs = float(seg.get('start', 0.0))
            ge = float(seg.get('end', 0.0))
            if ge <= clip_start or gs >= clip_end:
                continue
            item = dict(seg)
            item['start'] = max(0.0, gs - clip_start)
            item['end'] = max(item['start'], ge - clip_start)
            out.append(item)
        return out

    def _apply_multiclip_active_context(self, clip_idx: int, global_sec: float | None = None, autoplay: bool = False, show_thumbnail: bool = True):
        box = self._get_multiclip_clip_box(clip_idx)
        if not box:
            return

        clip_file = box.get("file", "")
        if not (clip_file and os.path.exists(clip_file) and hasattr(self, 'video_player')):
            return

        if global_sec is None:
            global_sec = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)

        clip_start = float(box.get("start", 0.0))
        local_seek = max(0.0, float(global_sec) - clip_start)
        local_segs = self._build_local_segments_for_clip(clip_idx)
        fps = self._fps_for_media_path(clip_file)
        if hasattr(self, "_set_editor_frame_rate"):
            self._set_editor_frame_rate(fps)

        if hasattr(self.timeline, 'canvas'):
            self.timeline.canvas._active_clip_idx = int(clip_idx)

        self.video_player.load_clip_context(
            clip_file,
            local_segs,
            seek_sec=local_seek,
            autoplay=autoplay,
            show_thumbnail=show_thumbnail,
        )
        self.media_path = clip_file

    def _resolve_active_context(self, global_sec: float | None = None, clip_idx: int | None = None):
        if global_sec is None:
            global_sec = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)

        boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
        is_multiclip = bool(boxes)

        if not is_multiclip:
            segs = list(self._get_current_segments()) if hasattr(self, '_get_current_segments') else []
            local_segs = [s for s in segs if not s.get('is_gap') and str(s.get('text', '') or '').strip()]
            return {
                'mode': 'single',
                'clip_idx': 0,
                'clip_file': getattr(self, 'media_path', '') or '',
                'global_sec': float(global_sec),
                'local_sec': float(global_sec),
                'clip_start': 0.0,
                'clip_end': float(getattr(self.video_player, 'total_time', 0.0) or 0.0),
                'fps': normalize_fps(getattr(self, "video_fps", 30.0) or 30.0),
                'local_segments': local_segs,
            }

        if clip_idx is None:
            for i, box in enumerate(boxes):
                if float(box.get('start', 0.0)) <= float(global_sec) < float(box.get('end', 0.0)):
                    clip_idx = i
                    break
            if clip_idx is None:
                clip_idx = max(0, min(int(getattr(self.timeline.canvas, '_active_clip_idx', 0) or 0), len(boxes) - 1))

        box = boxes[int(clip_idx)]
        clip_start = float(box.get('start', 0.0))
        clip_end = float(box.get('end', clip_start))
        local_sec = max(0.0, float(global_sec) - clip_start)
        clip_file = box.get('file', '')
        local_segments = self._build_local_segments_for_clip(int(clip_idx)) if hasattr(self, '_build_local_segments_for_clip') else []
        fps = self._fps_for_media_path(clip_file) if clip_file else normalize_fps(getattr(self, "video_fps", 30.0))

        return {
            'mode': 'multi',
            'clip_idx': int(clip_idx),
            'clip_file': clip_file,
            'global_sec': float(global_sec),
            'local_sec': float(local_sec),
            'clip_start': clip_start,
            'clip_end': clip_end,
            'fps': fps,
            'local_segments': local_segments,
        }

    def _apply_active_context(self, ctx: dict, autoplay: bool = False, show_thumbnail: bool = True):
        if not ctx or not hasattr(self, 'video_player'):
            return
        if not getattr(self.video_player, '_end_of_media_callback', None):
            self.video_player._end_of_media_callback = getattr(self, '_on_end_of_clip', None)

        clip_file = str(ctx.get('clip_file', '') or '')
        if not clip_file:
            return

        local_segments = list(ctx.get('local_segments', []) or [])
        local_sec = float(ctx.get('local_sec', 0.0) or 0.0)
        clip_idx = int(ctx.get('clip_idx', 0) or 0)
        fps = normalize_fps(ctx.get('fps', None) or self._fps_for_media_path(clip_file))
        if hasattr(self, "_set_editor_frame_rate"):
            self._set_editor_frame_rate(fps)

        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas._active_clip_idx = clip_idx
            self.timeline.set_playhead(float(ctx.get('global_sec', 0.0) or 0.0))
            self._cached_clip_bounds = None
            self._last_sync_clip_idx = -1

        self.video_player.set_active_context(
            path=clip_file,
            segments=local_segments,
            seek_sec=local_sec,
            autoplay=autoplay,
            show_thumbnail=show_thumbnail,
        )
        self.media_path = clip_file

    def _on_clip_selected(self, clip_idx):
        ctx = self._resolve_active_context(clip_idx=int(clip_idx))
        self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)

    def _on_end_of_clip(self):
        boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
        if not boxes:
            return
        cur_idx = int(getattr(self.timeline.canvas, '_active_clip_idx', 0) or 0)
        nxt = cur_idx + 1
        if nxt >= len(boxes):
            if hasattr(self, 'video_player'):
                self.video_player.pause_video()
            return
        nxt_box = boxes[nxt]
        nxt_global = float(nxt_box.get('start', 0.0))
        ctx = self._resolve_active_context(global_sec=nxt_global, clip_idx=nxt)
        self._apply_active_context(ctx, autoplay=True, show_thumbnail=False)
