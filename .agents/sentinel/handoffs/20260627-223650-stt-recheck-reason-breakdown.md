DEX_REVIEW_READY

# STT Recheck Reason Breakdown

- Scope: Added behavior-preserving reason breakdown diagnostics for STT2 selective recheck and word precision, then re-ran the owner-required NAS HeyDealer first 180s reference benchmark.
- Report: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`
- Result: pass. NAS HeyDealer `mode_high` elapsed `58.820s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, acceptance `true`.
- Key interpretation: STT2 is a missing-voice rescue path (`missing_voice/route_hint/low_score/empty_text=1/0/0/1`). Word precision selected `25` ranges, but none were selected/review/red/yellow/risk/missing-word forced (`0/0/0/0/0/0/0`).
- Next: look for collect scheduling/cache reuse or decision-equivalent High context-boundary proof before changing STT2/word precision quality policy.
