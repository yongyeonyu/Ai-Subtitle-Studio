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
- `native/macos/AIStudioNative/Sources/AIStudioCore/PipelineStatus.swift`

These files are stable because they are mostly:

- pure data transforms
- deterministic scoring or layout logic
- JSON-in / JSON-out helpers
- low Qt coupling
- already covered by focused tests

## Active Native Queue

These are the remaining Python/native seams worth considering next:

- `core/media_info.py`
  - Only the probe-result normalization layer, not the full orchestration.
  - Cache key + ffprobe result shaping can move first.
  - Python-side fingerprint/stat caching is now lighter, so native migration should only graduate if parity benchmarks beat the cached Python path.

- cut-boundary scoring and alignment families
  - Only after the Python helper-builder split lands and the interfaces stop moving.
  - Promote only the numerically heavy loops, not the surrounding orchestration.

- subtitle candidate scoring and sequence smoothing
  - Only after the current Python scoring pipeline is split into stable scorer/planner seams.
  - Prefer Swift/C++ only where repeated large-batch transforms beat the bridge cost.

## Parked Or Rejected For Now

- `core/project/project_model_settings.py`
  - Keep this Python-side for now.
  - The payload is small, deterministic Python reads are already cheap, and bridge/parity cost is higher than the likely gain.
  - Revisit only if project-open/save benchmarks show this path becoming materially larger.

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
- live automation/status snapshot assembly in `ui/main/app_command_bridge.py`

Reasons:

- Qt lifecycle coupling
- thread/event ordering
- subprocess management
- dynamic settings overrides
- fallback-heavy AI/runtime routing
- project state mutation across many layers
- live logger/owner state where Python-side cache/count helpers beat native bridge overhead
- live log-tail and stage-inference hot paths where `deque` tail slicing plus cached string patterns avoid native bridge serialization entirely
- viewport-scoped Qt render caches where Python can reuse existing list objects without crossing a native bridge
- filesystem cache accounting/pruning where streaming `os.scandir` avoids Python object churn without paying native bridge payload cost

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

Small payloads should stay in Python when the native bridge cost is higher than the savings.

## Current Status

1st bundle complete:

- `core/pipeline/startup_diagnostics.py`
  - Native library now owns diagnostic build, ETA attach, and log formatting.
  - Python keeps media/audio probing and fallback behavior.

- `core/pipeline/cut_boundary_cache.py`
  - Native library now owns canonical settings payload, base payload shaping, and cache-path planning.
  - Python still owns file stat and media fingerprint collection to preserve current cache parity.

- `core/pipeline_status.py`
  - Native library now owns the optional stage-summary reduction path through `PipelineStatus.swift` and the persistent `core-jsonl-worker`.
  - Python keeps the small-blob parser/cache plus fallback path so bridge cost is reserved for larger multiline payloads where it helps more.

Python-side hot-path prep complete:

- `core/media_info.py`
  - Repeated media fingerprint reads are cached by resolved path, mtime, and size before the ffprobe cache path is selected.
  - Probe-result normalization remains isolated as the safe native seam, but the current cached Python path is the baseline to beat.

- `core/project/project_model_settings.py`
  - Summary/snapshot accessors and restore helpers are now isolated and cheaper on the Python side.
  - This is deliberately parked as a non-native path unless future measurements show a larger real payload than today.

- `core/project/project_assets.py` / `ui/editor/editor_canvas_state.py`
  - Row-copy, SRT-write, canvas-FPS hydration, and runtime-capture boundary copies now avoid extra temporary list materialization for streaming row inputs.
  - Keep these Python-side unless a future native text-asset writer beats the current alias-safe copy path on real project open/save benchmarks.

- `ui/timeline/timeline_canvas.py` / `ui/timeline/timeline_paint.py`
  - Voice-activity paint now reuses cached visible marker lists instead of copying the cached list per paint.
  - Keep this Python/Qt-side for now: the measured win comes from avoiding object churn in existing widget state, while a native bridge would add serialization/lifetime overhead.

- `core/runtime/memory_manager.py`
  - Runtime disk-cache usage and prune now share a streaming `os.scandir` walker with string paths instead of materializing recursive `Path.rglob("*")` / per-file `Path` objects.
  - Under-budget prune now takes a total-only fast path and skips deletion-candidate list/sort work in the common healthy-cache case.
  - Root-level cache indexes now update on file create/delete events, preview-cache usage is included in the runtime budget, and thumbnail/proxy caches prune against hard local budgets without a native bridge.
  - Keep this Python-side for now because filesystem traversal already happens at the OS boundary and the current streaming/fast-path design avoids the largest allocation without JSON bridge overhead.
