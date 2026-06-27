DEX_REVIEW_READY

역할: 덱스
범위: STT2 / word precision collect fallback timing precision instrumentation
읽은 파일:
- `ACTION_ITEMS.md`
- `waste_action_item.md`
- `lesson_n_learned.md`
- `core/audio/media_processor_transcribe.py`
- `core/audio/media_processor_transcribe_run.py`
- `core/audio/media_processor_transcribe_recheck.py`
- `tools/verify_full_media_pipeline.py`
- `tests/test_media_processor_overlap.py`
- `tests/test_verify_full_media_pipeline.py`

결론:
- collect/worker 내부의 WhisperKit empty/timeout -> MLX fallback overhead가 `stt_collect_whisperkit_fallback` stage span으로 측정됩니다.
- verifier `summary_metrics`, repeat summary JSON/CSV, compact CLI summary에서 fallback count/total/max elapsed를 확인할 수 있습니다.
- 동작 변경 없이 계측/검증 표면만 보강했습니다.

findings:
- Local 60s benchmark smoke: fallback count `2`, total `7.962836s`, max `7.493920s`; final overlap `0`, stable for save/reopen `true`, global max active `1`.
- Local verify smoke: fallback count `2`, total `14.900298s`, max `7.530310s`; final overlap `0`, stable for save/reopen `true`, global max active `1`.

defer:
- HeyDealer/X5 long fixture acceptance rerun remains next because current smoke proves measurement availability, not long-fixture quality parity.

덱스 확인 포인트:
- Before changing worker scheduling/cache behavior, compare long-fixture STT2/word precision collect time against `stage_wall_clock_stt_collect_whisperkit_fallback_*` metrics.
