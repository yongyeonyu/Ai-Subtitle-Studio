from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TEXT_RULES: tuple[dict[str, Any], ...] = (
    {
        "path": "ui/timeline/timeline_canvas.py",
        "owner": "TimelineCanvas",
        "required": (
            'TIMELINE_RENDER_BACKEND_2D = "qwidget-2d"',
            "TimelineCanvasBase = QWidget",
            "self._single_owner_2d_renderer = True",
            "self._external_playhead_overlay = False",
            "self._scenegraph_subtitle_rendering = False",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "accelerated_widget_base", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/timeline_canvas.py",
        "owner": "TimelineSingleOwnerPlayheadInvalidation",
        "backend": "qwidget-2d-full-canvas-repaint",
        "required": (
            "def set_playhead(self, sec, *, visual_sec: float | None = None):",
            "def set_shadow_playhead(self, sec) -> bool:",
            "def set_drag_shadow_playhead(self, sec) -> bool:",
            "def _update_dirty_rect(self, rect: QRect):",
        ),
        "required_count": (
            {
                "pattern": "if self._timeline_uses_single_owner_2d():",
                "min": 4,
            },
            {
                "pattern": "self.update()\n            return",
                "min": 1,
            },
            {
                "pattern": "self.update()\n            return True",
                "min": 2,
            },
            {
                "pattern": "self.update()\n            self._notify_scenegraph_layer()\n            return",
                "min": 1,
            },
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "accelerated_widget_base", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/timeline_global.py",
        "owner": "GlobalCanvas",
        "required": (
            'GLOBAL_TIMELINE_RENDER_BACKEND_2D = "qwidget-2d"',
            "GlobalCanvasBase = QWidget",
            "self._single_owner_2d_renderer = True",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "accelerated_widget_base", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/timeline_widget.py",
        "owner": "TimelineWidget",
        "required": (
            "def _create_scenegraph_layer(self):",
            "self.canvas._scenegraph_subtitle_rendering = False",
            "return None",
            "_single_owner_2d_renderer",
            "layer.set_visible(False)",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget("),
    },
    {
        "path": "ui/timeline/timeline_paint.py",
        "owner": "TimelinePaintMixin",
        "backend": "qwidget-2d-painter-owner",
        "required": (
            "should_paint_subtitle_segment_text(",
            "return False",
            "def _draw_canvas_playhead(",
            "build_cut_boundary_work_lane_paint_plan(",
            "build_stt_preview_lane_paint_plan(",
            "diamond_pairs = self._diamond_pairs()",
            "shadow_playhead_sec = getattr(self, \"shadow_playhead_sec\", None)",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/timeline_paint_helpers.py",
        "owner": "TimelinePaintHelpers",
        "backend": "qwidget-2d-plan-only",
        "required": (
            "def should_paint_subtitle_segment_text(",
            "if native_inline_active:",
            "return False",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/paint_passes.py",
        "owner": "TimelinePaintPassPlanner",
        "backend": "qwidget-2d-plan-only",
        "required": (
            "The painter still owns drawing",
            "def build_cut_boundary_work_lane_paint_plan(",
            "def build_gap_lane_paint_plan(",
            "def build_stt_preview_lane_paint_plan(",
            "def build_aggregate_vector_subtitle_paint_plan(",
        ),
        "forbidden": ("from PyQt6.QtGui import QPainter", "QPainter(", "QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/editor/ux/timeline_input.py",
        "owner": "TimelineInputHitTargets",
        "backend": "qwidget-2d-input-only",
        "required": (
            "def _handle_polygon(",
            "def _diamond_pairs(",
            "def _playhead_handle_hit_rect(",
            "self._emit_scrub_with_playhead_cut_magnet(",
            "def _update_drag_visual_rect(",
            "self.update(dirty)",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport", "scenegraph_enabled("),
    },
    {
        "path": "ui/editor/ux/timeline_input_shadow.py",
        "owner": "TimelineInputShadowPlayhead",
        "backend": "qwidget-2d-input-only",
        "required": (
            "def _emit_scrub_with_playhead_cut_magnet(",
            "self._set_shadow_playhead(snap_sec)",
            "self._emit_scrub_with_shadow(target_sec)",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport", "scenegraph_enabled("),
    },
    {
        "path": "ui/timeline/timeline_waveform.py",
        "owner": "TimelineWaveformSource",
        "backend": "waveform-data-source",
        "required": (
            "WAVEFORM_CACHE_SCHEMA",
            "def _downsample_waveform_raw(",
            "def patch_waveform_buffer(",
            "class WaveformWorker(QThread):",
        ),
        "forbidden": ("from PyQt6.QtGui import QPainter", "QPainter(", "QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/timeline/stt_preview_layout.py",
        "owner": "STTPreviewLaneLayout",
        "backend": "qwidget-2d-layout-only",
        "required": (
            "MAX_STT_PREVIEW_SUBLANES",
            "def assign_stt_preview_lanes(",
            "def stt_preview_lane_geometry(",
        ),
        "forbidden": ("from PyQt6.QtGui import QPainter", "QPainter(", "QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/editor/ux/timeline_inline_text_editor.py",
        "owner": "TimelineInlineTextEdit",
        "backend": "opaque-qwidget",
        "required": (
            'self.setObjectName("timelineInlineTextEdit")',
            'self.setProperty("timelineInlineEditorRole", "segment-inline-locked")',
            "WA_TranslucentBackground, False",
            "WA_OpaquePaintEvent",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "WA_TranslucentBackground, True"),
    },
    {
        "path": "ui/editor/ux/subtitle_text_edit.py",
        "owner": "SubtitleTextEditQmlOverlayGate",
        "backend": "explicit-diagnostic-gate",
        "required": (
            "AI_SUBTITLE_EDITOR_TEXT_QML",
            "explicit diagnostic opt-in",
            'if not scenegraph_enabled("editor"):',
            "from PyQt6.QtQuickWidgets import QQuickWidget",
        ),
        "forbidden": ("QQuickWidget(self)\n            layer.show()\n            return layer",),
    },
    {
        "path": "ui/editor/video_player_transport.py",
        "owner": "VideoControlBarQmlGate",
        "backend": "explicit-scenegraph-gate",
        "required": (
            'if not scenegraph_enabled("video"):',
            "from PyQt6.QtQuickWidgets import QQuickWidget",
            "quick = QQuickWidget(parent)",
        ),
        "forbidden": ("quick = QQuickWidget(parent)\n            quick.show()",),
    },
    {
        "path": "ui/editor/video_overlay_widgets.py",
        "owner": "VideoSubtitleOverlayQmlGate",
        "backend": "explicit-diagnostic-gate",
        "required": (
            "AI_SUBTITLE_ENABLE_QML_VIDEO_SUBTITLE_OVERLAY",
            'if not scenegraph_enabled("video"):',
            "from PyQt6.QtQuickWidgets import QQuickWidget",
        ),
        "forbidden": ("return cls(qml_path, parent)\n\n    def __init__",),
    },
    {
        "path": "ui/timeline/timeline_scenegraph.py",
        "owner": "TimelineSceneGraphLayerGate",
        "backend": "explicit-scenegraph-gate",
        "required": (
            "class TimelineSceneGraphLayer:",
            'return scenegraph_enabled("timeline") and QML_PATH.exists()',
            "self.widget.setVisible(False)",
        ),
        "forbidden": ("TimelineSceneGraphLayer(", "self.widget.show()"),
    },
    {
        "path": "ui/gpu_rendering.py",
        "owner": "GpuRenderingGate",
        "backend": "explicit-diagnostic-gate",
        "required": (
            "explicit diagnostics only",
            "editor_rendering_scenegraph_opt_in_enabled",
            "return False",
        ),
        "forbidden": ("return not gpu_widgets_enabled(feature_key)",),
    },
)


ORDER_RULES: tuple[dict[str, Any], ...] = (
    {
        "path": "ui/timeline/timeline_paint.py",
        "owner": "TimelinePaintOrder",
        "backend": "qwidget-2d-painter-owner",
        "ordered": (
            "_draw_subtitle_score_labels(final_stt_segments)",
            "diamond_pairs = self._diamond_pairs()",
            "shadow_playhead_sec = getattr(self, \"shadow_playhead_sec\", None)",
            "drag_shadow_playhead_sec = getattr(self, \"_drag_shadow_playhead_sec\", None)",
            "include_subtitle_band=not bool(getattr(self, \"_edit_active\", False))",
            "include_non_subtitle_band=True",
            "include_handle=True",
        ),
    },
)


def _playhead_dirty_rect_gate(issues: list[dict[str, Any]], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    owner = next(
        (item for item in inventory if item.get("owner") == "TimelineSingleOwnerPlayheadInvalidation"),
        {},
    )
    owner_issues = [
        issue
        for issue in issues
        if str(issue.get("owner") or "") == "TimelineSingleOwnerPlayheadInvalidation"
    ]
    protected = bool(owner) and not owner_issues and str(owner.get("backend") or "") == "qwidget-2d-full-canvas-repaint"
    return {
        "candidate": "playhead_only_dirty_rect_repaint",
        "status": "hold_full_canvas_repaint" if protected else "blocked_audit_failed",
        "protected_by": "TimelineSingleOwnerPlayheadInvalidation",
        "current_backend": str(owner.get("backend") or ""),
        "runtime_change_allowed": False,
        "required_before_experiment": [
            "fresh_macau_visual_smoke_no_residue",
            "focused_playhead_shadow_playhead_repaint_tests",
            "owner_approval_before_default_change",
        ],
        "reason": (
            "single_owner_2d_full_canvas_repaint_protects_against_timeline_residue"
            if protected
            else "single_owner_2d_full_canvas_repaint_guard_failed"
        ),
    }


def audit_editor_rendering_ownership(root: Path | None = None) -> dict[str, Any]:
    root = root or ROOT
    issues: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    for rule in TEXT_RULES:
        rel_path = str(rule["path"])
        path = root / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        inventory.append(
            {
                "path": rel_path,
                "owner": str(rule["owner"]),
                "backend": str(
                    rule.get(
                        "backend",
                        "qwidget-2d" if "timeline" in rel_path or "gpu_rendering" in rel_path else "opaque-qwidget",
                    )
                ),
            }
        )
        if not text:
            issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_file"})
            continue
        for pattern in rule.get("required", ()):
            if str(pattern) not in text:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_required", "pattern": str(pattern)})
        for spec in rule.get("required_count", ()):
            pattern = str(spec["pattern"])
            minimum = int(spec.get("min", 1))
            actual = text.count(pattern)
            if actual < minimum:
                issues.append(
                    {
                        "path": rel_path,
                        "owner": rule["owner"],
                        "reason": "insufficient_required_count",
                        "pattern": pattern,
                        "expected_min": minimum,
                        "actual": actual,
                    }
                )
        for pattern in rule.get("forbidden", ()):
            if str(pattern) in text:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "forbidden_pattern", "pattern": str(pattern)})
    for rule in ORDER_RULES:
        rel_path = str(rule["path"])
        path = root / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        inventory.append(
            {
                "path": rel_path,
                "owner": str(rule["owner"]),
                "backend": str(rule.get("backend", "qwidget-2d-painter-owner")),
            }
        )
        if not text:
            issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_file"})
            continue
        cursor = -1
        for pattern in rule.get("ordered", ()):
            index = text.find(str(pattern), cursor + 1)
            if index < 0:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_ordered", "pattern": str(pattern)})
                continue
            if index <= cursor:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "order_regression", "pattern": str(pattern)})
            cursor = max(cursor, index)
    playhead_gate = _playhead_dirty_rect_gate(issues, inventory)
    return {
        "ok": not issues,
        "schema": "ai_subtitle_studio.editor_rendering_ownership_audit.v1",
        "inventory": inventory,
        "issues": issues,
        "playhead_dirty_rect_candidate": playhead_gate,
    }


def render_markdown(report: dict[str, Any]) -> str:
    gate = dict(report.get("playhead_dirty_rect_candidate") or {})
    lines = [
        "# Editor Rendering Ownership Audit",
        "",
        f"- Schema: `{report.get('schema', '')}`",
        f"- OK: `{bool(report.get('ok', False))}`",
        f"- Inventory count: `{len(list(report.get('inventory') or []))}`",
        f"- Issue count: `{len(list(report.get('issues') or []))}`",
        "",
        "## Playhead Dirty-Rect Candidate Gate",
        "",
        f"- Candidate: `{gate.get('candidate', '')}`",
        f"- Status: `{gate.get('status', '')}`",
        f"- Runtime change allowed: `{bool(gate.get('runtime_change_allowed', False))}`",
        f"- Protected by: `{gate.get('protected_by', '')}`",
        f"- Current backend: `{gate.get('current_backend', '')}`",
        f"- Reason: `{gate.get('reason', '')}`",
        "",
        "## Required Before Experiment",
        "",
    ]
    for item in list(gate.get("required_before_experiment") or []):
        lines.append(f"- `{item}`")
    lines.extend(["", "## Issues", ""])
    issues = list(report.get("issues") or [])
    if not issues:
        lines.append("- none")
    for issue in issues:
        lines.append(
            f"- `{issue.get('path', '')}` owner=`{issue.get('owner', '')}` reason=`{issue.get('reason', '')}` pattern=`{issue.get('pattern', '')}`"
        )
    lines.extend(["", "## Inventory", ""])
    for item in list(report.get("inventory") or []):
        lines.append(f"- `{item.get('owner', '')}`: `{item.get('backend', '')}` in `{item.get('path', '')}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit editor/timeline rendering ownership defaults.")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--output-dir", default="", help="write audit JSON and Markdown to this directory")
    args = parser.parse_args(argv)
    report = audit_editor_rendering_ownership(ROOT)
    output_dir = Path(str(args.output_dir or "")).expanduser() if args.output_dir else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "editor_rendering_ownership_audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_dir / "editor_rendering_ownership_audit.md").write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_dir is not None:
        print(output_dir / "editor_rendering_ownership_audit.md")
    else:
        print("OK" if report["ok"] else "FAIL")
        for issue in report["issues"]:
            print(f"- {issue['path']}: {issue['reason']} {issue.get('pattern', '')}".rstrip())
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
