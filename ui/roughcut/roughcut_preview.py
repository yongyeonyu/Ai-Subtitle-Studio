# Version: 03.01.13
# Phase: PHASE2
from __future__ import annotations


class RoughcutPreviewMixin:
    def _video_player(self):
        editor = self._active_editor()
        return getattr(editor, "video_player", None) if editor is not None else None

    def _play_preview(self, row: int, muted: bool = False, hover: bool = False):
        chapter = self._chapter_for_row(row)
        if chapter is None:
            return
        self._preview_row_data(row)
        player = self._video_player()
        if player is None or not hasattr(player, "media_player"):
            return

        start = float(chapter.start)
        end = float(chapter.end)
        edl_segment = self._edl_for_row(row)
        if edl_segment is not None:
            start = float(edl_segment.timeline_start if edl_segment.timeline_start is not None else edl_segment.source_start)
            end = float(edl_segment.timeline_end if edl_segment.timeline_end is not None else edl_segment.source_end)

        local_start = start
        local_end = end
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_resolve_active_context") and hasattr(editor, "_apply_active_context"):
            try:
                ctx = editor._resolve_active_context(global_sec=start)
                editor._apply_active_context(ctx, autoplay=False, show_thumbnail=not hover)
                if edl_segment is not None and edl_segment.clip_index is not None:
                    local_start = float(edl_segment.source_start)
                    local_end = float(edl_segment.source_end)
                else:
                    local_start = float(ctx.get("local_sec", start) or 0.0)
                    local_end = local_start + max(0.1, end - start)
                player = self._video_player()
            except Exception:
                local_start = start
                local_end = end

        self._preview_end = max(local_start + 0.1, local_end)
        self._preview_is_hover = hover
        self._preview_deadline_ms = 4000 if hover else max(500, int((self._preview_end - local_start) * 1000.0))

        audio = getattr(player, "audio_output", None)
        if muted and audio is not None and hasattr(audio, "volume") and hasattr(audio, "setVolume"):
            if self._restore_volume is None:
                self._restore_volume = float(audio.volume())
            audio.setVolume(0.0)
        elif not muted:
            self._restore_player_volume()

        if hasattr(player, "seek_direct"):
            player.seek_direct(local_start)
        else:
            player.media_player.setPosition(int(local_start * 1000.0))
        player.media_player.play()
        self._preview_timer.start()

    def _preview_tick(self):
        player = self._video_player()
        if player is None or not hasattr(player, "media_player"):
            self._stop_preview()
            return
        self._preview_deadline_ms -= self._preview_timer.interval()
        current = float(getattr(player, "current_time", 0.0) or 0.0)
        if hasattr(player.media_player, "position"):
            current = max(current, player.media_player.position() / 1000.0)
        if self._preview_is_hover and self._preview_deadline_ms > 0 and current >= self._preview_end:
            self._play_preview(self._preview_row, muted=True, hover=True)
            return
        if self._preview_deadline_ms <= 0 or current >= self._preview_end:
            if self._preview_should_loop():
                self._play_preview(self._preview_row, muted=False, hover=False)
                return
            self._stop_preview()

    def _preview_should_loop(self) -> bool:
        if bool(getattr(self, "_preview_is_hover", False)):
            return False
        button = getattr(self, "btn_preview_loop", None)
        if button is not None and hasattr(button, "isChecked"):
            return bool(button.isChecked())
        return bool(getattr(self, "_preview_loop_enabled", False))

    def _restore_player_volume(self):
        if self._restore_volume is None:
            return
        player = self._video_player()
        audio = getattr(player, "audio_output", None) if player is not None else None
        if audio is not None and hasattr(audio, "setVolume"):
            audio.setVolume(self._restore_volume)
        self._restore_volume = None

    def _stop_preview(self):
        self._preview_timer.stop()
        player = self._video_player()
        if player is not None and hasattr(player, "media_player"):
            player.media_player.pause()
        self._restore_player_volume()
