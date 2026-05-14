from __future__ import annotations


class EditorMulticlipOwnerBridgeMixin:
    def _multiclip_owner(self):
        try:
            return self.window()
        except RuntimeError:
            return None

    def _multiclip_files_from_owner(self, owner=None) -> list[str]:
        owner = owner if owner is not None else self._multiclip_owner()
        return list(getattr(owner, "_multiclip_files", []) or []) if owner is not None else []

    def _multiclip_boundaries_from_owner(self, owner=None) -> list[dict]:
        owner = owner if owner is not None else self._multiclip_owner()
        return list(getattr(owner, "_multiclip_boundaries", []) or []) if owner is not None else []

    def _multiclip_project_boundary_rows(self, owner=None) -> list[dict]:
        owner = owner if owner is not None else self._multiclip_owner()
        return list(getattr(owner, "_project_boundary_times", []) or []) if owner is not None else []

    def _multiclip_active_clip_idx(self, owner=None) -> int:
        owner = owner if owner is not None else self._multiclip_owner()
        try:
            return int(getattr(owner, "_active_clip_idx", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _set_multiclip_active_clip_idx(self, clip_idx: int, owner=None) -> int:
        owner = owner if owner is not None else self._multiclip_owner()
        clip_idx = int(clip_idx or 0)
        if owner is not None:
            try:
                owner._active_clip_idx = clip_idx
            except (AttributeError, RuntimeError):
                pass
        return clip_idx

    def _multiclip_total_duration(self, owner=None) -> float:
        boundaries = self._multiclip_boundaries_from_owner(owner)
        if not boundaries:
            return 0.0
        try:
            return float(boundaries[-1].get("end", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            return 0.0
