DEX_REVIEW_READY

# STT2 / Word Precision Context-Boundary Batch Rejection

## Summary

- Tried batching non-overlapping High context-boundary LLM pair checks into one Ollama JSON call.
- Temporary focused tests passed, but the real HeyDealer reference-scored fixture showed small quality/text/segmentation drift.
- Dex reverted the candidate code and kept only documentation/rejection evidence.

## Evidence

- Report: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`
- Non-profile repeat with candidate: pipeline elapsed `[69.223, 67.564]`, avg `68.393s`, raw/final `58/55`, final overlap `0`, stable for save/reopen, memory pressure `critical`.
- Reference run with candidate: elapsed `64.222s`, raw/final `58/56`, quality `81.316`, text `94.241`, timing MAE `1.5958s`, segmentation `87.812`, final overlap `0`, stable for save/reopen.
- Accepted prior reference baseline: quality `81.335`, text `94.267`, timing MAE `1.5958s`, segmentation `87.879`.

## Decision

- Reject/revert. The candidate lowered subtitle postprocess time to `9.879991s`, but changed one LLM boundary/word decision and reduced reference quality.
- Do not retry this batching direction unless a new parity guard first proves batch decisions exactly match per-pair decisions on the same rows.
