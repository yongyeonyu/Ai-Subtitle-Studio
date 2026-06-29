# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations


class RoughcutPreviewMixin:
    def _video_player(self):
        editor = self._active_editor()
        return getattr(editor, "video_player", None) if editor is not None else None

    def _play_preview(self, row: int, muted: bool = False, hover: bool = False, update_preview_data: bool = True):
        chapter = self._chapter_for_row(row)
        if chapter is None:
            return
        if update_preview_data:
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
        update_video_box = getattr(self, "_update_roughcut_video_for_row", None)
        if callable(update_video_box):
            update_video_box(row, playing=True, current_sec=local_start)

    def _start_ordered_preview_sequence(self):
        visible_rows = self._visible_preview_rows()
        if not visible_rows:
            return False
        current_row = self._preview_row if self._preview_row in visible_rows else self.table.currentRow()
        if current_row not in visible_rows:
            current_row = visible_rows[0]
        self._sequence_preview_rows = list(visible_rows)
        self._sequence_preview_index = self._sequence_preview_rows.index(current_row)
        self._sequence_preview_active = True
        self.table.selectRow(current_row)
        self._preview_row_data(current_row)
        self._play_preview(current_row, muted=False)
        return True

    def _advance_ordered_preview_sequence(self):
        rows = list(getattr(self, "_sequence_preview_rows", []) or [])
        current_index = int(getattr(self, "_sequence_preview_index", -1))
        if not rows or current_index < 0:
            return False
        next_index = current_index + 1
        if next_index >= len(rows):
            return False
        next_row = rows[next_index]
        self._sequence_preview_index = next_index
        self.table.selectRow(next_row)
        self._preview_row_data(next_row)
        self._play_preview(next_row, muted=False)
        return True

    def _preview_tick(self):
        player = self._video_player()
        if player is None or not hasattr(player, "media_player"):
            self._stop_preview()
            return
        self._preview_deadline_ms -= self._preview_timer.interval()
        current = float(getattr(player, "current_time", 0.0) or 0.0)
        if hasattr(player.media_player, "position"):
            current = max(current, player.media_player.position() / 1000.0)
        update_playbar = getattr(self, "_update_roughcut_video_playbar", None)
        if callable(update_playbar):
            update_playbar(current)
        if self._preview_is_hover and self._preview_deadline_ms > 0 and current >= self._preview_end:
            self._play_preview(self._preview_row, muted=True, hover=True)
            return
        if self._preview_deadline_ms <= 0 or current >= self._preview_end:
            if bool(getattr(self, "_sequence_preview_active", False)):
                if self._advance_ordered_preview_sequence():
                    return
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
        self._sequence_preview_active = False
        self._sequence_preview_rows = []
        self._sequence_preview_index = -1
        self._preview_timer.stop()
        player = self._video_player()
        if player is not None and hasattr(player, "media_player"):
            player.media_player.pause()
        self._restore_player_volume()
        set_state = getattr(self, "_set_roughcut_video_state", None)
        if callable(set_state):
            set_state("정지", "#A9B0B7", "#2D3942")
