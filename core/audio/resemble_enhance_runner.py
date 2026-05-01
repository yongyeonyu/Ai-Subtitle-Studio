# Version: 03.05.09
# Phase: PHASE2
"""Compatibility runner for Resemble Enhance CLI."""

from __future__ import annotations

import sys


def _patch_torchaudio_path_args() -> None:
    try:
        import torchaudio
    except Exception:
        return

    original_load = torchaudio.load
    original_save = torchaudio.save

    def load(uri, *args, **kwargs):
        return original_load(str(uri), *args, **kwargs)

    def save(uri, *args, **kwargs):
        return original_save(str(uri), *args, **kwargs)

    torchaudio.load = load
    torchaudio.save = save


def main() -> int:
    _patch_torchaudio_path_args()
    from resemble_enhance.enhancer.__main__ import main as resemble_main

    result = resemble_main()
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
