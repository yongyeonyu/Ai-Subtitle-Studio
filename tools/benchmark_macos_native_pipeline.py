from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.audio_extract_backend_router import select_audio_extract_backend
from core.audio.stt_backend_router import select_stt_backend
from core.cut_boundary_backend_router import select_cut_boundary_backend
from core.performance import hardware_profile
from core.runtime import config
from core.settings_profiles import materialize_user_settings


def _choice_dict(obj) -> dict:
    return {
        key: getattr(obj, key)
        for key in ("backend", "model", "reason", "scan_path", "use_proxy", "direct_chunk_min_sec")
        if hasattr(obj, key)
    }


def _migration_decisions(routes: dict) -> dict:
    stt = dict(routes.get("stt") or {})
    audio = dict(routes.get("audio_clearvoice") or {})
    cut = dict(routes.get("cut_boundary") or {})
    return {
        "stt_primary": "adopt" if stt.get("backend") == "whisperkit_persistent" else "fallback",
        "clearvoice_audio": "adopt" if audio.get("backend") == "ffmpeg_direct_chunks" else "benchmark_more",
        "cut_boundary": "adopt" if str(cut.get("backend") or "").startswith("native") else "benchmark_more",
        "notes": [
            "Only promote native helpers when output quality is equal or better on real media.",
            "Keep MLX/whisper.cpp fallback routes available for comparison and recovery.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark macOS native routing readiness.")
    parser.add_argument("--media", default="", help="Optional media path for cut-boundary scan routing.")
    parser.add_argument("--span-sec", type=float, default=600.0, help="Audio span used for extraction routing.")
    args = parser.parse_args()

    started = time.perf_counter()
    settings = materialize_user_settings({})
    media_path = str(Path(args.media).expanduser()) if args.media else "sample.mp4"

    routes = {
        "stt": _choice_dict(select_stt_backend(settings.get("selected_whisper_model"), settings)),
        "audio_clearvoice": _choice_dict(
            select_audio_extract_backend(settings, audio_ai="clearvoice", span_sec=float(args.span_sec))
        ),
        "cut_boundary": _choice_dict(select_cut_boundary_backend(media_path, settings)),
    }
    payload = {
        "schema": "ai_subtitle_studio.macos_native_pipeline_benchmark.v1",
        "macbook_only_app": bool(getattr(config, "MACBOOK_ONLY_APP", False)),
        "app_store_target": bool(getattr(config, "APP_STORE_TARGET", False)),
        "platform": {
            "is_mac": bool(config.IS_MAC),
            "is_apple_silicon": bool(config.IS_APPLE_SILICON),
            "machine": config.MACHINE,
        },
        "hardware": hardware_profile(),
        "routes": routes,
        "migration_decisions": _migration_decisions(routes),
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
