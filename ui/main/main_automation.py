# Version: 03.14.33
# Phase: PHASE2
"""Automation and external app-command helpers for MainWindow."""

from __future__ import annotations

import os
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.runtime import config
from ui.main.app_command_bridge import dispatch_app_command, handle_app_command_signal


class MainAutomationMixin:
    def dispatch_external_app_command(self, payload, *, timeout_sec: float = 12.0):
        return dispatch_app_command(self, payload, timeout_sec=timeout_sec)

    def _do_execute_external_app_command(self, payload, reply_state=None):
        handle_app_command_signal(self, payload, reply_state)

    def _automation_guided_snapshot_state_payload(self):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict):
            state = {}
        snapshots = []
        for item in list(state.get("snapshots", []) or []):
            if isinstance(item, dict):
                snapshots.append(
                    {
                        "label": str(item.get("label", "") or ""),
                        "stage_text": str(item.get("stage_text", "") or ""),
                        "path": str(item.get("path", "") or ""),
                        "sequence": int(item.get("sequence", 0) or 0),
                    }
                )
        stage_events = []
        for item in list(state.get("stage_events", []) or []):
            if isinstance(item, dict):
                stage_events.append(
                    {
                        "key": str(item.get("key", "") or ""),
                        "label": str(item.get("label", "") or ""),
                        "text": str(item.get("text", "") or ""),
                        "sequence": int(item.get("sequence", 0) or 0),
                    }
                )
        last_async = dict(getattr(self, "_last_async_snapshot_result", {}) or {})
        pending_async = []
        for item in list(getattr(self, "_pending_async_snapshots", []) or []):
            if isinstance(item, dict):
                pending_async.append(
                    {
                        "path": str(item.get("path", "") or ""),
                        "requested_at": float(item.get("requested_at", 0.0) or 0.0),
                    }
                )
        return {
            "active": bool(state.get("active", False)),
            "media_path": str(state.get("media_path", "") or ""),
            "snapshot_dir": str(state.get("snapshot_dir", "") or ""),
            "last_stage": str(state.get("last_stage", "") or ""),
            "last_stage_key": str(state.get("last_stage_key", "") or ""),
            "last_stage_label": str(state.get("last_stage_label", "") or ""),
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "stage_event_count": len(stage_events),
            "stage_events": stage_events,
            "latest_snapshot_path": str((snapshots[-1].get("path", "") if snapshots else "") or ""),
            "pending_async_snapshot_count": len(pending_async),
            "pending_async_snapshots": pending_async,
            "last_async_snapshot": last_async,
        }

    def _automation_begin_guided_subtitle_run(self, media_path: str, snapshot_dir: str = ""):
        base_name = os.path.splitext(os.path.basename(str(media_path or "").strip()))[0] or "media"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = str(snapshot_dir or "").strip() or os.path.join(str(config.OUTPUT_DIR or ""), "guided_runs", f"{base_name}_{stamp}")
        os.makedirs(target_dir, exist_ok=True)
        self._guided_snapshot_run = {
            "active": True,
            "media_path": str(media_path or ""),
            "snapshot_dir": target_dir,
            "snapshots": [],
            "captured_labels": set(),
            "captured_stage_keys": set(),
            "stage_events": [],
            "stage_event_keys": set(),
            "last_stage": "",
            "last_stage_key": "",
            "last_stage_label": "",
            "sequence": 0,
        }
        return self._automation_guided_snapshot_state_payload()

    def _automation_classify_guided_stage(self, text: str):
        raw = str(text or "").strip()
        if not raw:
            return "", ""
        lowered = raw.lower()
        if "자막 생성 완료" in raw or "backend_done" in lowered:
            return "completed", "자막 생성 완료"
        if "저장 준비 중" in raw or ("저장" in raw and "실패" not in raw):
            return "save", "저장"
        if "러프컷" in raw and ("llm" in lowered or "초안" in raw or "running" in lowered or "queued" in lowered):
            return "roughcut-llm", "러프컷 LLM"
        if "컷 경계" in raw:
            return "cut-boundary", "컷 경계"
        if any(token in raw for token in ("오디오 추출", "오토 오디오", "음성 향상", "ClearVoice")) or "[음성]" in raw:
            return "audio-filter", "음성 필터"
        if any(token in lowered for token in ("stt", "whisper")) or "자막 llm" in lowered or "단어 타임태그" in raw or "자막 생성 중" in raw:
            return "subtitle-generation", "자막 생성"
        return "", ""

    def _automation_record_guided_stage(self, key: str, label: str, text: str, *, capture: bool = False):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return {}
        normalized_key = str(key or "").strip()
        normalized_label = str(label or "").strip()
        normalized_text = str(text or "").strip()
        if not normalized_key:
            return {}
        state["last_stage"] = normalized_text or normalized_label or normalized_key
        state["last_stage_key"] = normalized_key
        state["last_stage_label"] = normalized_label
        event_keys = state.setdefault("stage_event_keys", set())
        if normalized_key in event_keys:
            return {}
        event_keys.add(normalized_key)
        events = state.setdefault("stage_events", [])
        event = {
            "key": normalized_key,
            "label": normalized_label,
            "text": normalized_text,
            "sequence": len(events) + 1,
        }
        events.append(event)
        if capture:
            return self._automation_capture_guided_snapshot(normalized_key, stage_text=normalized_text, force=True)
        return event

    def _automation_capture_guided_snapshot(self, label: str, *, stage_text: str = "", force: bool = False):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not state:
            return {}
        label_text = str(label or "").strip().lower() or "snapshot"
        slug_chars = []
        previous_dash = False
        for ch in label_text:
            if ch.isascii() and ch.isalnum():
                slug_chars.append(ch)
                previous_dash = False
            elif not previous_dash:
                slug_chars.append("-")
                previous_dash = True
        slug = "".join(slug_chars).strip("-") or "snapshot"
        captured_labels = state.setdefault("captured_labels", set())
        if not force and slug in captured_labels:
            return {}
        sequence = int(state.get("sequence", 0) or 0) + 1
        state["sequence"] = sequence
        snapshot_dir = str(state.get("snapshot_dir", "") or "")
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_path = os.path.join(snapshot_dir, f"{sequence:02d}_{slug}.png")
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        pixmap = self.grab()
        if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
            return {}
        if not bool(pixmap.save(snapshot_path, "PNG")):
            return {}
        captured_labels.add(slug)
        snapshot = {
            "label": str(label or ""),
            "stage_text": str(stage_text or ""),
            "path": snapshot_path,
            "sequence": sequence,
        }
        state.setdefault("snapshots", []).append(snapshot)
        state["last_stage"] = str(stage_text or label or "")
        return snapshot

    def _automation_request_async_snapshot_capture(self, snapshot_path: str):
        path = str(snapshot_path or "").strip()
        if not path:
            return {}
        request = {
            "path": path,
            "requested_at": time.time(),
        }
        self._pending_async_snapshots.append(request)
        QTimer.singleShot(0, self._automation_flush_async_snapshot_queue)
        return request

    def _automation_flush_async_snapshot_queue(self):
        pending = list(getattr(self, "_pending_async_snapshots", []) or [])
        if not pending:
            return
        request = pending[0]
        path = str(request.get("path", "") or "")
        result = {"ok": False, "path": path}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass
        try:
            pixmap = self.grab()
            if pixmap is not None and not getattr(pixmap, "isNull", lambda: True)():
                saved = bool(pixmap.save(path, "PNG"))
                result = {
                    "ok": saved,
                    "path": path,
                    "width": int(getattr(pixmap, "width", lambda: 0)() or 0),
                    "height": int(getattr(pixmap, "height", lambda: 0)() or 0),
                    "bytes": int(os.path.getsize(path)) if saved and os.path.isfile(path) else 0,
                }
        except Exception:
            result = {"ok": False, "path": path}
        self._last_async_snapshot_result = dict(result)
        try:
            self._pending_async_snapshots = self._pending_async_snapshots[1:]
        except Exception:
            self._pending_async_snapshots = []
        if self._pending_async_snapshots:
            QTimer.singleShot(50, self._automation_flush_async_snapshot_queue)

    def _automation_capture_processing_stage(self, stage_text: str):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        text = str(stage_text or "").strip()
        if not text:
            return
        key, label = self._automation_classify_guided_stage(text)
        if not key:
            state["last_stage"] = text
            return
        self._automation_record_guided_stage(key, label, text, capture=True)

    def _automation_track_log_line(self, line: str):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        text = str(line or "").strip()
        if not text:
            return
        key, label = self._automation_classify_guided_stage(text)
        if not key:
            return
        self._automation_record_guided_stage(key, label, text, capture=True)

    def _automation_finalize_guided_snapshot(self, reason: str = "backend_done"):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        self._automation_record_guided_stage("completed", "자막 생성 완료", str(reason or "backend_done"), capture=True)
        state["active"] = False
