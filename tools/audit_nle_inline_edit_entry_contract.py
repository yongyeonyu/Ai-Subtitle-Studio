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


SCHEMA = "ai_subtitle_studio.nle_inline_edit_entry_contract.v1"
AUDIT_ID = "nle_inline_edit_entry_contract_20260628"
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
    "validate_segments",
    "validate_srt_duration",
    "_finalize_edit",
    "_mark_dirty",
    "_on_seg_time_changed",
    "update_segments",
}
FORBIDDEN_TRACE_KEYS = {
    "text",
    "old_text",
    "new_text",
    "target_ids",
    "source_project_path",
}
REQUIRED_TOKENS = {
    "TimelineInlineEditMixin.start_inline_edit": (
        "self._trace_inline_edit_entry(",
        "self.sig_editing_mode.emit(True)",
        "editor.setFocus(",
    ),
    "TimelineInlineEditMixin._trace_inline_edit_entry": (
        "current_app_trace_logger()",
        'logger.log_event(\n                "timeline_inline_edit_entry"',
        'stage="ui-ux"',
        'event_type="inline_edit_entry"',
        'action="inline_edit_entry"',
        'commit_boundary="none"',
        'commit_source="timeline_inline_edit_entry"',
        "nle_write_allowed=False",
        "normal_caption_row_rewrite_allowed=False",
        "placeholder_clear_applied=bool(placeholder_clear)",
        "caption_payload_included=False",
    ),
    "TimelineInputMixin.mouseDoubleClickEvent": (
        "self.seg_double_clicked.emit",
        "if self._edit_active:",
    ),
}


def _dotted_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _find_class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == method_name:
                return child
    return None


