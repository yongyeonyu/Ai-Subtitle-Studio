# Version: 03.14.31
# Phase: PHASE2
"""Shadow playhead helpers for timeline input interactions."""


class TimelineInputShadowMixin:
    def _timeline_widget_owner(self):
        owner = self.parent()
        while owner is not None:
            if hasattr(owner, "set_shadow_playhead") or hasattr(owner, "pin_shadow_playhead"):
                return owner
            try:
                owner = owner.parent()
            except Exception:
                owner = None
        return None

    def _shadow_playhead_sec(self) -> float | None:
        value = getattr(self, "shadow_playhead_sec", None)
        if value is None:
            return None
        try:
            return self._snap_to_frame(float(value or 0.0))
        except Exception:
            return None

    def _armed_shadow_playhead_sec(self) -> float | None:
        value = getattr(self, "_shadow_playhead_armed_sec", None)
        if value is None:
            return None
        try:
            return self._snap_to_frame(float(value or 0.0))
        except Exception:
            return None

    def _set_shadow_playhead(self, sec: float | None) -> bool:
        owner = self._timeline_widget_owner()
        setter = getattr(owner, "set_shadow_playhead", None) if owner is not None else None
        if not callable(setter):
            setter = getattr(self, "set_shadow_playhead", None)
        if not callable(setter):
            return False
        if sec is not None:
            self._disarm_shadow_playhead()
        try:
            return bool(setter(sec))
        except Exception:
            return False

    def _arm_shadow_playhead(self, sec: float | None, *, clear_visible: bool = True) -> bool:
        if sec is None:
            self._disarm_shadow_playhead()
            if clear_visible:
                self._clear_shadow_playhead()
            return False
        try:
            armed_sec = self._snap_to_frame(float(sec or 0.0))
        except Exception:
            return False
        setattr(self, "_shadow_playhead_armed_sec", armed_sec)
        if clear_visible:
            self._clear_shadow_playhead()
        return True

    def _disarm_shadow_playhead(self) -> bool:
        if getattr(self, "_shadow_playhead_armed_sec", None) is None:
            return False
        self._shadow_playhead_armed_sec = None
        return True

    def _show_armed_shadow_playhead(self) -> bool:
        armed_sec = self._armed_shadow_playhead_sec()
        if armed_sec is None:
            return False
        self._shadow_playhead_armed_sec = None
        return self._set_shadow_playhead(armed_sec)

    def _pin_shadow_playhead(self, sec: float | None = None) -> bool:
        owner = self._timeline_widget_owner()
        pinner = getattr(owner, "pin_shadow_playhead", None) if owner is not None else None
        if callable(pinner):
            try:
                return bool(pinner(sec))
            except Exception:
                return False
        target = getattr(self, "playhead_sec", 0.0) if sec is None else sec
        return self._set_shadow_playhead(target)

    def _clear_shadow_playhead(self) -> bool:
        owner = self._timeline_widget_owner()
        clearer = getattr(owner, "clear_shadow_playhead", None) if owner is not None else None
        if not callable(clearer):
            clearer = getattr(self, "clear_shadow_playhead", None)
        if not callable(clearer):
            return False
        try:
            return bool(clearer())
        except Exception:
            return False

    def _remember_shadow_before_playhead_move(self, sec: float, *, force: bool = False) -> bool:
        try:
            current_sec = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
            target_sec = self._snap_to_frame(float(sec or 0.0))
        except Exception:
            return False
        if not force and abs(target_sec - current_sec) < 0.001:
            return False
        armed_sec = self._armed_shadow_playhead_sec()
        if armed_sec is None:
            return False
        if not force and abs(current_sec - armed_sec) >= 0.001:
            return False
        return self._show_armed_shadow_playhead()

    def _consume_shadow_playhead_snap(self, snapped: dict | None) -> bool:
        if not isinstance(snapped, dict):
            return False
        if str(snapped.get("kind") or "") != "shadow_playhead":
            return False
        self._disarm_shadow_playhead()
        self._clear_shadow_playhead()
        return True

    def _emit_scrub_with_shadow(self, sec: float, *, remember_shadow: bool = True) -> None:
        target_sec = self._snap_to_frame(float(sec or 0.0))
        if remember_shadow:
            self._remember_shadow_before_playhead_move(target_sec)
        self.scrub_sec.emit(target_sec)

    def _begin_playhead_handle_scrub(self) -> None:
        self._clear_pending_center_drag()
        self._is_scrubbing = True
        self._playhead_handle_scrubbing = True
        self._playhead_cut_magnet_locked_sec = None
        try:
            origin = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        except Exception:
            origin = 0.0
        self._playhead_cut_magnet_origin_sec = origin
        self._playhead_cut_magnet_previous_sec = origin

    def _finish_playhead_handle_scrub(self) -> None:
        self._playhead_handle_scrubbing = False
        self._playhead_cut_magnet_locked_sec = None
        self._playhead_cut_magnet_origin_sec = None
        self._playhead_cut_magnet_previous_sec = None

    def _emit_scrub_with_playhead_cut_magnet(self, sec: float) -> None:
        if getattr(self, "_playhead_cut_magnet_locked_sec", None) is not None:
            return
        target_sec = self._snap_to_frame(float(sec or 0.0))
        snapper = getattr(self, "_playhead_auto_cut_snap_sec", None)
        if callable(snapper):
            try:
                previous_sec = self._snap_to_frame(
                    float(getattr(self, "_playhead_cut_magnet_previous_sec", getattr(self, "playhead_sec", target_sec)) or target_sec)
                )
                snapped = snapper(target_sec, previous_sec)
            except Exception:
                snapped = None
            if isinstance(snapped, tuple) and len(snapped) >= 2 and bool(snapped[1]):
                snap_sec = self._snap_to_frame(float(snapped[0] or target_sec))
                self._playhead_cut_magnet_locked_sec = snap_sec
                self._playhead_cut_magnet_previous_sec = snap_sec
                self._set_shadow_playhead(snap_sec)
                self._emit_scrub_with_shadow(snap_sec, remember_shadow=False)
                return

        self._playhead_cut_magnet_previous_sec = target_sec
        self._emit_scrub_with_shadow(target_sec)
