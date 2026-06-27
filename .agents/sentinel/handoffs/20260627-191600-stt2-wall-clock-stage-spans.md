DEX_REVIEW_READY

# STT2 / Word Precision Wall-Clock Stage Spans

- Scope: direct wall-clock stage-span instrumentation for generation-latency evidence.
- Changed surfaces: `core/audio/media_processor_transcribe.py`, `core/audio/media_processor_transcribe_recheck.py`, `tools/benchmark_subtitle_pipeline_variants.py`, `tools/verify_full_media_pipeline.py`, docs/results.
- Evidence report: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
- Non-reference HeyDealer 180s probe: elapsed `65.222s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`; stage spans STT1 `18.162010s`, STT2 `14.360250s`, word precision `12.489603s`, postprocess `20.108474s`.
- Reference-scored HeyDealer 180s benchmark: elapsed `65.824s`, raw/final `58/56`, quality `81.335`, timing MAE `1.5958s`, final overlap `0`; stage spans STT1 `19.519015s`, STT2 `14.229755s`, word precision `12.560951s`, postprocess `19.406983s`.
- Next review-ready action: inspect measured stages for redundant waiting, duplicate cache work, avoidable scheduling serialization, or proven cleanup churn only. Do not reduce STT2, word precision, LLM, LoRA, VAD, timing, or final stability policy.
