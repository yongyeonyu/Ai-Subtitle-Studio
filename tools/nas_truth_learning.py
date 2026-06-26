#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.personalization.nas_truth_learning import build_nas_truth_learning_dry_run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a read-only NAS 50 truth-learning manifest.")
    parser.add_argument("--plan", default="docs/NAS_SUBTITLE_BENCHMARK_50_PLAN.md")
    parser.add_argument("--nas-root", default=None)
    parser.add_argument("--with-records", action="store_true", help="Parse SRTs and build in-memory truth rows.")
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print full JSON payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = build_nas_truth_learning_dry_run(
        plan_path=args.plan,
        nas_root=args.nas_root,
        include_truth_records=args.with_records,
        max_items=args.max_items,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    summary = result["summary"]
    print("NAS 50 truth-learning dry-run")
    print(f"plan={result['manifest']['plan_path']}")
    print(f"nas_root={result['manifest']['nas_root']}")
    print(f"items_total={summary['items_total']}")
    print(f"present_pairs={summary['present_pairs']}")
    print(f"missing_media={summary['missing_media']}")
    print(f"missing_subtitle={summary['missing_subtitle']}")
    print(f"dataset_splits={summary['dataset_splits']}")
    print(f"fixture_roles={summary['fixture_roles']}")
    if args.with_records:
        print(f"analyzed_pairs={summary['analyzed_pairs']}")
        print(f"truth_rows={summary['truth_rows']}")
        print(f"excluded_parenthetical_rows={summary['excluded_parenthetical_rows']}")
        print(f"voice_bridge_rows={summary['voice_bridge_rows']}")
        print(f"multimodal_context_rows={summary['multimodal_context_rows']}")
        print(f"importable_truth_rows={summary['importable_truth_rows']}")
        print(f"split_analysis_effective_rows={summary['split_analysis_effective_rows']}")
        print(f"skipped_empty_text={summary['skipped_empty_text']}")
        print(f"skipped_pure_symbols={summary['skipped_pure_symbols']}")
        print(f"skipped_rows={summary['skipped_rows']}")
    print("read_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
