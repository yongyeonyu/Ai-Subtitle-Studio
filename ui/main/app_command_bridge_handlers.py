from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any


def _handle_editor_transport_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    editor = getattr(owner, "_editor_widget", None)
    if command == "editor-set-playhead":
        if editor is None:
            return fail("editor_missing")
        setter = getattr(editor, "automation_set_playhead", None)
        if not callable(setter):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        sec = helpers.command_option_float(options, "sec")
        if sec is None:
            return fail("invalid_playhead_sec")
        try:
            data = dict(
                setter(
                    sec,
                    center=helpers.command_option_bool(options, "center", default=False),
                    sync_video=helpers.command_option_bool(options, "sync_video", default=True),
                )
                or {}
            )
        except ValueError as exc:
            return fail(str(exc))
        helpers.bring_to_front(owner)
        return ok(message="editor_playhead_set", data=data)

    if command in {"editor-pin-shadow-playhead", "editor-clear-shadow-playhead", "editor-zoom-max"}:
        if editor is None:
            return fail("editor_missing")
        method_name = {
            "editor-pin-shadow-playhead": "automation_pin_shadow_playhead",
            "editor-clear-shadow-playhead": "automation_clear_shadow_playhead",
            "editor-zoom-max": "automation_zoom_max",
        }[command]
        action = getattr(editor, method_name, None)
        if not callable(action):
            return fail("editor_automation_unavailable")
        try:
            if command == "editor-pin-shadow-playhead":
                options = dict(command_payload.get("options") or {})
                data = dict(action(sec=helpers.command_option_float(options, "sec")) or {})
            else:
                data = dict(action() or {})
        except ValueError as exc:
            return fail(str(exc))
        helpers.bring_to_front(owner)
        message = {
            "editor-pin-shadow-playhead": "editor_shadow_playhead_pinned",
            "editor-clear-shadow-playhead": "editor_shadow_playhead_cleared",
            "editor-zoom-max": "editor_zoom_max_applied",
        }[command]
        return ok(message=message, data=data)

    if command in {"editor-playback", "editor-video", "editor-select-segment"}:
        if editor is None:
            return fail("editor_missing")
        options = dict(command_payload.get("options") or {})
        if command == "editor-playback":
            player = getattr(editor, "automation_set_playback_state", None)
            if not callable(player):
                return fail("editor_automation_unavailable")
            action = str(options.get("action", "toggle") or "toggle")
            try:
                data = dict(player(action) or {})
            except ValueError as exc:
                return fail(str(exc))
            helpers.bring_to_front(owner)
            return ok(message=f"editor_playback_{action}", data=data)
        if command == "editor-video":
            toggler = getattr(editor, "automation_set_video_visible", None)
            if not callable(toggler):
                return fail("editor_automation_unavailable")
            action = str(options.get("action", "toggle") or "toggle")
            try:
                data = dict(toggler(action) or {})
            except ValueError as exc:
                return fail(str(exc), data={"editor_runtime": helpers.editor_runtime_snapshot(editor)})
            helpers.bring_to_front(owner)
            return ok(message=f"editor_video_{action}", data=data)
        selector = getattr(editor, "automation_select_segment", None)
        if not callable(selector):
            return fail("editor_automation_unavailable")
        try:
            data = dict(
                selector(
                    line=helpers.command_option_int(options, "line"),
                    start_sec=helpers.command_option_float(options, "start_sec"),
                    at_playhead=helpers.command_option_bool(options, "at_playhead", default=False),
                    center=helpers.command_option_bool(options, "center", default=False),
                    sync_playhead=helpers.command_option_bool(options, "sync_playhead", default=False),
                )
                or {}
            )
        except ValueError as exc:
            return fail(str(exc))
        helpers.bring_to_front(owner)
        return ok(message="editor_segment_selected", data=data)
    return None


