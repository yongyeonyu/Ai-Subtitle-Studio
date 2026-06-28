from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.personalization.ground_truth_import import build_truth_table_records_from_srt
from core.personalization.lora_models import stable_hash


NAS_TRUTH_LEARNING_SCHEMA = "ai_subtitle_studio.nas_50_truth_learning_manifest.v1"
DEFAULT_NAS_BENCHMARK_PLAN_PATH = Path("docs/quality_validation/NAS_SUBTITLE_BENCHMARK_50_PLAN.md")
CALIBRATION_ITEM_NUMBERS = {48, 50}
VALIDATION_ITEM_NUMBERS = {6, 14, 22, 33, 42}
HOLDOUT_ITEM_NUMBERS = {3, 18, 27, 38, 46}

_NAS_ROOT_RE = re.compile(r"^대상 NAS 루트:\s*`(?P<root>[^`]+)`\s*$")
_APP_VERSION_RE = re.compile(r"^앱 버전 기준:\s*`(?P<version>[^`]+)`\s*$")
_ACTION_ITEM_RE = re.compile(
    r"^-\s*\[[ xX]?\]\s*"
    r"(?P<index>\d+)\.\s*"
    r"`(?P<title>[^`]+)`\s*\|\s*"
    r"folder:\s*`(?P<folder>[^`]+)`\s*\|\s*"
    r"video:\s*`(?P<video>[^`]+)`\s*\|\s*"
    r"truth:\s*`(?P<truth>[^`]+)`\s*$"
)


@dataclass(frozen=True)
class NasTruthManifestItem:
    action_item: int
    title: str
    folder: str
    video: str
    truth: str
    media_path: str
    subtitle_path: str
    media_id: str
    pair_basis: str
    dataset_split: str
    fixture_role: str
    media_exists: bool
    subtitle_exists: bool

    def to_record(self) -> dict[str, Any]:
        missing_reasons: list[str] = []
        if not self.media_exists:
            missing_reasons.append("missing_media")
        if not self.subtitle_exists:
            missing_reasons.append("missing_subtitle")
        return {
            "action_item": self.action_item,
            "title": self.title,
            "folder": self.folder,
            "video": self.video,
            "truth": self.truth,
            "media_path": self.media_path,
            "subtitle_path": self.subtitle_path,
            "media_id": self.media_id,
            "pair_basis": self.pair_basis,
            "dataset_split": self.dataset_split,
            "fixture_role": self.fixture_role,
            "exists": {
                "media": self.media_exists,
                "subtitle": self.subtitle_exists,
            },
            "missing_reasons": missing_reasons,
        }


def _dataset_split_for_item(action_item: int) -> str:
    if action_item in VALIDATION_ITEM_NUMBERS:
        return "validation"
    if action_item in HOLDOUT_ITEM_NUMBERS:
        return "holdout"
    return "train"


def _fixture_role_for_item(action_item: int) -> str:
    return "calibration" if action_item in CALIBRATION_ITEM_NUMBERS else "primary"


def _read_plan_text(plan_path: str | Path | None = None) -> tuple[Path, str]:
    target = Path(plan_path or DEFAULT_NAS_BENCHMARK_PLAN_PATH)
    return target, target.read_text(encoding="utf-8")


def parse_nas_truth_plan(plan_path: str | Path | None = None) -> dict[str, Any]:
    resolved_path, text = _read_plan_text(plan_path)
    nas_root = ""
    app_version = ""
    items: list[dict[str, Any]] = []
    in_primary_action_items = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "## 50 Action Items":
            in_primary_action_items = True
            continue
        if in_primary_action_items and line.startswith("## "):
            in_primary_action_items = False
        root_match = _NAS_ROOT_RE.match(line)
        if root_match:
            nas_root = root_match.group("root")
            continue
        version_match = _APP_VERSION_RE.match(line)
        if version_match:
            app_version = version_match.group("version")
            continue
        if not in_primary_action_items:
            continue
        item_match = _ACTION_ITEM_RE.match(line)
        if not item_match:
            continue
        action_item = int(item_match.group("index"))
        items.append(
            {
                "action_item": action_item,
                "title": item_match.group("title"),
                "folder": item_match.group("folder"),
                "video": item_match.group("video"),
                "truth": item_match.group("truth"),
                "dataset_split": _dataset_split_for_item(action_item),
                "fixture_role": _fixture_role_for_item(action_item),
            }
        )

    return {
        "plan_path": str(resolved_path),
        "nas_root": nas_root,
        "app_version": app_version,
        "items": sorted(items, key=lambda item: int(item["action_item"])),
    }


def _media_id_for_item(item: dict[str, Any]) -> str:
    action_item = int(item.get("action_item") or 0)
    digest = stable_hash(
        {
            "action_item": action_item,
            "folder": item.get("folder"),
            "video": item.get("video"),
            "truth": item.get("truth"),
        }
    )[:12]
    return f"nas50-{action_item:02d}-{digest}"


