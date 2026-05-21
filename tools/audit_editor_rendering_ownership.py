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
        "required": ("def should_paint_subtitle_segment_text(", "if native_inline_active:", "return False"),
        "forbidden": ("QOpenGLWidget", "QQuickWidget", "make_accelerated_viewport"),
    },
    {
        "path": "ui/editor/ux/timeline_inline_text_editor.py",
        "owner": "TimelineInlineTextEdit",
        "required": (
            'self.setObjectName("timelineInlineTextEdit")',
            'self.setProperty("timelineInlineEditorRole", "segment-inline-locked")',
            "WA_TranslucentBackground, False",
            "WA_OpaquePaintEvent",
        ),
        "forbidden": ("QOpenGLWidget", "QQuickWidget"),
    },
    {
        "path": "ui/gpu_rendering.py",
        "owner": "GpuRenderingGate",
        "required": (
            "explicit diagnostics only",
            "editor_rendering_scenegraph_opt_in_enabled",
            "return False",
        ),
        "forbidden": ("return not gpu_widgets_enabled(feature_key)",),
    },
)


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
                "backend": "qwidget-2d" if "timeline" in rel_path or "gpu_rendering" in rel_path else "opaque-qwidget",
            }
        )
        if not text:
            issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_file"})
            continue
        for pattern in rule.get("required", ()):
            if str(pattern) not in text:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "missing_required", "pattern": str(pattern)})
        for pattern in rule.get("forbidden", ()):
            if str(pattern) in text:
                issues.append({"path": rel_path, "owner": rule["owner"], "reason": "forbidden_pattern", "pattern": str(pattern)})
    return {
        "ok": not issues,
        "schema": "ai_subtitle_studio.editor_rendering_ownership_audit.v1",
        "inventory": inventory,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit editor/timeline rendering ownership defaults.")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)
    report = audit_editor_rendering_ownership(ROOT)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("OK" if report["ok"] else "FAIL")
        for issue in report["issues"]:
            print(f"- {issue['path']}: {issue['reason']} {issue.get('pattern', '')}".rstrip())
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
