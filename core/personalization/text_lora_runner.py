from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.text_lora_dataset import (
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_DATASET_DIR,
    VOICE_LORA_BRIDGE_PATH,
)


TEXT_LORA_TRAINING_PLAN_PATH = TEXT_LORA_DATASET_DIR / "text_lora_training_plan.json"
VOICE_LORA_PROFILE_MANIFEST_PATH = TEXT_LORA_DATASET_DIR / "voice_lora_profile_manifest.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def build_text_lora_training_plan(
    *,
    corpus_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    base_model: str = "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
    adapter_name: str = "personal_text_lora",
    epochs: int = 3,
    learning_rate: float = 1e-4,
    lora_rank: int = 8,
    micro_batch_size: int = 1,
) -> dict[str, Any]:
    corpus_target = Path(corpus_path) if corpus_path else TEXT_LORA_CORPUS_PATH
    out_dir = Path(output_dir) if output_dir else (TEXT_LORA_DATASET_DIR / "trained_adapters" / adapter_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_jsonl(corpus_target)
    usable_rows = [row for row in rows if str(row.get("task", "") or "") == "text_correction"]
    sources = defaultdict(int)
    speakers = defaultdict(int)
    for row in usable_rows:
        sources[str(row.get("source", "") or "unknown")] += 1
        meta = row.get("meta", {}) if isinstance(row.get("meta"), dict) else {}
        speaker = str(meta.get("speaker", "") or "")
        if speaker:
            speakers[speaker] += 1

    backend = "mlx_lm_lora" if _module_exists("mlx_lm") else "unavailable"
    command = []
    if backend == "mlx_lm_lora":
        command = [
            "python3",
            "-m",
            "mlx_lm.lora",
            "--model",
            base_model,
            "--train",
            "--data",
            str(corpus_target),
            "--iters",
            str(max(100, len(usable_rows) * max(1, int(epochs)))),
            "--learning-rate",
            str(learning_rate),
            "--batch-size",
            str(max(1, int(micro_batch_size))),
            "--lora-layers",
            str(max(4, int(lora_rank))),
            "--adapter-path",
            str(out_dir),
        ]

    plan = {
        "schema": "ai_subtitle_studio.text_lora_training_plan.v1",
        "created_at": _now(),
        "platform": "mac",
        "backend": backend,
        "base_model": base_model,
        "adapter_name": adapter_name,
        "output_dir": str(out_dir),
        "corpus_path": str(corpus_target),
        "corpus_manifest_path": str(TEXT_LORA_CORPUS_MANIFEST_PATH),
        "stats": {
            "total_rows": len(rows),
            "usable_text_rows": len(usable_rows),
            "source_breakdown": dict(sorted(sources.items())),
            "speaker_breakdown": dict(sorted(speakers.items())),
        },
        "hyperparams": {
            "epochs": int(epochs),
            "learning_rate": float(learning_rate),
            "lora_rank": int(lora_rank),
            "micro_batch_size": int(micro_batch_size),
        },
        "command": command,
        "notes": [
            "mac first text LoRA training scaffold",
            "uses accumulated personalization corpus",
            "voice LoRA remains separate but shares frame/speaker bridge",
        ],
    }
    return plan


def save_text_lora_training_plan(**kwargs) -> dict[str, Any]:
    plan = build_text_lora_training_plan(**kwargs)
    TEXT_LORA_TRAINING_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEXT_LORA_TRAINING_PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "plan_path": str(TEXT_LORA_TRAINING_PLAN_PATH),
        "backend": str(plan.get("backend", "") or ""),
        "usable_rows": int(((plan.get("stats") or {}).get("usable_text_rows", 0)) or 0),
        "output_dir": str(plan.get("output_dir", "") or ""),
    }


def build_voice_lora_profile_manifest(
    *,
    bridge_path: str | Path | None = None,
) -> dict[str, Any]:
    bridge_target = Path(bridge_path) if bridge_path else VOICE_LORA_BRIDGE_PATH
    rows = _read_jsonl(bridge_target)
    by_speaker: dict[str, dict[str, Any]] = {}
    for row in rows:
        speaker = str(row.get("speaker", "") or "unknown")
        item = by_speaker.setdefault(
            speaker,
            {
                "speaker": speaker,
                "segments": 0,
                "total_frames": 0,
                "clips": set(),
                "projects": set(),
                "texts": 0,
            },
        )
        item["segments"] += 1
        item["total_frames"] += int(row.get("duration_frames", 0) or 0)
        clip_path = str(row.get("clip_path", "") or "")
        project_path = str(row.get("project_path", "") or "")
        if clip_path:
            item["clips"].add(clip_path)
        if project_path:
            item["projects"].add(project_path)
        if str(row.get("text", "") or "").strip():
            item["texts"] += 1

    speakers = []
    for speaker, item in sorted(by_speaker.items()):
        speakers.append(
            {
                "speaker": speaker,
                "segments": int(item["segments"]),
                "total_frames": int(item["total_frames"]),
                "clip_count": len(item["clips"]),
                "project_count": len(item["projects"]),
                "text_count": int(item["texts"]),
                "ready_for_voice_lora": bool(item["segments"] >= 20 and item["total_frames"] >= 2400),
            }
        )

    manifest = {
        "schema": "ai_subtitle_studio.voice_lora_profile_manifest.v1",
        "created_at": _now(),
        "bridge_path": str(bridge_target),
        "speaker_profiles": speakers,
        "notes": [
            "frame/speaker based voice lora bridge summary",
            "used to decide when enough per-speaker data exists",
        ],
    }
    return manifest


def save_voice_lora_profile_manifest(**kwargs) -> dict[str, Any]:
    manifest = build_voice_lora_profile_manifest(**kwargs)
    VOICE_LORA_PROFILE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOICE_LORA_PROFILE_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "manifest_path": str(VOICE_LORA_PROFILE_MANIFEST_PATH),
        "speaker_profiles": int(len(list(manifest.get("speaker_profiles") or []))),
    }


__all__ = [
    "TEXT_LORA_TRAINING_PLAN_PATH",
    "VOICE_LORA_PROFILE_MANIFEST_PATH",
    "build_text_lora_training_plan",
    "save_text_lora_training_plan",
    "build_voice_lora_profile_manifest",
    "save_voice_lora_profile_manifest",
]