def _handle_editor_edit_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    editor = getattr(owner, "_editor_widget", None)
    if command in {"editor-begin-smart-split", "editor-set-inline-cursor", "editor-commit-inline-edit"}:
        if editor is None:
            return fail("editor_missing")
        options = dict(command_payload.get("options") or {})
        if command == "editor-begin-smart-split":
            starter = getattr(editor, "automation_begin_smart_split_at_playhead", None)
            if not callable(starter):
                return fail("editor_automation_unavailable")
            try:
                data = dict(
                    starter(
                        line=helpers.command_option_int(options, "line"),
                        start_sec=helpers.command_option_float(options, "start_sec"),
                        at_playhead=helpers.command_option_bool(options, "at_playhead", default=False),
                    )
                    or {}
                )
            except ValueError as exc:
                return fail(str(exc), data={"editor_runtime": helpers.editor_runtime_snapshot(editor)})
            helpers.bring_to_front(owner)
            return ok(message="editor_smart_split_mode_started", data=data)
        if command == "editor-set-inline-cursor":
            mover = getattr(editor, "automation_set_inline_edit_cursor", None)
            if not callable(mover):
                return fail("editor_automation_unavailable")
            position = helpers.command_option_int(options, "position")
            if position is None:
                return fail("invalid_inline_cursor_position")
            try:
                data = dict(mover(position) or {})
            except ValueError as exc:
                return fail(str(exc), data={"editor_runtime": helpers.editor_runtime_snapshot(editor)})
            helpers.bring_to_front(owner)
            return ok(message="editor_inline_cursor_set", data=data)
        committer = getattr(editor, "automation_commit_inline_edit", None)
        if not callable(committer):
            return fail("editor_automation_unavailable")
        try:
            data = dict(committer() or {})
        except ValueError as exc:
            return fail(str(exc), data={"editor_runtime": helpers.editor_runtime_snapshot(editor)})
        helpers.bring_to_front(owner)
        return ok(message="editor_inline_edit_committed", data=data)

    if command in {
        "editor-smart-split",
        "editor-move-segment-left",
        "editor-move-segment-right",
        "editor-move-diamond",
        "editor-merge-diamond",
    }:
        if editor is None:
            return fail("editor_missing")
        options = dict(command_payload.get("options") or {})
        try:
            selected = helpers.select_editor_segment_from_options(editor, options)
            if command == "editor-smart-split":
                splitter = getattr(editor, "automation_smart_split_at_playhead", None)
                if not callable(splitter):
                    return fail("editor_automation_unavailable")
                data = dict(splitter() or {})
                message = "editor_smart_split_done"
            elif command in {"editor-move-segment-left", "editor-move-segment-right"}:
                mover = getattr(editor, "automation_move_segment_boundary_to_playhead", None)
                if not callable(mover):
                    return fail("editor_automation_unavailable")
                edge = "left" if command.endswith("left") else "right"
                data = dict(mover(edge) or {})
                message = f"editor_segment_{edge}_moved"
            elif command == "editor-move-diamond":
                mover = getattr(editor, "automation_move_diamond_to_playhead", None)
                if not callable(mover):
                    return fail("editor_automation_unavailable")
                data = dict(mover(side=str(options.get("side", "closest") or "closest")) or {})
                message = "editor_diamond_moved"
            else:
                merger = getattr(editor, "automation_merge_diamond", None)
                if not callable(merger):
                    return fail("editor_automation_unavailable")
                data = dict(merger(side=str(options.get("side", "closest") or "closest")) or {})
                message = "editor_diamond_merged"
            if selected:
                data.setdefault("selected", dict(selected))
        except ValueError as exc:
            return fail(str(exc))
        helpers.bring_to_front(owner)
        return ok(message=message, data=data)
    return None


