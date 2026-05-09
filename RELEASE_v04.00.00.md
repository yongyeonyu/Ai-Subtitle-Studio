# RELEASE v04.00.00

Release date: 2026-05-09
Phase: MAC_NATIVE_APPSTORE_V4_RELEASED
Base branch: `main`
Immediately previous release: `v03.25.01`
Release app version: `04.00.00`

## Summary

v04.00.00 is the first macOS-only major release on the Apple Silicon native branch. It builds on v03.25.01 by formalizing the branch direction change: Windows release paths are removed from the active product surface, native Swift and C++ helpers are promoted further into the production subtitle pipeline, and Apple Silicon scheduling is tuned from detected chip topology rather than generic worker counts.

The release keeps subtitle quality first, but it reduces avoidable work in the expensive parts of the pipeline. STT candidate scoring, STT1/STT2 merge decisions, cut-boundary verification, timeline waveform helpers, project I/O, and Apple Silicon runtime budgeting now all prefer native or indexed paths where they match or beat the existing Python behavior.

## Changes Since v03.25.01

- Promoted the branch to a macOS Apple Silicon-only release target and removed Windows-only launcher and dependency paths from the active repository surface.
- Added Apple Silicon chip-aware runtime budgeting so worker counts, FFmpeg thread caps, cut-boundary pioneer/follower concurrency, and accelerator slot usage can adapt to the detected Mac, including M5-specific defaults on the current machine.
- Added native or indexed fast paths for STT candidate VAD alignment, peer agreement, and STT1/STT2 merge work so large candidate sets no longer rescan the full peer list on every decision.
- Kept the C++ helper for LLM macro chunk grouping available for benchmarking, but left it disabled by default because the measured Python path was still faster on the current Mac.
- Expanded the Swift-native core package and Python bridges for subtitle segments, SRT handling, project validation, waveform peaks, timeline minimap columns, policy helpers, quality helpers, and memory-pressure hooks intended for future Apple-platform reuse.
- Added native macOS memory/runtime helpers and benchmark tools for Apple Silicon scheduler behavior, native pipeline adoption, policy-engine scoring, and STT backend comparison.
- Continued packaging preparation for local `.app`, update script, beta DMG, notarization, and App Store package flows while keeping DMG creation out of normal refactor work unless explicitly requested.
- Refreshed release handoff documents to track the macOS-only direction, current native-first runtime state, and the reduced release-note history set.

## Code Review Notes

- Reviewed native acceleration changes to ensure benchmark-only helpers stay opt-in when they are not yet faster than the production Python path.
- Reviewed STT scoring and merge paths so indexed overlap filtering preserves existing candidate decisions while reducing repeated work.
- Reviewed Apple Silicon scheduler materialization so manual worker overrides still have a compatibility path when the chip-aware scheduler is disabled.
- Reviewed release-surface cleanup so deleted Windows files are documentation and launcher removals rather than hidden runtime dependencies for the macOS branch.

## Compatibility Notes

- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- This release branch is macOS-only. Windows fallback development is intentionally out of scope until the user explicitly requests a cross-platform branch again.
- Swift-native helpers remain quality-gated. Python fallbacks stay in place wherever the native path has not yet proven equal or better on benchmarked workloads.
- Existing project/state files remain compatible; native project and subtitle helpers are integrated as bridges rather than a file-format rewrite.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests tools`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -c 'import sys; from PyQt6.QtWidgets import QApplication; from ui.main.main_window import MainWindow; app = QApplication(sys.argv); win = MainWindow(); print("MainWindow OK")'`
  - `MainWindow OK`
- `venv/bin/python tools/benchmark_apple_silicon_scheduler.py --json`
  - Detected hardware: `Apple M5`, `10` CPU cores (`4P + 6E`), `10` GPU cores, `16` Neural Engine cores, `16 GB` RAM
  - Measured CPU fanout: `1 worker = 17.14 jobs/sec`, `4 = 58.16`, `7 = 72.71`, `10 = 86.12`
  - Native overlap throughput: `8062.35 calls/sec`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1317 passed, 5 subtests passed in 44.72s`

Known warnings or limits:

- In the headless test session, Python exit still prints a non-fatal Metal warning from a native module callback:
  - `RuntimeError: [metal::load_device] No Metal device available`
  - The release test run still completed successfully with exit code `0`.

## Next Direction

The next safe follow-up is to keep migrating only the quality-neutral or quality-positive heavy loops into Swift/C++ on Apple Silicon, then validate them against real Korean long-form media before replacing the remaining Python hot paths.
