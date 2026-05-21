from __future__ import annotations

import json
import os

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImage
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from core.runtime import config
from core.runtime.logger import get_logger
from ui.gpu_rendering import scenegraph_enabled


class _MirrorLabel(QLabel):
    text_changed = pyqtSignal(str)
    visible_changed = pyqtSignal(bool)

    def setText(self, text):
        next_text = str(text or "")
        if next_text == self.text():
            super().setText(next_text)
            return
        super().setText(next_text)
        self.text_changed.emit(next_text)

    def setVisible(self, visible):
        changed = bool(visible) != self.isVisible()
        super().setVisible(visible)
        if changed:
            self.visible_changed.emit(bool(visible))


class VideoPlayerTransportMixin:
    _CONTROL_BADGE_HEIGHT = 36
    _SOURCE_INFO_BADGE_MAX_WIDTH = 220
    _SOURCE_NAME_BADGE_MAX_WIDTH = 200

    def _log_video_transport_nonfatal(self, stage: str, exc: Exception) -> None:
        try:
            get_logger().log(f"⚠️ [video-transport:{stage}] {type(exc).__name__}: {exc}")
        except Exception:
            return

    def _create_transport_button(
        self,
        text: str,
        *,
        tooltip: str,
        width: int | None = None,
        font_size: int = 12,
        padding: str = "6px 12px",
        callback=None,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        if width is not None:
            button.setFixedWidth(int(width))
        button.setStyleSheet(self._control_button_style(font_size=font_size, padding=padding))
        if callable(callback):
            button.clicked.connect(callback)
        return button

    def _play_pause_tooltip_text(self) -> str:
        return (
            "재생/일시정지\n"
            "Tab: 기본\n"
            "Space: 캔버스\n"
            "반복재생 체크 시 선택 세그먼트만 반복\n"
            "캔버스 Space 두 번: 다음 세그먼트"
        )

    def _build_control_bar(self) -> QWidget:
        ctrl = QWidget()
        ctrl.setFixedHeight(44)
        ctrl.setStyleSheet("background: transparent; border: none;")
        uniform_gap = 6
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(uniform_gap)

        self.btn_scan_prev_cut = self._create_transport_button(
            "<<",
            tooltip="이전 컷 경계까지 빠르게 탐색",
            width=42,
            font_size=13,
            padding="6px 8px",
            callback=lambda: self.request_scan_cut(-1),
        )
        ctrl_layout.addWidget(self.btn_scan_prev_cut)

        self.btn_prev_frame = self._create_transport_button(
            "<",
            tooltip="이전 프레임",
            width=34,
            font_size=14,
            padding="6px 8px",
            callback=lambda: self.request_frame_step(-1),
        )
        ctrl_layout.addWidget(self.btn_prev_frame)

        self.btn_play = self._create_transport_button(
            "▶",
            tooltip=self._play_pause_tooltip_text(),
            callback=self.toggle_play,
        )
        ctrl_layout.addWidget(self.btn_play)

        self.btn_next_frame = self._create_transport_button(
            ">",
            tooltip="다음 프레임",
            width=34,
            font_size=14,
            padding="6px 8px",
            callback=lambda: self.request_frame_step(1),
        )
        ctrl_layout.addWidget(self.btn_next_frame)

        self.btn_scan_next_cut = self._create_transport_button(
            ">>",
            tooltip="다음 컷 경계까지 빠르게 탐색",
            width=42,
            font_size=13,
            padding="6px 8px",
            callback=lambda: self.request_scan_cut(1),
        )
        ctrl_layout.addWidget(self.btn_scan_next_cut)

        self.time_label = _MirrorLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #A9B0B7; font-size: 11px; font-weight: 500; background: transparent; border: none;")
        ctrl_layout.addWidget(self.time_label)

        self.frame_count_label = _MirrorLabel("F 0 / 0")
        self.frame_count_label.setObjectName("VideoFrameCountLabel")
        self.frame_count_label.setToolTip("현재 프레임 / 전체 프레임")
        self.frame_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_count_label.setWordWrap(False)
        self.frame_count_label.setFixedWidth(124)
        self.frame_count_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.frame_count_label.setStyleSheet(
            "QLabel#VideoFrameCountLabel {"
            " color: #8FE7FF;"
            " background: transparent;"
            " border: none;"
            " padding: 0 4px;"
            " font-size: 10px;"
            " font-weight: 800;"
            "}"
        )
        ctrl_layout.addWidget(self.frame_count_label)

        self.status_info_container = QWidget(ctrl)
        self.status_info_container.setObjectName("VideoStatusInfoContainer")
        self.status_info_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.status_info_container.setFixedHeight(self._CONTROL_BADGE_HEIGHT)
        status_layout = QHBoxLayout(self.status_info_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(uniform_gap)

        self.info_label = _MirrorLabel("영상 정보를 불러오는 중...")
        self.info_label.setObjectName("VideoSourceMetaLabel")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.info_label.setMinimumWidth(152)
        self.info_label.setMaximumWidth(self._SOURCE_INFO_BADGE_MAX_WIDTH)
        self.info_label.setFixedHeight(self._CONTROL_BADGE_HEIGHT)
        self.info_label.setStyleSheet(
            "QLabel#VideoSourceMetaLabel {"
            " color: #A9B0B7;"
            " background: #1A2127;"
            " border: 1px solid #2D3942;"
            " border-radius: 9px;"
            " padding: 2px 10px 1px 10px;"
            " font-size: 9px;"
            "}"
        )
        status_layout.addWidget(self.info_label, 0)
        status_layout.addStretch(1)

        self.source_name_label = _MirrorLabel("")
        self.source_name_label.setObjectName("VideoSourceNameLabel")
        self.source_name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.source_name_label.setWordWrap(True)
        self.source_name_label.setMinimumWidth(152)
        self.source_name_label.setMaximumWidth(self._SOURCE_NAME_BADGE_MAX_WIDTH)
        self.source_name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.source_name_label.setFixedHeight(self._CONTROL_BADGE_HEIGHT)
        self.source_name_label.setStyleSheet(
            "QLabel#VideoSourceNameLabel {"
            " color: #EAF2F8;"
            " background: #182126;"
            " border: 1px solid #2F4852;"
            " border-radius: 9px;"
            " padding: 2px 10px 1px 10px;"
            " font-size: 10px;"
            " font-weight: 700;"
            "}"
        )
        status_layout.addWidget(self.source_name_label, 0)

        ctrl_layout.addWidget(self.status_info_container, 1)
        return ctrl

    def _control_bar_video_content_insets(self) -> tuple[int, int]:
        control = getattr(self, "_control_bar_widget", None)
        video = getattr(self, "video_container", None)
        if control is None or video is None:
            return (0, 0)
        try:
            video_bounds = video.rect()
            video_w = max(1, int(video_bounds.width()))
            control_w = max(1, int(control.width()))
            video_rect = self._displayed_video_rect(video_bounds)
            scale = control_w / video_w
            left = max(0, int(round(int(video_rect.left()) * scale)))
            right_src = max(0, video_w - int(video_rect.left()) - int(video_rect.width()))
            right = max(0, int(round(right_src * scale)))
            return (left, right)
        except Exception:
            return (0, 0)

    def _apply_control_bar_video_content_insets(self) -> tuple[int, int]:
        left, right = self._control_bar_video_content_insets()
        layout_getter = getattr(getattr(self, "_control_bar_widget", None), "layout", None)
        layout = layout_getter() if callable(layout_getter) else None
        if layout is not None:
            try:
                current = layout.contentsMargins()
                if (current.left(), current.top(), current.right(), current.bottom()) != (left, 0, right, 0):
                    layout.setContentsMargins(left, 0, right, 0)
            except Exception:
                pass
        return (left, right)

    def _frame_step_hold_interval_ms(self) -> int:
        try:
            return max(45, int(os.environ.get("AI_SUBTITLE_FRAME_STEP_HOLD_INTERVAL_MS", "90")))
        except Exception:
            return 90

    def _frame_step_hold_delay_ms(self) -> int:
        try:
            return max(120, int(os.environ.get("AI_SUBTITLE_FRAME_STEP_HOLD_DELAY_MS", "280")))
        except Exception:
            return 280

    def _frame_step_button_clicked(self, direction: int):
        if bool(getattr(self, "_frame_step_hold_ignore_next_click", False)):
            self._frame_step_hold_ignore_next_click = False
            return
        self.request_frame_step(direction)

    def _start_frame_step_hold(self, direction: int):
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self._frame_step_hold_direction = direction
        self._frame_step_hold_active = False
        self._frame_step_hold_ignore_next_click = False
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.stop()
        if hasattr(self, "_frame_step_hold_start_timer"):
            self._frame_step_hold_start_timer.start(self._frame_step_hold_delay_ms())

    def _activate_frame_step_hold(self):
        direction = int(getattr(self, "_frame_step_hold_direction", 0) or 0)
        if direction == 0:
            return
        self._frame_step_hold_active = True
        self._frame_step_hold_ignore_next_click = True
        self.request_frame_step(direction)
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.setInterval(self._frame_step_hold_interval_ms())
            self._frame_step_hold_timer.start()

    def _emit_frame_step_hold(self):
        direction = int(getattr(self, "_frame_step_hold_direction", 0) or 0)
        if direction == 0:
            self.stop_frame_step_hold()
            return
        self.request_frame_step(direction)

    def stop_frame_step_hold(self):
        if hasattr(self, "_frame_step_hold_start_timer"):
            self._frame_step_hold_start_timer.stop()
        if hasattr(self, "_frame_step_hold_timer"):
            self._frame_step_hold_timer.stop()
        self._frame_step_hold_direction = 0
        self._frame_step_hold_active = False

    def capture_frame_step_guard_image(self, max_width: int = 96, max_height: int = 54):
        try:
            widget = getattr(self, "video_widget", None) or getattr(self, "video_container", None)
            if widget is None:
                return None
            pixmap = widget.grab()
            if pixmap is None or pixmap.isNull():
                return None
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
            if image.isNull():
                return None
            return image.scaled(
                int(max_width),
                int(max_height),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        except Exception:
            return None

    def set_scan_cut_active(self, direction: int):
        """Highlight << / >> while scan-cut is running. direction: -1, 0, 1."""
        try:
            direction = int(direction or 0)
        except Exception:
            direction = 0
        self._scan_cut_active_direction = direction

        inactive = self._control_button_style(font_size=13, padding="6px 8px")
        active = (
            "QPushButton { "
            "background: #1F8F4D; color: #FFFFFF; "
            "border: 1px solid #30D158; border-radius: 6px; "
            "padding: 6px 8px; font-size: 13px; font-weight: 800; "
            "} "
            "QPushButton:hover { background: #25A85A; color: #FFFFFF; } "
            "QPushButton:pressed { background: #187A40; }"
        )

        prev_btn = getattr(self, "btn_scan_prev_cut", None)
        next_btn = getattr(self, "btn_scan_next_cut", None)

        if prev_btn is not None:
            prev_btn.setStyleSheet(active if direction < 0 else inactive)
        if next_btn is not None:
            next_btn.setStyleSheet(active if direction > 0 else inactive)
        self._sync_quick_control_bar()

    def _control_button_style(self, *, font_size=12, padding="6px 12px") -> str:
        return f"""
            QPushButton {{
                background: #252B31; color: #F5F7FA;
                border: 1px solid #3A424A; padding: {padding}; font-weight: bold;
                border-radius: 6px; font-size: {int(font_size)}px;
            }}
            QPushButton:hover {{ background: #303841; }}
            QPushButton:pressed {{ background: #1D2329; }}
        """

    def _format_clock_time(self, sec: float | int | str | None) -> str:
        try:
            total_sec = max(0, int(float(sec or 0.0)))
        except Exception:
            total_sec = 0
        minutes, seconds = divmod(total_sec, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _time_label_text(self) -> str:
        return (
            f"{self._format_clock_time(getattr(self, 'current_time', 0.0))} / "
            f"{self._format_clock_time(getattr(self, 'total_time', 0.0))}"
        )

    def _refresh_time_label(self, *, force: bool = False) -> None:
        label = getattr(self, "time_label", None)
        if label is None:
            return
        pos_ms = int(float(getattr(self, "current_time", 0.0) or 0.0) * 1000)
        if force or abs(pos_ms - int(getattr(self, "_last_time_label_ms", -250) or -250)) >= 250:
            self._last_time_label_ms = pos_ms
            label.setText(self._time_label_text())

    def _format_probe_fps(self, fps_value) -> str:
        try:
            fps = float(fps_value or 0.0)
        except Exception:
            fps = 0.0
        if fps <= 0.0:
            return ""
        return f"{fps:.2f}".rstrip("0").rstrip(".") + "fps"

    def _format_probe_bitrate(self, bit_rate_value) -> str:
        try:
            bit_rate = int(bit_rate_value or 0)
        except Exception:
            bit_rate = 0
        if bit_rate <= 0:
            return ""
        if bit_rate >= 1_000_000:
            return f"{bit_rate / 1_000_000.0:.1f}".rstrip("0").rstrip(".") + "Mbps"
        if bit_rate >= 1_000:
            return f"{bit_rate / 1_000.0:.0f}kbps"
        return f"{bit_rate}bps"

    def _format_probe_color_info(self, info: dict | None) -> str:
        info = dict(info or {})
        pix_fmt = str(info.get("pix_fmt", "") or "").strip()
        primaries = str(info.get("color_primaries", "") or "").strip()
        color_space = str(info.get("color_space", "") or "").strip()
        transfer = str(info.get("color_transfer", "") or "").strip()
        tokens: list[str] = []
        if pix_fmt:
            tokens.append(pix_fmt)
        for value in (primaries, color_space, transfer):
            if value and value not in tokens:
                tokens.append(value)
            if len(tokens) >= 3:
                break
        if not tokens:
            return ""
        return " ".join(tokens)

    def _format_source_media_summary(self) -> str:
        info = dict(getattr(self, "_source_media_info", {}) or {})
        first_line: list[str] = []
        second_line: list[str] = []
        preview_label = str(getattr(self, "_source_preview_label", "") or "").strip()
        if preview_label:
            first_line.append(preview_label)
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        if width > 0 and height > 0:
            first_line.append(f"{width}x{height}")
        fps_text = self._format_probe_fps(info.get("fps", 0.0))
        if fps_text:
            first_line.append(fps_text)
        color_text = self._format_probe_color_info(info)
        if color_text:
            second_line.append(color_text)
        bitrate_text = self._format_probe_bitrate(info.get("bit_rate", 0))
        if bitrate_text:
            second_line.append(bitrate_text)
        lines = []
        if first_line:
            lines.append(" | ".join(part for part in first_line if part))
        if second_line:
            lines.append(" | ".join(part for part in second_line if part))
        return "\n".join(line for line in lines if line)

    def _source_info_fallback_text(self) -> str:
        status_text = str(getattr(self, "_source_info_status_text", "") or "").strip()
        if status_text:
            return status_text
        if str(getattr(self, "_current_source_path", "") or "").strip():
            return "메타데이터 준비 중"
        return ""

    def _refresh_source_info_label(self):
        label = getattr(self, "info_label", None)
        if label is None:
            return
        summary_text = self._format_source_media_summary()
        text = summary_text or self._source_info_fallback_text()
        label.setText(text)
        label.setToolTip(text)

    def _ensure_source_info_label_visible(self):
        label = getattr(self, "info_label", None)
        if label is None:
            return
        try:
            current_text = str(label.text() or "").strip()
        except Exception:
            current_text = ""
        if current_text:
            return
        if self._format_source_media_summary() or self._source_info_fallback_text():
            self._refresh_source_info_label()

    def _set_source_info_status(self, text: str):
        self._source_info_status_text = str(text or "")
        self._refresh_source_info_label()

    def apply_source_media_probe(self, path: str, info: dict | None):
        current_path = str(getattr(self, "_current_source_path", "") or "")
        target_path = str(path or "")
        try:
            if current_path and target_path and os.path.normpath(current_path) != os.path.normpath(target_path):
                return
        except Exception:
            if current_path and target_path and current_path != target_path:
                return
        probe_info = dict(info or {})
        self._source_media_info = probe_info
        width = int(probe_info.get("width", 0) or 0)
        height = int(probe_info.get("height", 0) or 0)
        self._source_width = width
        self._source_height = height
        if width > 0 and height > 0:
            self._source_aspect = width / height
        duration = float(probe_info.get("duration", 0.0) or 0.0)
        fps = float(probe_info.get("fps", 0.0) or 0.0)
        if duration > 0.0 or fps > 0.0:
            self._rebuild_frame_time_map(
                duration=duration or self.total_time or 0.0,
                fps=fps or self.frame_rate or 30.0,
            )
        if self._source_info_status_text in {"", "영상 정보를 불러오는 중...", "영상을 불러오는 중..."}:
            self._source_info_status_text = ""
        self._refresh_source_info_label()

    def _set_source_name_badge(self, path: str):
        name = os.path.basename(str(path or "").strip())
        self._source_display_name = name
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        label.setToolTip(name)
        self._refresh_source_name_label()

    def _refresh_source_name_label(self):
        label = getattr(self, "source_name_label", None)
        if label is None:
            return
        name = str(getattr(self, "_source_display_name", "") or "")
        label.setText(self._format_source_name_badge_text(label, name))
        label.setToolTip(name)

    def _badge_text_width(self, label: QLabel, *, fallback_width: int) -> int:
        width = int(getattr(label, "width", lambda: 0)() or 0)
        if width <= 0:
            try:
                max_width = int(label.maximumWidth() or 0)
                if 0 < max_width < 16777215:
                    width = max_width
            except Exception:
                width = 0
        if width <= 0:
            width = int(fallback_width or 0)
        return max(64, width - 22)

    def _format_source_name_badge_text(self, label: QLabel, name: str) -> str:
        text = str(name or "").replace("\n", " ").strip()
        if not text:
            return ""
        metrics = QFontMetrics(label.font())
        available = self._badge_text_width(label, fallback_width=self._SOURCE_NAME_BADGE_MAX_WIDTH)
        if metrics.horizontalAdvance(text) <= available:
            return text

        break_chars = " _-./|"
        best: tuple[int, str, str] | None = None
        for index in range(1, len(text)):
            first = text[:index]
            second = text[index:]
            if not first or not second:
                continue
            if metrics.horizontalAdvance(first) > available:
                continue
            second_elided = metrics.elidedText(second, Qt.TextElideMode.ElideRight, available)
            balance = abs(metrics.horizontalAdvance(first) - metrics.horizontalAdvance(second_elided))
            penalty = 0 if text[index - 1] in break_chars or text[index] in break_chars else 24
            score = balance + penalty
            if best is None or score < best[0]:
                best = (score, first, second_elided)
        if best is None:
            split_at = max(1, min(len(text) - 1, len(text) // 2))
            first = metrics.elidedText(text[:split_at], Qt.TextElideMode.ElideRight, available)
            second = metrics.elidedText(text[split_at:], Qt.TextElideMode.ElideRight, available)
            return f"{first}\n{second}"
        return f"{best[1]}\n{best[2]}"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_video_overlay()
        self._apply_control_bar_video_content_insets()
        self._refresh_source_info_label()
        self._refresh_source_name_label()
        self._sync_quick_control_bar()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_control_bar_widget", None) and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            quick = getattr(self, "_quick_control_bar", None)
            if quick is not None and callable(getattr(quick, "rootObject", None)):
                self._apply_control_bar_video_content_insets()
                quick.setGeometry(obj.rect())
                quick.raise_()
        return super().eventFilter(obj, event)

    def _create_quick_control_bar(self, parent):
        if not scenegraph_enabled("video"):
            return None
        qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "qml", "video_control_bar.qml"))
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            quick = QQuickWidget(parent)
            quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            quick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            quick.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            quick.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            quick.setClearColor(QColor(0, 0, 0, 0))
            quick.setSource(QUrl.fromLocalFile(qml_path))
            if quick.status() == QQuickWidget.Status.Error:
                quick.deleteLater()
                return None
            root = quick.rootObject()
            if root is not None:
                root.playRequested.connect(self.toggle_play)
                root.prevFrameRequested.connect(lambda: self.request_frame_step(-1))
                root.nextFrameRequested.connect(lambda: self.request_frame_step(1))
                root.prevScanRequested.connect(lambda: self.request_scan_cut(-1))
                root.nextScanRequested.connect(lambda: self.request_scan_cut(1))
            quick.setGeometry(parent.rect())
            quick.show()
            quick.raise_()
            return quick
        except Exception:
            return None

    def _quick_control_bar_state(self) -> dict:
        info_label = getattr(self, "info_label", None)
        info_text = ""
        if info_label is not None:
            try:
                info_text = str(info_label.text() or "")
            except Exception:
                info_text = ""
        content_left, content_right = self._control_bar_video_content_insets()
        return {
            "timeText": str(getattr(self.time_label, "text", lambda: "")() or ""),
            "infoText": info_text,
            "frameText": str(getattr(self.frame_count_label, "text", lambda: "")() or ""),
            "contentLeftInset": content_left,
            "contentRightInset": content_right,
            "sourceNameText": (
                str(getattr(self.source_name_label, "text", lambda: "")() or "")
                if not bool(getattr(self.source_name_label, "isHidden", lambda: True)())
                else ""
            ),
            "playText": str(getattr(self.btn_play, "text", lambda: "▶")() or "▶"),
            "playing": bool(self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState),
            "scanPrevActive": bool(getattr(self, "_scan_cut_active_direction", 0) < 0),
            "scanNextActive": bool(getattr(self, "_scan_cut_active_direction", 0) > 0),
        }

    def _sync_quick_control_bar(self, *_args):
        quick = getattr(self, "_quick_control_bar", None)
        if quick is None or not callable(getattr(quick, "rootObject", None)):
            return
        try:
            # QWidget 전환 테스트 더블은 QML rootObject가 없으므로 실제 QQuickWidget일 때만 동기화한다.
            root = quick.rootObject()
            if root is None:
                return
            state = self._quick_control_bar_state()
            for key, value in state.items():
                root.setProperty(key, value)
        except Exception as exc:
            self._log_video_transport_nonfatal("sync_quick_control_bar", exc)

    def _get_video_ui_interval_ms(self) -> int:
        try:
            settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    return max(24, min(80, int(json.load(f).get("video_ui_interval_ms", 50))))
        except Exception as exc:
            self._log_video_transport_nonfatal("load_ui_interval", exc)
        return 50

    def request_scan_cut(self, direction: int):
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self.scan_cut_requested.emit(direction)

    def request_frame_step(self, direction: int):
        try:
            step = int(direction or 0)
        except Exception:
            step = 1
        if step == 0:
            return
        self.pause_video()
        owner = self
        visited: set[int] = set()
        while owner is not None and id(owner) not in visited:
            visited.add(id(owner))
            handler = getattr(owner, "_on_step_frame", None)
            if callable(handler):
                try:
                    handler(step)
                    return
                except Exception:
                    break
            next_owner = None
            try:
                next_owner = owner.parentWidget()
            except Exception:
                next_owner = None
            if next_owner is None:
                try:
                    next_owner = owner.parent()
                except Exception:
                    next_owner = None
            owner = next_owner
        self.frame_step_requested.emit(step)

    def toggle_play(self):
        source_prepared = False
        if not getattr(self, "_source_ready", True):
            self._pending_autoplay = True
            # macOS/QMediaPlayer can miss LoadedMedia after long STT/LLM runs; recover if the source is already bound.
            if not self._ensure_media_source_loaded():
                return
            self._source_ready = True
            self._pending_autoplay = False
            source_prepared = True
        starting = self.media_player.playbackState() != self.media_player.PlaybackState.PlayingState
        if starting:
            prepare_repeat = getattr(self, "_repeat_play_prepare_callback", None)
            if callable(prepare_repeat):
                try:
                    prepare_repeat()
                except Exception as exc:
                    self._log_video_transport_nonfatal("prepare_repeat_playback", exc)
        self._ensure_audio_outputs()
        if not source_prepared and not self._ensure_media_source_loaded():
            self._pending_autoplay = True
            return
        self._hide_thumbnail()
        if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, "has_vocal_track", False):
                self._ensure_vocal_player().pause()
        else:
            if bool(getattr(self, "_provider_refresh_requested", False)):
                self._refresh_provider_segments(force=False)
            self._video_surface_primed = True
            start_frame = self.frame_for_sec(max(0.0, float(getattr(self, "current_time", 0.0) or 0.0)))
            last_playable_frame = self._last_playable_frame()
            if self.total_time > 0.0 and start_frame >= last_playable_frame:
                start_frame = last_playable_frame
                start_sec = self.sec_for_frame(start_frame)
                self.current_frame = start_frame
                self.current_time = start_sec
                self.set_subtitle_display_time(start_sec, refresh=False)
            else:
                start_sec = self.sec_for_frame(start_frame)
            if start_sec > 0.05:
                self.media_player.setPosition(self.position_ms_for_frame(start_frame))
            if getattr(self, "has_vocal_track", False):
                self._ensure_vocal_player().setPosition(self.media_player.position())
            self.media_player.play()
            if getattr(self, "has_vocal_track", False):
                self._ensure_vocal_player().play()
        self._update_btn()

    def pause_video(self):
        if self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState:
            self.media_player.pause()
            if getattr(self, "has_vocal_track", False):
                self._ensure_vocal_player().pause()
            self._update_btn()

    def _update_btn(self):
        is_playing = self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState
        if self._last_btn_state == is_playing:
            return
        self._last_btn_state = is_playing
        self.btn_play.setText("⏸" if is_playing else "▶")
        self._sync_quick_control_bar()

    def _ui_tick(self):
        self._update_btn()
        self._ensure_source_info_label_visible()
        self._refresh_time_label()
        if not getattr(self, "_source_ready", True):
            return
        is_playing = self.media_player.playbackState() == self.media_player.PlaybackState.PlayingState
        target_interval = self._play_ui_interval_ms if is_playing else self._idle_ui_interval_ms
        try:
            if int(self._ui_timer.interval()) != int(target_interval):
                self._ui_timer.setInterval(int(target_interval))
        except Exception as exc:
            self._log_video_transport_nonfatal("retime_ui_tick", exc)
        if is_playing:
            self.current_playback_frame_time()
            self.set_subtitle_display_time(self.current_time, refresh=False)
        else:
            if bool(getattr(self, "_provider_refresh_requested", False)):
                self._refresh_provider_segments(force=False)

        self._update_frame_count_label()
        self._refresh_subtitle_now()


__all__ = ["_MirrorLabel", "VideoPlayerTransportMixin"]