def _method_contract(path: Path, class_name: str, method_name: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    method = _find_class_method(tree, class_name, method_name)
    forbidden_calls: list[str] = []
    if method is not None:
        for node in ast.walk(method):
            if isinstance(node, ast.Call):
                name = _dotted_call_name(node.func)
                short = name.rsplit(".", 1)[-1]
                if short in FORBIDDEN_CALLS:
                    forbidden_calls.append(name)
    return {
        "owner": f"{class_name}.{method_name}",
        "file": str(path.relative_to(ROOT)),
        "method_present": method is not None,
        "forbidden_calls": sorted(set(forbidden_calls)),
        "forbidden_call_count": len(set(forbidden_calls)),
    }


def _trace_payload_contract() -> dict[str, Any]:
    path = ROOT / "ui" / "editor" / "ux" / "timeline_canvas_editing.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    method = _find_class_method(tree, "TimelineInlineEditMixin", "_trace_inline_edit_entry")
    literal_keys: set[str] = set()
    if method is not None:
        for node in ast.walk(method):
            if isinstance(node, ast.keyword) and node.arg:
                literal_keys.add(str(node.arg))
    forbidden_present = sorted(literal_keys & FORBIDDEN_TRACE_KEYS)
    return {
        "owner": "TimelineInlineEditMixin._trace_inline_edit_entry",
        "file": str(path.relative_to(ROOT)),
        "trace_method_present": method is not None,
        "forbidden_payload_keys": forbidden_present,
        "forbidden_payload_key_count": len(forbidden_present),
        "caption_payload_included": "caption_payload_included" in literal_keys,
    }


def _token_contract() -> list[dict[str, Any]]:
    files = {
        "TimelineInlineEditMixin.start_inline_edit": ROOT / "ui" / "editor" / "ux" / "timeline_canvas_editing.py",
        "TimelineInlineEditMixin._trace_inline_edit_entry": ROOT / "ui" / "editor" / "ux" / "timeline_canvas_editing.py",
        "TimelineInputMixin.mouseDoubleClickEvent": ROOT / "ui" / "editor" / "ux" / "timeline_input.py",
    }
    rows: list[dict[str, Any]] = []
    for owner, tokens in REQUIRED_TOKENS.items():
        text = files[owner].read_text(encoding="utf-8")
        rows.append(
            {
                "owner": owner,
                "file": str(files[owner].relative_to(ROOT)),
                "required_tokens": list(tokens),
                "present_tokens": [token for token in tokens if token in text],
                "all_tokens_present": all(token in text for token in tokens),
            }
        )
    return rows


def build_nle_inline_edit_entry_contract_report() -> dict[str, Any]:
    method_rows = [
        _method_contract(
            ROOT / "ui" / "editor" / "ux" / "timeline_canvas_editing.py",
            "TimelineInlineEditMixin",
            "start_inline_edit",
        ),
        _method_contract(
            ROOT / "ui" / "editor" / "ux" / "timeline_canvas_editing.py",
            "TimelineInlineEditMixin",
            "_trace_inline_edit_entry",
        ),
    ]
    trace_contract = _trace_payload_contract()
    token_rows = _token_contract()
    ready = (
        all(row["method_present"] for row in method_rows)
        and all(row["forbidden_call_count"] == 0 for row in method_rows)
        and trace_contract["trace_method_present"]
        and trace_contract["forbidden_payload_key_count"] == 0
        and trace_contract["caption_payload_included"] is True
        and all(row["all_tokens_present"] for row in token_rows)
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": ready,
        "taption_contract": "inline_edit_entry_preview_only_until_text_commit",
        "entry_trace_enabled": True,
        "nle_write_allowed_on_entry": False,
        "normal_caption_row_rewrite_allowed_on_entry": False,
        "project_save_allowed_on_entry": False,
        "row_validation_allowed_on_entry": False,
        "caption_text_payload_allowed": False,
        "nas_validation_required": False,
        "method_contracts": method_rows,
        "trace_payload_contract": trace_contract,
        "token_contracts": token_rows,
        "blocked_scope": [
            "double_click_inline_edit_entry_must_not_append_nle_operation_journal",
            "double_click_inline_edit_entry_must_not_save_project",
            "double_click_inline_edit_entry_must_not_validate_or_rewrite_primary_subtitle_model",
            "inline_edit_entry_trace_must_not_include_caption_text_or_target_ids",
            "actual_text_change_commit_remains_caption_text_edit_release_commit",
        ],
    }


def write_nle_inline_edit_entry_contract_report(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "nle_inline_edit_entry_contract.json"
    markdown_path = output_dir / "nle_inline_edit_entry_contract.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# NLE Inline Edit Entry Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Taption contract: `{report['taption_contract']}`",
        f"- Entry trace enabled: `{report['entry_trace_enabled']}`",
        f"- NLE write allowed on entry: `{report['nle_write_allowed_on_entry']}`",
        f"- Normal caption row rewrite allowed on entry: `{report['normal_caption_row_rewrite_allowed_on_entry']}`",
        f"- Project save allowed on entry: `{report['project_save_allowed_on_entry']}`",
        f"- Row validation allowed on entry: `{report['row_validation_allowed_on_entry']}`",
        f"- Caption text payload allowed: `{report['caption_text_payload_allowed']}`",
        f"- NAS validation required: `{report['nas_validation_required']}`",
        "",
        "## Method Contracts",
        "",
        "| owner | file | present | forbidden_calls |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["method_contracts"]:
        lines.append(
            "| {owner} | {file} | {present} | {calls} |".format(
                owner=row["owner"],
                file=row["file"],
                present=row["method_present"],
                calls=row["forbidden_call_count"],
            )
        )
    trace = report["trace_payload_contract"]
    lines.extend(
        [
            "",
            "## Trace Payload Contract",
            "",
            f"- Owner: `{trace['owner']}`",
            f"- Forbidden payload key count: `{trace['forbidden_payload_key_count']}`",
            f"- Caption payload included flag present: `{trace['caption_payload_included']}`",
            "",
            "## Required Tokens",
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
    parser = argparse.ArgumentParser(description="Audit Taption-style inline edit entry NLE contract.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_inline_edit_entry_contract_20260628")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    report = build_nle_inline_edit_entry_contract_report()
    write_nle_inline_edit_entry_contract_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