def build_nas_truth_manifest(
    *,
    plan_path: str | Path | None = None,
    nas_root: str | Path | None = None,
    check_files: bool = True,
) -> dict[str, Any]:
    parsed = parse_nas_truth_plan(plan_path)
    root = Path(nas_root or parsed["nas_root"])
    manifest_items: list[dict[str, Any]] = []

    for item in parsed["items"]:
        media_path = root / str(item["folder"]) / str(item["video"])
        subtitle_path = root / str(item["folder"]) / str(item["truth"])
        manifest_items.append(
            NasTruthManifestItem(
                action_item=int(item["action_item"]),
                title=str(item["title"]),
                folder=str(item["folder"]),
                video=str(item["video"]),
                truth=str(item["truth"]),
                media_path=str(media_path),
                subtitle_path=str(subtitle_path),
                media_id=_media_id_for_item(item),
                pair_basis="exact_stem_match",
                dataset_split=str(item["dataset_split"]),
                fixture_role=str(item["fixture_role"]),
                media_exists=media_path.exists() if check_files else False,
                subtitle_exists=subtitle_path.exists() if check_files else False,
            ).to_record()
        )

    split_counts = Counter(str(item["dataset_split"]) for item in manifest_items)
    role_counts = Counter(str(item["fixture_role"]) for item in manifest_items)
    missing_media = sum(1 for item in manifest_items if not item["exists"]["media"])
    missing_subtitles = sum(1 for item in manifest_items if not item["exists"]["subtitle"])

    return {
        "schema": NAS_TRUTH_LEARNING_SCHEMA,
        "plan_path": parsed["plan_path"],
        "nas_root": str(root),
        "app_version": parsed["app_version"],
        "counts": {
            "items_total": len(manifest_items),
            "present_pairs": sum(
                1 for item in manifest_items if item["exists"]["media"] and item["exists"]["subtitle"]
            ),
            "missing_media": missing_media,
            "missing_subtitle": missing_subtitles,
            "dataset_splits": dict(sorted(split_counts.items())),
            "fixture_roles": dict(sorted(role_counts.items())),
        },
        "items": manifest_items,
    }


def build_nas_truth_learning_dry_run(
    *,
    plan_path: str | Path | None = None,
    nas_root: str | Path | None = None,
    include_truth_records: bool = False,
    max_items: int | None = None,
) -> dict[str, Any]:
    manifest = build_nas_truth_manifest(plan_path=plan_path, nas_root=nas_root, check_files=True)
    selected_items = list(manifest["items"])
    if max_items is not None:
        selected_items = selected_items[: max(0, int(max_items))]

    truth_rows = 0
    excluded_rows = 0
    voice_bridge_rows = 0
    multimodal_context_rows = 0
    skipped_empty_text = 0
    skipped_pure_symbols = 0
    analyzed_pairs = 0
    item_summaries: list[dict[str, Any]] = []

    if include_truth_records:
        for item in selected_items:
            if not (item["exists"]["media"] and item["exists"]["subtitle"]):
                continue
            result = build_truth_table_records_from_srt(
                item["media_path"],
                item["subtitle_path"],
                media_id=item["media_id"],
                pair_match_type=item["pair_basis"],
            )
            stats = dict(result.get("stats") or {})
            truth_count = int(stats.get("truth_rows") or 0)
            excluded_count = int(stats.get("excluded_parenthetical_rows") or 0)
            skipped_empty_count = int(stats.get("skipped_empty_text") or 0)
            skipped_symbol_count = int(stats.get("skipped_pure_symbols") or 0)
            truth_rows += truth_count
            excluded_rows += excluded_count
            voice_bridge_rows += len(list(result.get("voice_bridge_rows") or []))
            multimodal_context_rows += len(list(result.get("multimodal_context_rows") or []))
            skipped_empty_text += skipped_empty_count
            skipped_pure_symbols += skipped_symbol_count
            analyzed_pairs += 1
            item_summaries.append(
                {
                    "action_item": item["action_item"],
                    "title": item["title"],
                    "dataset_split": item["dataset_split"],
                    "fixture_role": item["fixture_role"],
                    "truth_rows": truth_count,
                    "excluded_parenthetical_rows": excluded_count,
                    "skipped_empty_text": skipped_empty_count,
                    "skipped_pure_symbols": skipped_symbol_count,
                    "split_analysis_effective_rows": truth_count + skipped_symbol_count,
                    "classification": result.get("classification") or {},
                    "subtitle_profile": result.get("subtitle_profile") or {},
                }
            )

    summary = {
        "items_total": int(manifest["counts"]["items_total"]),
        "selected_items": len(selected_items),
        "present_pairs": int(manifest["counts"]["present_pairs"]),
        "missing_media": int(manifest["counts"]["missing_media"]),
        "missing_subtitle": int(manifest["counts"]["missing_subtitle"]),
        "analyzed_pairs": analyzed_pairs,
        "truth_rows": truth_rows,
        "excluded_parenthetical_rows": excluded_rows,
        "voice_bridge_rows": voice_bridge_rows,
        "multimodal_context_rows": multimodal_context_rows,
        "skipped_empty_text": skipped_empty_text,
        "skipped_pure_symbols": skipped_pure_symbols,
        "skipped_rows": skipped_empty_text + skipped_pure_symbols,
        "importable_truth_rows": truth_rows,
        "split_analysis_effective_rows": truth_rows + skipped_pure_symbols,
        "dataset_splits": manifest["counts"]["dataset_splits"],
        "fixture_roles": manifest["counts"]["fixture_roles"],
        "read_only": True,
    }

    return {
        "schema": "ai_subtitle_studio.nas_50_truth_learning_dry_run.v1",
        "manifest": manifest,
        "summary": summary,
        "item_summaries": item_summaries,
    }


__all__ = [
    "CALIBRATION_ITEM_NUMBERS",
    "DEFAULT_NAS_BENCHMARK_PLAN_PATH",
    "HOLDOUT_ITEM_NUMBERS",
    "NAS_TRUTH_LEARNING_SCHEMA",
    "VALIDATION_ITEM_NUMBERS",
    "build_nas_truth_learning_dry_run",
    "build_nas_truth_manifest",
    "parse_nas_truth_plan",
]
