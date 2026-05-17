# Native Library Plan

This file contains only the remaining native-library work and migration rules.
Completed native modules are intentionally omitted from the active queue.

## Migration Rules

- Migrate by function family, not by whole orchestration files.
- Keep Python fallback until parity, performance, and real-media behavior are proven.
- Prefer Swift for Apple-platform reusable core logic and C++ for narrow numeric kernels already adjacent to existing C++ paths.
- Use `.js` only when the runtime boundary is already JavaScript/QML-oriented and the measured result is equal or faster.
- Do not migrate live Qt widgets, mutable editor state, subprocess orchestration, model-worker ownership, or UI callbacks.
- Do not change UI, UX, subtitle quality, or existing behavior as part of native migration unless the owner explicitly approves it.
- Promote native code only when the native path is equal or faster than the current cached Python path on real fixtures.

## Graduation Checklist

A Python function family may move into native library form only when all items are true:

- The behavior is deterministic for the same input.
- It can be expressed as JSON-in / JSON-out or typed value-in / value-out.
- It does not depend on live Qt objects.
- It does not own long-running model processes.
- It already has focused tests for the Python behavior.
- The interface is stable enough to justify compile/build overhead.
- A Python fallback exists and stays covered by tests.
- Benchmarks include a real fixture, not only synthetic payloads.

## Active Native Queue

- [ ] 1. Benchmark native media-info normalization against the current cached Python path.
  Scope: probe-result normalization, media-info copy/presence helpers, cache-key shaping, and ffprobe-result payload shaping only.
  Keep in Python: ffprobe subprocess orchestration, file stat/fingerprint collection, project-session ownership, and UI status display.
  Promote only if: Swift normalization beats or matches the cached Python path on project open/save benchmarks without changing serialized media metadata.
  Verification: Macau project smoke plus project open/save benchmark; use Tinyping only if long-media project metadata is affected.

- [ ] 2. Prepare cut-boundary scoring and alignment loops for Swift/C++.
  Scope: deterministic color/gray/delta/alignment scoring loops, dense frame comparison kernels, and boundary-candidate numeric reduction.
  Prerequisite: split helper-builder functions in `core/pipeline/cut_boundary_helpers.py`, `core/cut_boundary_auto_scan.py`, and `core/cut_boundary_auto_verify.py` into stable Python interfaces first.
  Keep in Python: UI helper-line policy, project mutation, logging, worker orchestration, media probing, and fallback routing.
  Verification: cut-boundary unit tests plus Macau visual smoke.

- [ ] 3. Prepare subtitle candidate scoring and sequence smoothing for native acceleration.
  Scope: `core/audio/stt_candidate_scorer.py`, `core/audio/stt_lattice.py`, `core/engine/subtitle_accuracy_pipeline.py`, `core/engine/subtitle_timing.py`, and `core/engine/word_resegmenter.py` hot loops.
  Prerequisite: isolate scorer/planner interfaces and preserve original STT evidence ranges before native promotion.
  Promote only if: final subtitle text/timing accuracy is equal or higher on X5 and Tinyping checks.
  Verification: X5 accuracy slice plus targeted unit tests.

- [ ] 4. Split oversized Swift core files before expanding native features.
  Scope:
  `TimelineEditing.swift` -> geometry, magnet, undo, and serialization files.
  `NativePolicyEngine.swift` -> scoring, retrieval, and decision files.
  `RuntimeETAEstimator.swift` -> persistence and prediction files.
  Promote only if: Swift tests stay green and Python bridge contracts do not change.
  Verification: `swift test` in `native/macos/AIStudioNative`.

- [ ] 5. Measure native bridge payload sizes before adding new bridge calls.
  Scope: `core/native_swift_policy.py`, `core/native_swift_subtitle.py`, `core/native_swift_timeline.py`, `core/native_json.py`, and the persistent `core-jsonl-worker`.
  Success: large-batch native calls are preferred only when serialization/bridge cost does not erase the native win.
  Keep in Python: small payloads where cached Python work is cheaper than bridge setup.
  Verification: JSON payload size logs plus targeted benchmark artifacts under `output/manual_verification/latest/`.

## Parked Or Rejected For Now

- `core/project/project_model_settings.py`
  Decision: keep Python-side.
  Reason: payload is small, deterministic Python reads are cheap, and bridge/parity cost is higher than the likely gain.

- `core/audio/media_processor_transcribe.py`
- `core/audio/media_processor_audio.py`
- `core/pipeline/single_pipeline.py`
- `core/pipeline/backend_core.py`
- `core/backend_fast.py`
- most `ui/editor/*`
- most `ui/timeline/*` widgets with Qt object state
- live automation/status snapshot assembly in `ui/main/app_command_bridge.py`
  Decision: do not migrate as whole modules.
  Reason: these paths own Qt lifecycle, subprocesses, dynamic settings, model routing, mutable project state, live logger state, or UI callbacks.

## Practical Target

Native code should own stable algorithmic hot paths, repeated large-batch transforms, deterministic layout/scoring/planning, and canonical serialization/normalization rules.

Native code should not be used just to reduce Python line count. If a migration mirrors live UI/runtime state or adds bridge overhead without a measured win, leave it in Python and refactor the Python boundary instead.
