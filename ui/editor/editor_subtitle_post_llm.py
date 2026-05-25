"""Global-canvas subtitle post-processing actions."""

from __future__ import annotations

import os
import threading
from typing import Any

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from core.runtime import config
from core.runtime.logger import get_logger


class EditorSubtitlePostLlmMixin:
    def _subtitle_post_llm_model_options(self) -> list[tuple[str, str, str]]:
        settings = dict(getattr(self, "settings", {}) or {})
        options: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(label: str, provider: str, model: str) -> None:
            provider_key = str(provider or "ollama").strip().lower()
            model_name = str(model or "").strip()
            if not model_name or "사용 안함" in model_name or provider_key == "none":
                return
            key = (provider_key, model_name)
            if key in seen:
                return
            seen.add(key)
            options.append((str(label or model_name), provider_key, model_name))

        add(
            f"현재 자막 LLM · {settings.get('selected_model', getattr(config, 'OLLAMA_MODEL', 'exaone3.5:7.8b'))}",
            settings.get("selected_llm_provider", "ollama"),
            settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b")),
        )
        add(
            f"러프컷 LLM · {settings.get('roughcut_llm_model', '')}",
            settings.get("roughcut_llm_provider", settings.get("selected_llm_provider", "ollama")),
            settings.get("roughcut_llm_model", ""),
        )
        try:
            from core.model_manager import get_available_models

            for item in get_available_models(include_hidden=False, include_runtime_discovered=True):
                if not (item.get("installed") or item.get("discovered")):
                    continue
                category = str(item.get("category") or "").strip()
                if category.upper() != "LLM":
                    continue
                details = dict(item.get("details", {}) or {})
                provider = details.get("provider", "ollama")
                name = str(item.get("name") or item.get("id") or "").strip()
                if name.startswith("Ollama ("):
                    continue
                add(f"{category} · {name}", provider, name)
        except Exception:
            pass
        try:
            from core.llm.provider_registry import cloud_model_items

            for item in cloud_model_items():
                details = dict(item.get("details", {}) or {})
                add(
                    str(item.get("display_name") or item.get("name") or ""),
                    details.get("provider", ""),
                    str(item.get("name") or ""),
                )
        except Exception:
            pass
        if not options:
            add("Ollama 기본 · exaone3.5:7.8b", "ollama", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
        return options

    def _select_subtitle_post_llm_model(self, title: str) -> tuple[str, str] | None:
        options = self._subtitle_post_llm_model_options()
        labels = [label for label, _provider, _model in options]
        selected, ok = QInputDialog.getItem(
            self,
            title,
            "사용할 LLM:",
            labels,
            0,
            False,
        )
        if not ok or not selected:
            return None
        for label, provider, model in options:
            if label == selected:
                return provider, model
        return None

    def _handle_global_subtitle_spellcheck_request(self) -> None:
        self._start_subtitle_post_llm_action("spellcheck")

    def _handle_global_subtitle_translate_english_request(self) -> None:
        self._start_subtitle_post_llm_action("translate_en")

    def _start_subtitle_post_llm_action(self, action: str) -> None:
        if bool(getattr(self, "_subtitle_post_llm_running", False)):
            QMessageBox.information(self, "자막 LLM", "이미 자막 후처리 LLM이 실행 중입니다.")
            return
        title = "띄워쓰기 맞춤법 검사 LLM 선택" if action == "spellcheck" else "영어 번역 LLM 선택"
        selected = self._select_subtitle_post_llm_model(title)
        if selected is None:
            return
        provider, model = selected
        getter = getattr(self, "_get_current_segments", None)
        rows = getter(force_rebuild=True) if callable(getter) else []
        rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        if not any(str(row.get("text", "") or "").strip() and not row.get("is_gap") for row in rows):
            QMessageBox.information(self, "자막 LLM", "처리할 자막 텍스트가 없습니다.")
            return
        self._subtitle_post_llm_running = True
        get_logger().log(
            f"🧠 [자막 후처리] {title} 시작: provider={provider}, model={model}, rows={len(rows)}"
        )

        def worker() -> None:
            try:
                from core.engine.subtitle_post_llm import run_subtitle_post_llm_action

                updated, changed = run_subtitle_post_llm_action(
                    action,
                    rows,
                    provider=provider,
                    model=model,
                )
                self.sig_subtitle_post_llm_finished.emit(
                    action,
                    updated,
                    {"changed": changed, "provider": provider, "model": model},
                )
            except Exception as exc:
                self.sig_subtitle_post_llm_failed.emit(action, str(exc))

        thread = threading.Thread(target=worker, name=f"subtitle-post-llm-{action}", daemon=True)
        self._subtitle_post_llm_thread = thread
        thread.start()

    def _english_translation_srt_path(self) -> str:
        media_path = str(getattr(self, "media_path", "") or "")
        if media_path:
            from core.path_manager import get_srt_path

            srt_path = get_srt_path(media_path)
        else:
            outputs = list(getattr(self, "_last_saved_srt_outputs", []) or [])
            srt_path = str(outputs[0][0]) if outputs else ""
        if not srt_path:
            srt_path = os.path.abspath("subtitle.srt")
        root, _ext = os.path.splitext(srt_path)
        return f"{root}_영어.srt"

    def _on_subtitle_post_llm_finished(self, action: str, rows: object, meta: object) -> None:
        self._subtitle_post_llm_running = False
        updated_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        meta_dict = dict(meta or {}) if isinstance(meta, dict) else {}
        changed = int(meta_dict.get("changed", 0) or 0)
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        reloader = getattr(self, "_reload_segments_from_list", None)
        if callable(reloader):
            reloader(updated_rows, preserve_view=True, mark_dirty=(action == "spellcheck"))
        if action == "translate_en":
            out_path = self._english_translation_srt_path()
            try:
                from core.engine.subtitle_engine import save_srt

                save_srt(
                    updated_rows,
                    out_path,
                    fps=getattr(self, "video_fps", 30.0),
                    write_backup=False,
                )
                get_logger().log(
                    f"✅ [자막 번역] 영어 SRT 저장 완료: {os.path.basename(out_path)} "
                    f"(프로젝트 파일 저장 안 함, 변경 {changed}개)"
                )
            except Exception as exc:
                QMessageBox.warning(self, "영어 번역", f"영어 SRT 저장 실패:\n{exc}")
                return
        else:
            get_logger().log(f"✅ [자막 맞춤법] 에디터/세그먼트 반영 완료: 변경 {changed}개")

    def _on_subtitle_post_llm_failed(self, action: str, reason: str) -> None:
        self._subtitle_post_llm_running = False
        label = "띄워쓰기 맞춤법 검사" if action == "spellcheck" else "영어 번역"
        get_logger().log(f"❌ [자막 후처리] {label} 실패: {reason}")
        QMessageBox.warning(self, label, f"LLM 처리 실패:\n{reason}")
