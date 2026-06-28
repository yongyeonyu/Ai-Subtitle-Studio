#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.preview_frame_cache import (  # noqa: E402
    PREVIEW_FRAME_CACHE_PURPOSE,
    PREVIEW_FRAME_CACHE_SCHEMA,
    PREVIEW_FRAME_PROXY_REUSE_POLICY,
    PREVIEW_FRAME_RELINK_REUSE_POLICY,
    nearest_cached_preview_frame,
    preview_frame_cache_path,
    preview_frame_media_identity,
    read_preview_frame_manifest,
    write_preview_frame_manifest,
)


SCHEMA = "ai_subtitle_studio.nle_relink_preview_cache_contract.v1"
AUDIT_ID = "nle_relink_preview_cache_contract_20260628"
BLOCKED_SCOPE = (
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "proxy_transcode_cache_reuse_without_source_identity_not_allowed",
    "preview_cache_deletion_or_move_not_allowed",
    "ui_layout_or_label_changes_not_allowed",
)


def build_nle_relink_preview_cache_report(*, output_dir: Path) -> dict[str, Any]:
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "nas_original.mp4"
    relinked = work_dir / "nas_relinked_copy.mp4"
    proxy = work_dir / "nas_preview_proxy.mp4"
    source.write_bytes(b"same-nas-media" * 512)
    relinked.write_bytes(source.read_bytes())
    proxy.write_bytes(b"proxy-transcode-different-bytes" * 512)
    fps = 30.0
    width = 320
    cached_path = preview_frame_cache_path(str(source), 1.0, width=width, root=work_dir)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"jpg")
    write_preview_frame_manifest(cached_path, str(source), 1.0, fps=fps, width=width)

    relink_hit = nearest_cached_preview_frame(str(relinked), 1.03, fps=fps, width=width, tolerance_frames=2, root=work_dir)
    proxy_hit = nearest_cached_preview_frame(str(proxy), 1.03, fps=fps, width=width, tolerance_frames=2, root=work_dir)
    source_identity = preview_frame_media_identity(str(source))
    relink_identity = preview_frame_media_identity(str(relinked))
    proxy_identity = preview_frame_media_identity(str(proxy))
    manifest = read_preview_frame_manifest(cached_path)
    cached_still_exists = cached_path.exists() and cached_path.stat().st_size > 0
    relink_identity_matches = (
        source_identity.get("source_media_identity_digest") == relink_identity.get("source_media_identity_digest")
        and source_identity.get("source_path_sha1") != relink_identity.get("source_path_sha1")
    )
    proxy_identity_blocked = source_identity.get("source_media_identity_digest") != proxy_identity.get(
        "source_media_identity_digest"
    )
    ready = (
        str(relink_hit) == str(cached_path)
        and proxy_hit == ""
        and relink_identity_matches
        and proxy_identity_blocked
        and cached_still_exists
        and manifest.get("schema") == PREVIEW_FRAME_CACHE_SCHEMA
        and manifest.get("purpose") == PREVIEW_FRAME_CACHE_PURPOSE
        and manifest.get("relink_reuse_policy") == PREVIEW_FRAME_RELINK_REUSE_POLICY
        and manifest.get("proxy_switch_reuse_policy") == PREVIEW_FRAME_PROXY_REUSE_POLICY
        and manifest.get("source_media_identity_policy") == "path_independent_size_head_tail_sample_v1"
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": ready,
        "runtime_contract_applied": True,
        "ui_layout_change_applied": False,
        "persisted_project_schema_change_applied": False,
        "source_path": str(source),
        "relinked_path": str(relinked),
        "proxy_path": str(proxy),
        "cached_path": str(cached_path),
        "cached_still_exists": cached_still_exists,
        "relink_identity_matches": relink_identity_matches,
        "relink_hit_path": str(relink_hit),
        "relink_hit_reuses_original_cache": str(relink_hit) == str(cached_path),
        "proxy_identity_blocked": proxy_identity_blocked,
        "proxy_hit_path": str(proxy_hit),
        "proxy_hit_blocked": proxy_hit == "",
        "manifest_schema": manifest.get("schema"),
        "manifest_purpose": manifest.get("purpose"),
        "manifest_relink_reuse_policy": manifest.get("relink_reuse_policy"),
        "manifest_proxy_switch_reuse_policy": manifest.get("proxy_switch_reuse_policy"),
        "manifest_source_media_identity_policy": manifest.get("source_media_identity_policy"),
        "blocked_scope": list(BLOCKED_SCOPE),
    }


def write_nle_relink_preview_cache_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_relink_preview_cache_contract.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Relink Preview Cache Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime contract applied: `{report['runtime_contract_applied']}`",
        f"- UI layout change applied: `{report['ui_layout_change_applied']}`",
        f"- Persisted project schema change applied: `{report['persisted_project_schema_change_applied']}`",
        f"- Relink identity matches: `{report['relink_identity_matches']}`",
        f"- Relink hit reuses original cache: `{report['relink_hit_reuses_original_cache']}`",
        f"- Proxy identity blocked: `{report['proxy_identity_blocked']}`",
        f"- Proxy hit blocked: `{report['proxy_hit_blocked']}`",
        f"- Cached still exists: `{report['cached_still_exists']}`",
        f"- Manifest relink reuse policy: `{report['manifest_relink_reuse_policy']}`",
        f"- Manifest proxy switch reuse policy: `{report['manifest_proxy_switch_reuse_policy']}`",
        "",
        "## Blocked Scope",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["blocked_scope"])
    (output_dir / "nle_relink_preview_cache_contract.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NLE relink/proxy preview-cache contract.")
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_relink_preview_cache_contract_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_relink_preview_cache_report(output_dir=output_dir)
    write_nle_relink_preview_cache_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