def _handle_snapshot_dialog_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command in {"capture-snapshot", "snapshot"}:
        logger.log("🤖 자동화 명령 수신: capture-snapshot")
        async_requested = bool(command_payload.get("options", {}).get("async", True))
        has_async_capture = callable(getattr(owner, "_automation_request_async_snapshot_capture", None))
        snapshot_result = (
            helpers.queue_window_snapshot(owner, command_payload)
            if async_requested and has_async_capture
            else helpers.capture_window_snapshot(owner, command_payload)
        )
        if not snapshot_result.get("ok"):
            return fail(str(snapshot_result.get("error", "snapshot_failed")), message=str(snapshot_result.get("message", "")))
        return ok(
            message="snapshot_queued" if snapshot_result.get("queued") else "snapshot_captured",
            data=snapshot_result.get("data"),
            queued=bool(snapshot_result.get("queued", False)),
        )

    if command in {"capture-dictionary-snapshot", "show-home", "open-dictionary"}:
        if command == "capture-dictionary-snapshot":
            logger.log("🤖 자동화 명령 수신: capture-dictionary-snapshot")
            dialog = getattr(owner, "_correction_dictionary_dialog", None)
            if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
                return fail("dictionary_not_visible")
            snapshot_result = helpers.capture_widget_snapshot(dialog, command_payload)
            if not snapshot_result.get("ok"):
                return fail(str(snapshot_result.get("error", "snapshot_failed")), message=str(snapshot_result.get("message", "")))
            return ok(message="dictionary_snapshot_captured", data=snapshot_result.get("data"))
        if command == "show-home":
            logger.log("🤖 자동화 명령 수신: show-home")
            owner.show_home()
            helpers.bring_to_front(owner)
            return ok(message="home_visible")
        logger.log("🤖 자동화 명령 수신: open-dictionary")
        opener = getattr(owner, "_show_main_correction_dictionary_nonmodal", None)
        if not callable(opener):
            return fail("dictionary_open_unavailable")
        dialog = opener()
        helpers.show_dialog_nonmodal(owner, dialog)
        return ok(message="dictionary_visible")

    if command in {"open-settings", "open-speaker-settings", "capture-active-dialog", "close-active-dialog"}:
        if command == "capture-active-dialog":
            logger.log("🤖 자동화 명령 수신: capture-active-dialog")
            dialog = helpers.active_automation_dialog(owner)
            if dialog is None:
                return fail("active_dialog_missing")
            snapshot_result = helpers.capture_widget_snapshot(dialog, command_payload)
            if not snapshot_result.get("ok"):
                return fail(str(snapshot_result.get("error", "snapshot_failed")), message=str(snapshot_result.get("message", "")))
            return ok(message="active_dialog_snapshot_captured", data=snapshot_result.get("data"))
        if command == "close-active-dialog":
            logger.log("🤖 자동화 명령 수신: close-active-dialog")
            dialog = helpers.active_automation_dialog(owner)
            if dialog is None:
                return fail("active_dialog_missing")
            helpers.bridge_best_effort("dialog close", lambda: getattr(dialog, "close", lambda: None)(), default=None)
            helpers.set_active_automation_dialog(owner, None)
            return ok(message="active_dialog_closed")
        logger.log(f"🤖 자동화 명령 수신: {command}")
        editor = getattr(owner, "_editor_widget", None)
        settings = dict(getattr(editor, "settings", None) or getattr(owner, "settings", {}) or {})
        try:
            if command == "open-settings":
                from ui.settings.settings_dialog import SettingsDialog

                dialog = SettingsDialog(settings, editor or owner)
                message = "settings_visible"
            else:
                from ui.settings.settings_dialog import SpeakerDialog

                dialog = SpeakerDialog(settings, editor or owner)
                message = "speaker_settings_visible"
        except Exception as exc:
            error = "settings_open_failed" if command == "open-settings" else "speaker_settings_open_failed"
            return fail(error, message=str(exc))
        helpers.show_dialog_nonmodal(owner, dialog)
        return ok(message=message)
    return None


