# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

from ui.editor.editor_multiclip_owner_bridge import EditorMulticlipOwnerBridgeMixin


class EditorMulticlipTransactionFlowMixin(EditorMulticlipOwnerBridgeMixin):
    def _seed_multiclip_runtime_from_media_path(self, owner=None) -> list[str]:
        owner = owner if owner is not None else self._multiclip_owner()
        files = self._multiclip_files_from_owner(owner)
        if files or not getattr(self, "media_path", None):
            return files
        files = [self.media_path]
        self._apply_multiclip_runtime_state(owner, files, self._recompute_multiclip_boundaries(files))
        return list(files)

    def _multiclip_add_dialog_files(self, owner=None) -> list[str]:
        return self._seed_multiclip_runtime_from_media_path(owner)

    def _open_multiclip_add_dialog(self, owner, files):
        from ui.project.multiclip_panel import MultiClipEditor

        return MultiClipEditor(files, owner, reorder_only=True, show_multiclip=False)

    def _multiclip_added_files(self, old_files: list[str], new_files: list[str]) -> list[str]:
        old_set = set(old_files or [])
        return [path for path in list(new_files or []) if path not in old_set]

    def _resolve_existing_multiclip_srt_import(self, added_files: list[str]) -> tuple[bool, list[str]]:
        if not added_files:
            return False, []
        has_existing, existing_added_files = self._added_multiclip_files_with_existing_srts(added_files)
        if not has_existing:
            return False, []
        from ui.dialogs.message_box import ask_yes_no

        return bool(ask_yes_no(self, "기존 자막 사용", "기존 자막을 사용하시겠습니까?")), list(existing_added_files)

    def _finalize_multiclip_transaction(
        self,
        owner,
        new_files: list[str],
        new_bounds: list[dict],
        remapped: list[dict],
        *,
        active_clip_idx: int | None = None,
        import_existing_files: list[str] | None = None,
    ) -> None:
        self._apply_multiclip_runtime_state(owner, new_files, new_bounds)
        if active_clip_idx is None:
            active_clip_idx = self._multiclip_active_clip_idx(owner)
        self._set_multiclip_active_clip_idx(active_clip_idx, owner)
        if import_existing_files:
            remapped = self._append_existing_multiclip_segments(remapped, new_bounds, list(import_existing_files))
        self._reload_apply_and_persist_multiclip(remapped)

    def _on_clip_delete_requested(self, clip_idx):
        owner = self._multiclip_owner()
        files = self._multiclip_files_from_owner(owner)
        if clip_idx < 0 or clip_idx >= len(files):
            return
        self._undo_mgr.push_immediate()
        files.pop(clip_idx)
        remapped, new_bounds = self._remap_segments_for_multiclip_files(files)
        next_active = max(0, min(clip_idx, len(files) - 1)) if files else 0
        self._finalize_multiclip_transaction(
            owner,
            files,
            new_bounds,
            remapped,
            active_clip_idx=next_active,
        )

    def _on_clip_add_requested(self):
        owner = self._multiclip_owner()
        files = self._multiclip_add_dialog_files(owner)
        dlg = self._open_multiclip_add_dialog(owner, files)
        if not dlg.exec():
            return
        self._undo_mgr.push_immediate()
        old_files = self._multiclip_files_from_owner(owner)
        new_files = list(dlg.sorted_files)
        remapped, new_bounds = self._remap_segments_for_multiclip_files(new_files)
        added_files = self._multiclip_added_files(old_files, new_files)
        import_existing, existing_added_files = self._resolve_existing_multiclip_srt_import(added_files)
        import_files = existing_added_files if import_existing else []
        self._finalize_multiclip_transaction(
            owner,
            new_files,
            new_bounds,
            remapped,
            active_clip_idx=self._multiclip_active_clip_idx(owner),
            import_existing_files=import_files,
        )
