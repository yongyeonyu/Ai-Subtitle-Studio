DEX_REVIEW_READY

# STT Recheck Duration Diagnostics

- Scope: Added behavior-preserving STT2/word precision duration diagnostics and re-ran the owner-required NAS HeyDealer first 180s reference benchmark.
- Report: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`
- Result: pass. NAS HeyDealer `mode_high` elapsed `59.255s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, acceptance `true`.
- Key interpretation: `stt2_selective_recheck.applied_count=1` is one broad rescue range, not one low-value segment. It requested `180.096s`, prepared `120.000s`, collected `37` segments, and applied `37` segment-level results.
- Next: choose any latency trim only after inspecting range/prepared audio duration and proving before/after parity on the same NAS HeyDealer fixture.