def _handle_open_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command in {"open-project", "open-srt", "open-media"}:
        path = helpers.normalize_path(command_payload.get("path"))
        if not helpers.existing_file(path):
            error = {"open-project": "project_not_found", "open-srt": "srt_not_found", "open-media": "media_not_found"}[command]
            return fail(error, message=path)
        if command == "open-project":
            opener = getattr(owner, "_open_project_file", None)
            if not callable(opener):
                return fail("project_open_unavailable")
            logger.log(f"🤖 자동화 명령 수신: open-project {os.path.basename(path)}")
            if not bool(opener(path)):
                return fail("project_open_failed", message=path)
            helpers.bring_to_front(owner)
            return ok(message="project_opened", data={"path": path})
        if command == "open-srt":
            logger.log(f"🤖 자동화 명령 수신: open-srt {os.path.basename(path)}")
            owner._open_srt_in_editor(path)
            helpers.bring_to_front(owner)
            return ok(message="srt_opened", data={"path": path})
        backend = getattr(owner, "backend", None)
        starter = getattr(backend, "start_pipeline", None) if backend is not None else None
        if not callable(starter):
            return fail("pipeline_start_unavailable")
        logger.log(f"🤖 자동화 명령 수신: open-media {os.path.basename(path)}")
        opened = owner.open_editor_for_file_and_wait(
            path,
            helpers.noop,
            helpers.editor_pipeline_start_callback(owner, path, is_auto_start=True),
            helpers.noop,
            helpers.noop,
            False,
        )
        if not opened:
            return fail("media_open_failed", message=path)
        helpers.bring_to_front(owner)
        return ok(message="media_opened", data={"path": path})
    return None


