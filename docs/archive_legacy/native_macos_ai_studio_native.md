# AIStudioNative Legacy Reference

Historical Swift-native macOS core package reference. The current product line
is the Python/PyQt6 source app; native migration, Swift rewrite, and separate
native-app conversion remain opt-in unless the owner explicitly reopens that
scope.

The package starts with the data layer that must stay lossless while the app
moves away from Python/PyQt:

- `AIStudioCore`: Swift subtitle data models and SRT parsing/formatting.
- `ProjectJSON`: Swift project JSON validation, runtime-key stripping, summary,
  and atomic write helpers.
- `WaveformPeaks`: Swift f32le waveform peak/downsample engine for timeline
  rendering data.
- `TimelineColumns`: Swift minimap column builder for Mac-optimized timeline
  paint caches.
- `SubtitleQualityScorer`: Swift batch scorer for subtitle confidence A/B
  testing. It is currently opt-in because the CLI JSON bridge is slower than
  in-process Python on ordinary batches until a persistent native worker is
  attached.
- `CommonSplitPlanner`: Swift planner for common subtitle split/clamp decisions.
  Packaged macOS builds use it adaptively on large batches while Python keeps
  metadata-safe row assembly.
- `AIStudioNativeCLI`: small command-line bridge used by the transitional
  Python app and by packaging smoke checks.

Archived migration policy:

- Treat this as reference material for existing native helper code and packaging
  smoke checks.
- Do not use this document to start a native migration, Swift rewrite, or UI
  conversion without a fresh owner-approved gate in
  `docs/planning_queue/ACTION_ITEMS.md`.

Useful commands:

```bash
swift test --package-path native/macos/AIStudioNative
swift build -c release --package-path native/macos/AIStudioNative
native/macos/AIStudioNative/.build/release/AIStudioNativeCLI version
```
