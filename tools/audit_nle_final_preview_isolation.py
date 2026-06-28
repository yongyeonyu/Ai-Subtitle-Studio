#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.engine.subtitle_live_editor_feed import build_subtitle_live_editor_feed
from core.project.nle_runtime_cutover import (
    nle_final_overlay_segments_from_editor_rows,
    nle_global_canvas_segments_from_editor_rows,
)
from ui.editor.editor_segments_timeline_context import EditorSegmentsTimelineContextMixin


class _VideoOverlayProbe(EditorSegmentsTimelineContextMixin):
    def __init__(self) -> None:
        self.video_fps = 30.0
        self.video_player = SimpleNamespace(total_time=4.0)
        self.timeline = SimpleNamespace(canvas=SimpleNamespace(_multiclip_boxes=[], playhead_sec=1.0))
        self._subtitle_memory_cache: dict[str, Any] = {}
        self._cached_segs = [
            {"id": "caption_1", "start": 0.0, "end": 2.0, "text": "final", "line": 0}
        ]
        self._live_stt_preview_segments = [
            {
                "id": "stt_1",
                "start": 0.5,
                "end": 1.5,
                "text": "stt",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT1",
            }
        ]
        self._live_editor_preview_segments = [
            {"id": "draft_1", "start": 0.5, "end": 1.5, "text": "draft", "_live_subtitle_preview": True}
        ]

    def _get_current_segments(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._cached_segs]

    def _subtitle_context_center_sec(self) -> float:
        return 1.0

    def _subtitle_context_window_seconds(self) -> tuple[float, float, int]:
        return 75.0, 105.0, 480

    def _subtitle_memory_segments(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._cached_segs]

    def _subtitle_memory_visible_window(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._cached_segs]

    def _subtitle_context_window_from_segments(
        self,
        rows: list[dict[str, Any]],
        *,
        center_sec: float | None = None,
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]


def _has_preview_marker(row: dict[str, Any]) -> bool:
    return bool(
        row.get("stt_pending")
        or row.get("_live_stt_preview")
        or row.get("_live_subtitle_preview")
        or str(row.get("stt_preview_source") or "").strip()
    )


def _texts(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("text", "") or "") for row in rows]


def _check(name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": dict(detail or {})}


def build_report() -> dict[str, Any]:
    confirmed = [{"id": "caption_1", "start": 0.0, "end": 2.0, "text": "final"}]
    stt_preview = [
        {
            "id": "stt_1",
            "start": 0.5,
            "end": 1.5,
            "text": "stt",
            "stt_pending": True,
            "_live_stt_preview": True,
            "stt_preview_source": "STT1",
        }
    ]
    subtitle_preview = [
        {"id": "draft_1", "start": 0.5, "end": 1.5, "text": "draft", "_live_subtitle_preview": True}
    ]
    feed = build_subtitle_live_editor_feed(
        confirmed_segments=confirmed,
        stt_preview_segments=stt_preview,
        subtitle_preview_segments=subtitle_preview,
        total_duration_floor=4.0,
    )
    payload = feed.to_dict()
    combined_rows = [dict(row) for row in payload["combined_segments"]]
    final_rows = [dict(row) for row in payload["final_surface_segments"]]
    preview_rows = [dict(row) for row in payload["preview_lane_segments"]]
    overlay_rows = nle_final_overlay_segments_from_editor_rows(combined_rows, primary_fps=30.0, center_sec=1.0)
    global_rows = nle_global_canvas_segments_from_editor_rows(combined_rows, primary_fps=30.0)
    probe = _VideoOverlayProbe()
    live_context = probe._video_subtitle_live_preview_context(center_sec=1.0)
    video_context = probe._video_subtitle_context_for_player()

    checks = [
        _check(
            "feed_final_surface_confirmed_only",
            _texts(final_rows) == ["final"] and not any(_has_preview_marker(row) for row in final_rows),
            {"final_surface_texts": _texts(final_rows)},
        ),
        _check(
            "feed_preview_lane_keeps_candidates",
            sorted(_texts(preview_rows)) == ["draft", "stt"] and all(_has_preview_marker(row) for row in preview_rows),
            {"preview_lane_texts": _texts(preview_rows)},
        ),
        _check(
            "feed_combined_is_diagnostic_only",
            payload["surface_contract"]["combined_segments"] == "diagnostic_candidate_lane_only_not_final_overlay_or_save",
            {"combined_texts": _texts(combined_rows), "surface_contract": payload["surface_contract"]},
        ),
        _check(
            "final_overlay_filters_preview_rows",
            _texts(overlay_rows) == ["final"] and not any(_has_preview_marker(row) for row in overlay_rows),
            {"overlay_texts": _texts(overlay_rows)},
        ),
        _check(
            "global_canvas_filters_preview_rows",
            _texts(global_rows) == ["final"] and not any(_has_preview_marker(row) for row in global_rows),
            {"global_texts": _texts(global_rows)},
        ),
        _check(
            "video_overlay_ignores_live_preview_context",
            live_context is None and _texts(video_context) == ["final"] and not any(_has_preview_marker(row) for row in video_context),
            {"live_context": live_context, "video_context_texts": _texts(video_context)},
        ),
    ]
    return {
        "schema": "ai_subtitle_studio.audit_nle_final_preview_isolation.v1",
        "ready": all(item["passed"] for item in checks),
        "runtime_change_applied": True,
        "surface_policy": {
            "timeline_canvas": "final_rows_plus_explicit_preview_lanes",
            "final_overlay": "confirmed_final_rows_only",
            "global_canvas": "confirmed_final_rows_only",
            "save_export": "confirmed_final_rows_only",
            "combined_feed": "diagnostic_candidate_lane_only",
        },
        "counts": payload["counts"],
        "checks": checks,
        "defer": [
            "persisted_nle_fields",
            "per_pixel_writes",
            "ui_layout_redesign",
            "stt_default_or_cache_promotion",
            "app_store_packaging",
        ],
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "nle_final_preview_isolation.json"
    md_path = output_dir / "nle_final_preview_isolation.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# NLE Final/Preview Isolation Audit",
        "",
        f"- ready: `{str(report['ready']).lower()}`",
        f"- runtime_change_applied: `{str(report['runtime_change_applied']).lower()}`",
        f"- combined_feed: `{report['surface_policy']['combined_feed']}`",
        f"- final_overlay: `{report['surface_policy']['final_overlay']}`",
        f"- global_canvas: `{report['surface_policy']['global_canvas']}`",
        "",
        "## Checks",
    ]
    for item in report["checks"]:
        lines.append(f"- `{item['name']}`: `{str(item['passed']).lower()}`")
    lines.extend([
        "",
        "## Defer",
    ])
    for item in report["defer"]:
        lines.append(f"- `{item}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_final_preview_isolation_20260628",
        help="Directory for JSON/Markdown audit output.",
    )
    args = parser.parse_args()
    report = build_report()
    write_report(report, Path(args.output_dir))
    print(json.dumps({"ready": report["ready"], "output_dir": args.output_dir}, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