def _handle_queue_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command == "start-multiclip":
        backend = getattr(owner, "backend", None)
        starter = getattr(backend, "start_multiclip_pipeline", None) if backend is not None else None
        if not callable(starter):
            return fail("multiclip_start_unavailable")
        editor = getattr(owner, "_editor_widget", None)
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        if state == "ST_PROC" or bool(getattr(backend, "_active", False)):
            return fail("already_processing")
        files, folder = helpers.resolve_multiclip_files(command_payload)
        if command_payload.get("folder") or (command_payload.get("path") and not command_payload.get("paths")):
            requested_folder = helpers.normalize_path(command_payload.get("folder") or command_payload.get("path"))
            if requested_folder and not helpers.existing_dir(requested_folder):
                return fail("queue_folder_missing", message=requested_folder)
        if not files:
            return fail("multiclip_files_missing")
        if len(files) < 2:
            return fail("multiclip_requires_multiple_files", message=str(files[0]))
        options = dict(command_payload.get("options") or {})
        reuse_policy = helpers.normalize_multiclip_reuse_policy(options.get("reuse_existing"))
        if not reuse_policy:
            return fail("invalid_reuse_existing_option", message=str(options.get("reuse_existing", "")))
        existing_candidates = helpers.multiclip_existing_srt_candidates(files)
        if existing_candidates and reuse_policy == "ask":
            names = ", ".join(os.path.basename(path) for path in existing_candidates[:3])
            return fail("existing_subtitles_confirmation_required", message=names)
        mode_value = str(options.get("mode") or "").strip()
        applied_settings = None
        if mode_value:
            try:
                applied_settings = helpers.apply_automation_mode_override(owner, mode_value)
            except Exception as exc:
                return fail("mode_apply_failed", message=str(exc))
        setattr(backend, "_force_reuse_existing_multiclip_subtitles_once", reuse_policy == "yes")
        setattr(backend, "_force_no_reuse_once", reuse_policy == "no")
        try:
            from ui.project.project_session_runtime import set_runtime_multiclip_state

            set_runtime_multiclip_state(owner, list(files), [], project_boundary_rows=None, emit_boundary_signal=False)
        except Exception as exc:
            return fail("multiclip_runtime_prepare_failed", message=str(exc))
        logger.log(
            f"🤖 자동화 명령 수신: start-multiclip {len(files)}개"
            + (f" / {helpers.normalize_mode(mode_value)}" if mode_value else "")
            + f" / reuse={reuse_policy}"
        )
        starter(list(files), folder=folder or None)
        helpers.bring_to_front(owner)
        data = {
            "count": len(files),
            "files": list(files),
            "folder": folder,
            "reuse_existing": reuse_policy,
            "existing_subtitle_candidates": [os.path.basename(path) for path in existing_candidates],
            "queue_runtime": helpers.queue_runtime_snapshot(owner),
        }
        if applied_settings:
            data["mode"] = str(applied_settings.get("simple_operation_mode", "") or "")
            data["stt_quality_preset"] = str(applied_settings.get("stt_quality_preset", "") or "")
        return ok(message="multiclip_started", queued=True, data=data)

    if command == "guided-subtitle-run":
        path = helpers.normalize_path(command_payload.get("path"))
        if not helpers.existing_file(path):
            return fail("media_not_found", message=path)
        backend = getattr(owner, "backend", None)
        pipeline_starter = getattr(backend, "start_pipeline", None) if backend is not None else None
        if not callable(pipeline_starter):
            return fail("pipeline_start_unavailable")
        editor = getattr(owner, "_editor_widget", None)
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        if state == "ST_PROC":
            return fail("already_processing")
        logger.log(f"🤖 자동화 명령 수신: guided-subtitle-run {os.path.basename(path)}")
        opened = owner.open_editor_for_file_and_wait(
            path,
            helpers.noop,
            helpers.editor_pipeline_start_callback(owner, path, is_auto_start=True),
            helpers.noop,
            helpers.noop,
            False,
        )
        if not opened:
            return fail("media_open_failed", message=path)
        begin_run = getattr(owner, "_automation_begin_guided_subtitle_run", None)
        capture_run = getattr(owner, "_automation_capture_guided_snapshot", None)
        snapshot_dir = ""
        snapshots: list[dict[str, Any]] = []
        if callable(begin_run):
            state_payload = begin_run(path, snapshot_dir=str(command_payload.get("options", {}).get("snapshot_dir", "") or ""))
            snapshot_dir = str((state_payload or {}).get("snapshot_dir", "") or "")
        if callable(capture_run):
            for label, stage in (("opened", "opened"), ("pipeline-started", "pipeline_started")):
                snapshot = capture_run(label, stage_text=stage, force=True)
                if isinstance(snapshot, dict) and snapshot:
                    snapshots.append(dict(snapshot))
        starter = getattr(getattr(owner, "_editor_widget", None), "_on_start_clicked", None)
        if not callable(starter):
            return fail("pipeline_start_unavailable")
        starter()
        helpers.bring_to_front(owner)
        current_status = helpers.status_snapshot(owner)
        store_status = getattr(helpers, "store_status_snapshot", None)
        if callable(store_status):
            current_status = dict(store_status(owner, current_status) or current_status)
        return ok(
            message="guided_subtitle_started",
            data={"path": path, "snapshot_dir": snapshot_dir, "snapshots": snapshots, "status": current_status},
        )

    if command in {"queue-files", "queue-folder"}:
        if command == "queue-files":
            files = [helpers.normalize_path(path) for path in command_payload.get("paths", [])]
            files = [path for path in files if helpers.existing_file(path)]
            if not files:
                return fail("queue_files_missing")
            folder = os.path.dirname(files[0])
            logger.log(f"🤖 자동화 명령 수신: queue-files {len(files)}개")
        else:
            folder = helpers.normalize_path(command_payload.get("folder") or command_payload.get("path"))
            if not folder or not os.path.isdir(folder):
                return fail("queue_folder_missing", message=folder)
            files = helpers.ordered_media_files(folder)
            if not files:
                return fail("queue_folder_empty", message=folder)
            logger.log(f"🤖 자동화 명령 수신: queue-folder {os.path.basename(folder)} / {len(files)}개")
        owner._start_queue_mode(files, folder=folder, source="automation")
        helpers.bring_to_front(owner)
        return ok(message="queue_started", data={"count": len(files), "folder": folder})
    return None


