from __future__ import annotations

from core.runtime.logger import get_logger
from ui.dialogs.qml_popup import show_context_menu


class EditorPipelinePlayheadActionsMixin:
    def _current_cut_boundary_level(self) -> str:
        try:
            from core.settings import load_settings
            from core.cut_boundary import cut_boundary_level

            return str(cut_boundary_level(load_settings() or {}) or "medium")
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 단계 조회 실패: {exc}")
            return "medium"

    def _cut_boundary_level_choices(self) -> list[tuple[str, str]]:
        return [
            ("off", "사용안함"),
            ("low", "낮음 - 3초 간격"),
            ("medium", "중간 - 2초 간격"),
        ]

    def _add_cut_boundary_level_submenu(self, menu):
        try:
            current = self._current_cut_boundary_level()
            sub = menu.addMenu("🎬 컷 경계 단계")
            for level, label in self._cut_boundary_level_choices():
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(level == current)
                act.triggered.connect(lambda checked=False, lv=level: self._set_cut_boundary_level_from_menu(lv))
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 단계 메뉴 생성 실패: {exc}")

    def _set_cut_boundary_level_from_menu(self, level: str):
        try:
            from core.settings import load_settings
            try:
                from core.settings import save_settings
            except Exception:
                save_settings = None

            settings = load_settings() or {}
            level = str(level or "medium")
            if level == "high":
                level = "medium"
            settings["scan_cut_boundary_level"] = level
            settings["cut_boundary_level"] = level

            settings["scan_cut_enabled"] = level != "off"
            settings["scan_cut_auto_enabled"] = level != "off"
            settings["cut_boundary_enabled"] = level != "off"

            labels = {
                "off": "사용안함",
                "low": "낮음 - 3초 간격",
                "medium": "중간 - 2초 간격",
            }
            masks = {
                "off": "off",
                "low": "cross4",
                "medium": "cross5",
            }
            settings["scan_cut_boundary_label"] = labels.get(level, labels["medium"])
            settings["scan_cut_grid_mask"] = masks.get(level, "cross5")

            if callable(save_settings):
                save_settings(settings)

            if hasattr(self, "settings") and isinstance(self.settings, dict):
                self.settings.update(settings)

            try:
                self.sm.set_custom_status(f"🎬 컷 경계 단계: {settings['scan_cut_boundary_label']}")
            except Exception:
                pass

            get_logger().log(f"  🎚️ [컷 경계] 단계 변경: {settings['scan_cut_boundary_label']}")
        except Exception as exc:
            get_logger().log(f"⚠️ 컷 경계 단계 저장 실패: {exc}")

    def _playhead_menu_items(self) -> list[dict]:
        items = []
        current = self._current_cut_boundary_level()
        level_labels = {
            "off": "컷 경계: 사용안함",
            "low": "컷 경계: 낮음 - 3초 간격",
            "medium": "컷 경계: 중간 - 2초 간격",
        }
        for level in ("off", "low", "medium"):
            items.append(
                {
                    "id": f"cut_boundary:{level}",
                    "label": level_labels[level],
                    "checked": level == current,
                    "accent": "#34C759" if level != "off" else "#A9B0B7",
                }
            )
        items.append({"separator": True})
        items.extend(
            [
                {"id": "re_segment", "label": "현재 자막 세그먼트만 재인식", "accent": "#5AC8FA"},
                {"id": "re_from", "label": "현재부터 끝까지 자막 재인식", "accent": "#34C759"},
            ]
        )
        return items

    def _show_playhead_menu(self, gpos, sec):
        chosen = show_context_menu(self, gpos, self._playhead_menu_items())
        if not chosen:
            return
        if chosen.startswith("cut_boundary:"):
            self._set_cut_boundary_level_from_menu(chosen.split(":", 1)[1])
        elif chosen == "re_segment":
            self._re_recognize_segment(sec)
        elif chosen == "re_from":
            self._re_recognize_from(sec)

    def _segment_start_at_time(self, sec: float) -> float:
        start_sec = float(sec or 0.0)
        for seg in self._get_current_segments():
            try:
                seg_start = float(seg.get("start", 0.0))
                seg_end = float(seg.get("end", 0.0))
            except Exception:
                continue
            if seg_start <= sec < seg_end:
                return seg_start
        return start_sec

    def _segment_range_at_time(self, sec: float) -> tuple[float, float] | None:
        for seg in self._get_current_segments():
            try:
                seg_start = float(seg.get("start", 0.0))
                seg_end = float(seg.get("end", 0.0))
            except Exception:
                continue
            if seg_start <= sec < seg_end:
                return seg_start, seg_end
        return None

    def _re_recognize_segment(self, sec):
        seg_range = self._segment_range_at_time(float(sec or 0.0))
        if seg_range is None:
            return
        self._run_partial_backend(seg_range[0], seg_range[1], is_single=True)

    def _re_recognize_from(self, sec):
        start_sec = self._segment_start_at_time(float(sec or 0.0))
        end_sec = self._partial_rerun_total_end()
        self._run_partial_backend(start_sec, end_sec, is_single=False)
