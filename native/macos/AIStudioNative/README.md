# AIStudioNative

Swift-native macOS core package for the macOS-only migration branch.

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

Current migration policy:

- New macOS-native logic should be implemented here first when it can match or
  exceed the Python behavior.
- Python remains a compatibility fallback until the Swift implementation has
  tests and packaged-app verification.
- User-facing UI should move toward SwiftUI/AppKit modules after the subtitle
  data, media routing, STT worker, waveform/timeline, and project I/O layers are
  stable in Swift.

Useful commands:

```bash
swift test --package-path native/macos/AIStudioNative
swift build -c release --package-path native/macos/AIStudioNative
native/macos/AIStudioNative/.build/release/AIStudioNativeCLI version
```