def _handle_save_export_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command == "save-project":
        logger.log("🤖 자동화 명령 수신: save-project")
        project_path = str(getattr(owner, "_current_project_path", "") or "")
        if project_path:
            saver = getattr(owner, "_save_current_project", None)
            if not callable(saver):
                return fail("project_save_unavailable")
            saver()
            return ok(message="project_saved", data={"path": project_path})
        editor = getattr(owner, "_editor_widget", None)
        save_handler = getattr(editor, "_on_save", None) if editor is not None else None
        if not callable(save_handler):
            return fail("nothing_to_save")
        try:
            saved = bool(save_handler(skip_auto_next=True))
        except TypeError:
            saved = bool(save_handler())
        return ok(message="editor_saved") if saved else fail("save_declined")

    if command in {"save-subtitles", "export-subtitles", "export-subtitle-video"}:
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        if command == "save-subtitles":
            logger.log("🤖 자동화 명령 수신: save-subtitles")
            save_handler = getattr(editor, "_on_save", None)
            if not callable(save_handler):
                return fail("subtitle_save_unavailable")
            try:
                saved = bool(save_handler(skip_auto_next=True, auto_export=False))
            except TypeError:
                try:
                    saved = bool(save_handler(skip_auto_next=True))
                except TypeError:
                    saved = bool(save_handler())
            if not saved:
                return fail("subtitle_save_declined")
            outputs = helpers.saved_srt_outputs(editor)
            output_rows = [{**helpers.file_result(srt_path), "target_file": target_file} for srt_path, target_file in outputs]
            missing = [row for row in output_rows if not row.get("exists")]
            if not output_rows or missing:
                return fail("subtitle_outputs_missing", data={"count": len(output_rows), "missing_count": len(missing), "outputs": output_rows})
            return ok(message="subtitles_saved", data={"count": len(output_rows), "outputs": output_rows})

        if command == "export-subtitles":
            logger.log("🤖 자동화 명령 수신: export-subtitles")
            segs = helpers.current_editor_srt_segments(editor)
            if not segs:
                return fail("subtitle_segments_missing")
            output_path = helpers.normalize_path(command_payload.get("path"))
            if not output_path:
                media_path = helpers.normalize_path(getattr(editor, "media_path", "") or "")
                if not media_path:
                    return fail("subtitle_export_path_missing")
                stem = os.path.splitext(os.path.basename(media_path))[0]
                output_path = os.path.join(os.path.dirname(media_path), f"{stem}_automation_export.srt")
            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                from core.engine.subtitle_engine import save_srt

                save_srt(segs, output_path, fps=float(getattr(editor, "video_fps", 30.0) or 30.0), write_backup=False)
            except Exception as exc:
                return fail("subtitle_export_failed", message=str(exc))
            result = helpers.file_result(output_path)
            if not result.get("exists"):
                return fail("subtitle_export_missing", data={"output": result, "segment_count": len(segs)})
            return ok(message="subtitles_exported", data={"output": result, "segment_count": len(segs)})

        logger.log("🤖 자동화 명령 수신: export-subtitle-video")
        outputs = helpers.saved_srt_outputs(editor)
        if not outputs:
            save_handler = getattr(editor, "_on_save", None)
            if not callable(save_handler):
                return fail("subtitle_video_export_unavailable")
            try:
                saved = bool(save_handler(skip_auto_next=True, auto_export=False))
            except TypeError:
                try:
                    saved = bool(save_handler(skip_auto_next=True))
                except TypeError:
                    saved = bool(save_handler())
            if not saved:
                return fail("subtitle_save_declined")
            outputs = helpers.saved_srt_outputs(editor)
        if not outputs:
            return fail("subtitle_outputs_missing")
        exporter = getattr(editor, "_auto_export_saved_subtitle_videos", None)
        if not callable(exporter):
            return fail("subtitle_video_export_unavailable")
        try:
            exporter(outputs=outputs)
        except TypeError:
            exporter()
        except Exception as exc:
            return fail("subtitle_video_export_failed", message=str(exc))
        output_rows = [{"srt_path": helpers.normalize_path(srt_path), "target_file": helpers.normalize_path(target_file or srt_path), "mov_output": helpers.file_result(helpers.subtitle_video_output_path(target_file or srt_path))} for srt_path, target_file in outputs]
        missing = [row for row in output_rows if not bool((row.get("mov_output") or {}).get("exists"))]
        if missing:
            return fail("subtitle_video_outputs_missing", data={"count": len(output_rows), "missing_count": len(missing), "outputs": output_rows})
        return ok(message="subtitle_videos_exported", data={"count": len(output_rows), "outputs": output_rows})
    return None


