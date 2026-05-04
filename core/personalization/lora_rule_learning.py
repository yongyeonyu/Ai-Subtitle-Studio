from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.lora_models import LearnedRuleEntry
from core.personalization.lora_storage import (
    load_learned_rules,
    save_learned_rules,
    store_paths,
)
from core.runtime import config


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = __import__("json").loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = max(0.0, min(1.0, percent / 100.0)) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return round(ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction), 3)


def load_truth_table_rows(store_dir: str | Path | None = None) -> list[dict[str, Any]]:
    paths = store_paths(store_dir)
    return _read_jsonl(paths["truth_table"])


def analyze_truth_table_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    split_counts: Counter[str] = Counter()
    line_break_counts: Counter[str] = Counter()
    punctuation_counts: Counter[str] = Counter()
    split_examples: dict[str, list[str]] = {}
    line_examples: dict[str, list[str]] = {}
    split_media_refs: dict[str, set[str]] = {}
    line_media_refs: dict[str, set[str]] = {}
    char_counts: list[float] = []
    cps_values: list[float] = []
    durations: list[float] = []
    multiline_rows = 0

    for row in rows or []:
        speech_text = str(row.get("speech_training_text") or "")
        if speech_text:
            char_counts.append(float(row.get("char_count", 0) or 0))
            cps_values.append(float(row.get("cps", 0.0) or 0.0))
            durations.append(float(row.get("duration_sec", 0.0) or 0.0))
        media_ref = str(row.get("media_id") or row.get("media_path") or "")

        line_break_pattern = str(row.get("line_break_pattern") or "").strip()
        if line_break_pattern:
            line_break_counts[line_break_pattern] += 1
            line_examples.setdefault(line_break_pattern, [])
            if speech_text and len(line_examples[line_break_pattern]) < 5:
                line_examples[line_break_pattern].append(speech_text)
            line_media_refs.setdefault(line_break_pattern, set()).add(media_ref)
            if "|" in line_break_pattern:
                multiline_rows += 1

        punctuation_pattern = str(row.get("punctuation_pattern") or "").strip()
        if punctuation_pattern:
            punctuation_counts[punctuation_pattern] += 1

        split_rule = str(row.get("detected_split_rule") or "").strip()
        if split_rule:
            split_counts[split_rule] += 1
            split_examples.setdefault(split_rule, [])
            if speech_text and len(split_examples[split_rule]) < 5:
                split_examples[split_rule].append(speech_text)
            split_media_refs.setdefault(split_rule, set()).add(media_ref)

    split_total = max(1, sum(split_counts.values()))
    line_total = max(1, sum(line_break_counts.values()))

    split_items = [
        LearnedRuleEntry(
            rule_text=rule,
            rule_type="split_rule",
            frequency=count,
            confidence=count / split_total,
            examples=split_examples.get(rule, []),
            source_media_refs=sorted(split_media_refs.get(rule, set())),
        ).to_record()
        for rule, count in split_counts.most_common()
    ]
    line_break_items = [
        LearnedRuleEntry(
            rule_text=pattern,
            rule_type="line_break_rule",
            frequency=count,
            confidence=count / line_total,
            examples=line_examples.get(pattern, []),
            source_media_refs=sorted(line_media_refs.get(pattern, set())),
        ).to_record()
        for pattern, count in line_break_counts.most_common()
    ]

    summary = {
        "truth_row_count": len(rows or []),
        "multiline_row_count": multiline_rows,
        "char_count_p50": _percentile(char_counts, 50),
        "char_count_p90": _percentile(char_counts, 90),
        "cps_p50": _percentile(cps_values, 50),
        "cps_p90": _percentile(cps_values, 90),
        "duration_p50": _percentile(durations, 50),
        "duration_p90": _percentile(durations, 90),
        "top_punctuation_patterns": [
            {"pattern": pattern, "frequency": count}
            for pattern, count in punctuation_counts.most_common(10)
        ],
    }
    return {
        "split_items": split_items,
        "line_break_items": line_break_items,
        "summary": summary,
    }


def learn_rules_from_truth_table(store_dir: str | Path | None = None) -> dict[str, Any]:
    rows = load_truth_table_rows(store_dir)
    analysis = analyze_truth_table_rows(rows)
    split_payload = save_learned_rules(
        "split",
        analysis["split_items"],
        metadata={"summary": analysis["summary"]},
        store_dir=store_dir,
    )
    line_payload = save_learned_rules(
        "line_break",
        analysis["line_break_items"],
        metadata={"summary": analysis["summary"]},
        store_dir=store_dir,
    )
    return {
        "split_rule_count": len(split_payload["items"]),
        "line_break_rule_count": len(line_payload["items"]),
        "summary": analysis["summary"],
    }


def build_split_rule_update_review(
    *,
    store_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    learned = load_learned_rules("split", store_dir)
    if not list(learned.get("items") or []):
        learn_rules_from_truth_table(store_dir)
        learned = load_learned_rules("split", store_dir)

    proposed_rules = [
        str(item.get("rule_text") or "").strip()
        for item in list(learned.get("items") or [])
        if str(item.get("rule_text") or "").strip()
    ][: max(0, int(top_n))]
    current_rules = list(getattr(config, "DEFAULT_SPLIT_RULES", []) or [])
    return {
        "config_path": str(config_path or Path(config.__file__)),
        "top_n": int(top_n),
        "current_rules": current_rules,
        "proposed_rules": proposed_rules,
        "needs_update": proposed_rules != current_rules[: len(proposed_rules)],
        "learned_summary": dict((learned.get("metadata") or {}).get("summary") or {}),
    }


def _format_split_rule_block(rules: list[str]) -> str:
    chunks = [rules[index:index + 6] for index in range(0, len(rules), 6)]
    lines = ["DEFAULT_SPLIT_RULES = ["]
    for chunk in chunks:
        quoted = ", ".join(f'"{item}"' for item in chunk)
        suffix = "," if chunk is not chunks[-1] else ""
        lines.append(f"    {quoted}{suffix}")
    lines.append("]")
    return "\n".join(lines)


def apply_split_rule_update_review(
    *,
    store_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    review = build_split_rule_update_review(store_dir=store_dir, config_path=config_path, top_n=top_n)
    proposed_rules = list(review.get("proposed_rules") or [])
    target_path = Path(str(review["config_path"]))
    source = target_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"DEFAULT_SPLIT_RULES = \[\n(?:.*\n)*?\]\nDEFAULT_SPLIT_PUNCTUATION =",
        re.MULTILINE,
    )
    replacement = _format_split_rule_block(proposed_rules) + "\nDEFAULT_SPLIT_PUNCTUATION ="
    if not pattern.search(source):
        raise ValueError("DEFAULT_SPLIT_RULES block not found in config.py")

    backup_dir = store_paths(store_dir)["root"] / "config_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = backup_dir / f"config.py.{timestamp}.bak"
    backup_path.write_text(source, encoding="utf-8")
    updated = pattern.sub(replacement, source, count=1)
    target_path.write_text(updated, encoding="utf-8")
    return {
        "config_path": str(target_path),
        "backup_path": str(backup_path),
        "applied_rules": proposed_rules,
        "rule_count": len(proposed_rules),
    }


__all__ = [
    "analyze_truth_table_rows",
    "apply_split_rule_update_review",
    "build_split_rule_update_review",
    "learn_rules_from_truth_table",
    "load_truth_table_rows",
]
