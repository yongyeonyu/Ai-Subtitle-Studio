# Native Library Plan

This branch already has a safe native migration path:

1. Move deterministic, side-effect-light logic into `native/macos/AIStudioNative/Sources/AIStudioCore/`
2. Expose it through `AIStudioNativeCLI` JSON commands or the `core-jsonl-worker`
3. Keep a Python fallback until tests and real-media benchmarks prove parity

This is safer than pushing large Python orchestration files directly into a `dylib`.
The current app depends on Python runtime state, Qt object lifetime, subprocess workers,
and packaging constraints, so direct "compile the whole file" conversion is not a good
default for most modules.

## Already Good Native/Library Targets

These are already in the right shape for library ownership:

- `native/macos/AIStudioNative/Sources/AIStudioCore/SRTCodec.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/SubtitleSegment.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/ProjectJSON.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/WaveformPeaks.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/TimelineColumns.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/TimelineEditing.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/SubtitleQualityScorer.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/CommonSplitPlanner.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/MemoryPressure.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/InputActivity.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/RuntimeETAEstimator.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/StartupDiagnostics.swift`
- `native/macos/AIStudioNative/Sources/AIStudioCore/CutBoundaryCachePlanner.swift`

These files are stable because they are mostly:

- pure data transforms
- deterministic scoring or layout logic
- JSON-in / JSON-out helpers
- low Qt coupling
- already covered by focused tests

## Safe Next Candidates

These are the next Python modules worth migrating into native library code:

- `core/pipeline_status.py`
  - String parsing and stage classification only.
  - Easy parity testing.

- `core/project/project_model_settings.py`
  - Project model snapshot normalization logic.
  - Good candidate if project load/save rules stop changing.

- `core/media_info.py`
  - Only the probe-result normalization layer, not the full orchestration.
  - Cache key + ffprobe result shaping can move first.

## Do Not Migrate Yet

These are too orchestration-heavy right now and would likely make the project harder,
not lighter, if forced into native code too early:

- `core/audio/media_processor_transcribe.py`
- `core/audio/media_processor_audio.py`
- `core/pipeline/single_pipeline.py`
- `core/pipeline/backend_core.py`
- `core/backend_fast.py`
- most `ui/editor/*`
- most `ui/timeline/*` widgets with Qt object state

Reasons:

- Qt lifecycle coupling
- thread/event ordering
- subprocess management
- dynamic settings overrides
- fallback-heavy AI/runtime routing
- project state mutation across many layers

## Graduation Checklist

A Python module or function should move into native library form only when all are true:

- The behavior is deterministic for the same input.
- It can be expressed as JSON-in / JSON-out or typed value-in / value-out.
- It does not depend on live Qt objects.
- It does not own long-running model processes.
- It already has focused tests that describe expected behavior.
- The logic changes rarely enough to justify compile/build overhead.
- A Python fallback exists until parity is proven.

## Recommended Migration Rule

Prefer migrating by **function family**, not by whole file.

Good:

- one planner
- one scorer
- one layout engine
- one cache-key builder

Bad:

- a whole pipeline file
- a mixed UI/runtime/orchestration module
- a file with live callbacks and mutable editor state

## Practical Goal

The project gets meaningfully lighter when native code owns:

- stable algorithmic hot paths
- repeated large-batch transforms
- layout/scoring/planning code
- canonical serialization/normalization rules

The project does **not** get lighter just because source lines move out of Python.
If the migrated code still has to mirror Qt state or runtime orchestration, complexity
usually increases.

## Current Status

1st bundle complete:

- `core/pipeline/startup_diagnostics.py`
  - Native library now owns diagnostic build, ETA attach, and log formatting.
  - Python keeps media/audio probing and fallback behavior.

- `core/pipeline/cut_boundary_cache.py`
  - Native library now owns canonical settings payload, base payload shaping, and cache-path planning.
  - Python still owns file stat and media fingerprint collection to preserve current cache parity.
