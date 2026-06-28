#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "ai_subtitle_studio.nle_viewport_zoom_decoupling.v1"
FORBIDDEN_CALLS = {
    "apply_candidate_confirm_dual_write_pilot",
    "apply_caption_delete_dual_write_pilot",
    "apply_caption_merge_dual_write_pilot",
    "apply_caption_move_commit_dual_write_pilot",
    "apply_caption_move_dual_write_pilot",
    "apply_caption_range_replace_dual_write_pilot",
    "apply_caption_resize_dual_write_pilot",
    "apply_caption_split_dual_write_pilot",
    "apply_caption_text_edit_dual_write_pilot",
    "apply_gap_delete_dual_write_pilot",
    "apply_gap_generate_dual_write_pilot",
    "record_nle_operation_journal_entry",
    "save_project",
    "write_project_file",
    "update_segments",
    "_finalize_edit",
    "_mark_dirty",
    "_on_seg_time_changed",
}
FORBIDDEN_ASSIGN_ATTRS = {
    "_last_nle_timeline_operation",
    "_nle_project_state",
    "gap_segments",
    "segments",
    "vad_segments",
    "voice_activity_segments",
}
REQUIRED_VIEW_TOKENS = {
    "ui/timeline/timeline_widget.py": {
        "TimelineWidget.wheelEvent": ("def wheelEvent", "_apply_zoom", "apply_manual_horizontal_scroll_delta"),
        "TimelineWidget._apply_zoom": ("def _apply_zoom", "self.canvas.pps", "sb.setValue", "_schedule_vp_sync"),
    },
    "ui/timeline/timeline_global.py": {
        "GlobalCanvas.wheelEvent": ("def wheelEvent", "apply_manual_horizontal_scroll_delta", "ev.accept"),
    },
    "ui/timeline/timeline_canvas.py": {
        "TimelineCanvas.set_zoom": ("def set_zoom", "self.pps", "_update_viewport_region"),
    },
}


def _dotted_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _find_class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                return child
    return None


def _method_contract(path: Path, class_name: str, method_name: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    method = _find_class_method(tree, class_name, method_name)
    forbidden_calls: list[str] = []
    forbidden_assignments: list[str] = []
    if method is not None:
        for node in ast.walk(method):
            if isinstance(node, ast.Call):
                name = _dotted_call_name(node.func)
                short = name.rsplit(".", 1)[-1]
                if short in FORBIDDEN_CALLS:
                    forbidden_calls.append(name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    forbidden_assignments.extend(_forbidden_assignment_names(target))
            elif isinstance(node, ast.AnnAssign):
                forbidden_assignments.extend(_forbidden_assignment_names(node.target))
            elif isinstance(node, ast.AugAssign):
                forbidden_assignments.extend(_forbidden_assignment_names(node.target))
    source = ast.get_source_segment(text, method) if method is not None else ""
    return {
        "owner": f"{class_name}.{method_name}",
        "file": str(path.relative_to(ROOT)),
        "method_present": method is not None,
        "forbidden_calls": sorted(set(forbidden_calls)),
        "forbidden_assignments": sorted(set(forbidden_assignments)),
        "forbidden_call_count": len(set(forbidden_calls)),
        "forbidden_assignment_count": len(set(forbidden_assignments)),
        "source": source or "",
    }


def _forbidden_assignment_names(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_ASSIGN_ATTRS:
        names.append(_dotted_call_name(target))
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            names.extend(_forbidden_assignment_names(item))
    return names


def _token_contract() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel_path, owners in REQUIRED_VIEW_TOKENS.items():
        text = (ROOT / rel_path).read_text(encoding="utf-8")
        for owner, tokens in owners.items():
            rows.append(
                {
                    "owner": owner,
                    "file": rel_path,
                    "required_tokens": list(tokens),
                    "present_tokens": [token for token in tokens if token in text],
                    "all_tokens_present": all(token in text for token in tokens),
                }
            )
    return rows


def build_nle_viewport_zoom_decoupling_report() -> dict[str, Any]:
    method_rows = [
        _method_contract(ROOT / "ui" / "timeline" / "timeline_widget.py", "TimelineWidget", "wheelEvent"),
        _method_contract(ROOT / "ui" / "timeline" / "timeline_widget.py", "TimelineWidget", "_apply_zoom"),
        _method_contract(ROOT / "ui" / "timeline" / "timeline_global.py", "GlobalCanvas", "wheelEvent"),
        _method_contract(ROOT / "ui" / "timeline" / "timeline_canvas.py", "TimelineCanvas", "set_zoom"),
    ]
    token_rows = _token_contract()
    ready = (
        all(row["method_present"] for row in method_rows)
        and all(row["forbidden_call_count"] == 0 for row in method_rows)
        and all(row["forbidden_assignment_count"] == 0 for row in method_rows)
        and all(row["all_tokens_present"] for row in token_rows)
    )
    return {
        "schema": SCHEMA,
        "audit_id": "nle_viewport_zoom_decoupling_20260628",
        "ready": ready,
        "runtime_change_applied": False,
        "viewport_only_contract": True,
        "model_write_allowed": False,
        "nle_write_allowed": False,
        "method_contracts": [
            {key: value for key, value in row.items() if key != "source"}
            for row in method_rows
        ],
        "token_contracts": token_rows,
        "blocked_scope": [
            "timeline_wheel_zoom_must_not_write_primary_subtitle_model",
            "timeline_wheel_zoom_must_not_append_nle_operation_journal",
            "timeline_wheel_zoom_must_not_save_project",
            "timeline_wheel_zoom_must_not_change_ui_layout_labels_menus",
            "timeline_wheel_zoom_must_not_enable_qml_or_gpu_default_surface",
        ],
    }


def write_nle_viewport_zoom_decoupling_report(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "nle_viewport_zoom_decoupling.json"
    markdown_path = output_dir / "nle_viewport_zoom_decoupling.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# NLE Viewport Zoom Decoupling Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- Viewport-only contract: `{report['viewport_only_contract']}`",
        f"- Model write allowed: `{report['model_write_allowed']}`",
        f"- NLE write allowed: `{report['nle_write_allowed']}`",
        "",
        "## Method Contracts",
        "",
        "| owner | file | present | forbidden_calls | forbidden_assignments |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["method_contracts"]:
        lines.append(
            "| {owner} | {file} | {present} | {calls} | {assigns} |".format(
                owner=row["owner"],
                file=row["file"],
                present=row["method_present"],
                calls=row["forbidden_call_count"],
                assigns=row["forbidden_assignment_count"],
            )
        )
    lines.extend(
        [
            "",
            "## View Tokens",
            "",
            "| owner | all_tokens_present | required_tokens |",
            "| --- | --- | --- |",
        ]
    )
    for row in report["token_contracts"]:
        lines.append(
            "| {owner} | {present} | {tokens} |".format(
                owner=row["owner"],
                present=row["all_tokens_present"],
                tokens=", ".join(f"`{token}`" for token in row["required_tokens"]),
            )
        )
    lines.extend(["", "## Blocked Scope", ""])
    lines.extend(f"- `{item}`" for item in report["blocked_scope"])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "manual_verification" / "latest" / "nle_viewport_zoom_decoupling_20260628")
    args = parser.parse_args(argv)
    report = build_nle_viewport_zoom_decoupling_report()
    write_nle_viewport_zoom_decoupling_report(args.output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