def _handle_mode_personalization_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command == "editor-stt-mode":
        logger.log("🤖 자동화 명령 수신: editor-stt-mode")
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        options = dict(command_payload.get("options") or {})
        action = str(options.get("action", "toggle") or "toggle").strip().lower()
        setter = getattr(editor, "_set_stt_mode_enabled", None)
        toggler = getattr(editor, "_toggle_stt_mode", None)
        current_enabled = bool(getattr(editor, "_stt_mode_enabled", False))
        try:
            if action == "toggle":
                if not callable(toggler):
                    return fail("editor_stt_mode_unavailable")
                toggler()
            elif action == "enable":
                if callable(setter):
                    setter(True)
                elif callable(toggler) and not current_enabled:
                    toggler()
                else:
                    return fail("editor_stt_mode_unavailable")
            elif action == "disable":
                if callable(setter):
                    setter(False)
                elif callable(toggler) and current_enabled:
                    toggler()
                else:
                    return fail("editor_stt_mode_unavailable")
            else:
                return fail("invalid_stt_mode_action", message=action)
        except Exception as exc:
            return fail("editor_stt_mode_failed", message=str(exc))
        return ok(message="editor_stt_mode_updated", data={"enabled": bool(getattr(editor, "_stt_mode_enabled", False)), "state": str(getattr(editor, "_stt_state", "") or ""), "editor_runtime": helpers.editor_runtime_snapshot(editor)})

    if command == "personalization-idle":
        logger.log("🤖 자동화 명령 수신: personalization-idle")
        options = dict(command_payload.get("options") or {})
        action = str(options.get("action", "run-now") or "run-now").strip().lower()
        runner_name = {
            "run-now": "_run_personalization_idle_jobs_now",
            "pause": "_pause_personalization_idle_jobs",
            "resume": "_resume_personalization_idle_jobs",
        }.get(action, "")
        if not runner_name:
            return fail("invalid_personalization_idle_action", message=action)
        runner = getattr(owner, runner_name, None)
        if not callable(runner):
            return fail("personalization_idle_unavailable")
        runtime = helpers.start_background_personalization_action(owner, action=action, runner=runner)
        return ok(message=f"personalization_idle_{action.replace('-', '_')}_accepted", queued=bool(runtime.get("active")), data={"personalization_runtime": runtime})
    return None


def _handle_pipeline_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    if command in {"start-current-pipeline", "start-current-roughcut"}:
        logger.log(f"🤖 자동화 명령 수신: {command}")
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "")
        if state == "ST_PROC":
            return fail("already_processing")
        if command == "start-current-pipeline":
            starter = getattr(editor, "_on_start_clicked", None)
            if not callable(starter):
                return fail("pipeline_start_unavailable")
            starter()
            helpers.bring_to_front(owner)
            return ok(message="pipeline_started", data={"state_before": state})
        starter = getattr(editor, "_schedule_post_generation_roughcut_draft", None)
        if not callable(starter):
            return fail("roughcut_start_unavailable")
        starter(force=True)
        helpers.bring_to_front(owner)
        return ok(message="roughcut_started", data={"state_before": state, "media_path": str(getattr(editor, "media_path", "") or "")})
    return None


def handle_command(
    owner: Any,
    command_payload: dict[str, Any],
    command: str,
    *,
    ok,
    fail,
    logger,
    helpers: SimpleNamespace,
) -> dict[str, Any] | None:
    handlers = (
        _handle_editor_transport_command,
        _handle_editor_edit_command,
        _handle_snapshot_dialog_command,
        _handle_open_command,
        _handle_queue_command,
        _handle_save_export_command,
        _handle_mode_personalization_command,
        _handle_pipeline_command,
    )
    for handler in handlers:
        result = handler(owner, command_payload, command, ok=ok, fail=fail, logger=logger, helpers=helpers)
        if result is not None:
            return result
    return None
