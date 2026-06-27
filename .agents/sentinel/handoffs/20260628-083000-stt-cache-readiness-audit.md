DEX_REVIEW_READY
역할: 덱스
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: STT collect-cache backfill readiness audit

결론:
- NAS-off 상태에서 STT collect-cache 기본값 promotion은 계속 HOLD입니다.
- 새 read-only audit 도구가 기존 benchmark artifacts를 검사했고, production recommendation은 `hold_default_off`입니다.
- collect-cache 기본값은 `stt_primary_collect_cache_enabled=false`, `stt_recheck_collect_cache_enabled=false`로 유지됩니다.
- 기존 generated cache-hit artifacts는 strict duration-bound final gate에서 실패로 분류되므로 tail-collapse fix 이후 synthetic cache-hit replay를 먼저 새로 찍어야 합니다.
- strict real-media cache-hit replay evidence는 아직 `0`입니다.

수정 파일:
- `tools/audit_stt_cache_backfill_readiness.py`
- `tests/test_stt_cache_backfill_readiness.py`
- `ACTION_ITEMS.md`
- `COMPLETED_ACTION_ITEMS.md`
- `docs/VALIDATION.md`
- `docs/HANDOFF.md`
- `test_result.md`
- `.agents/sentinel/handoff.md`

검증:
- `./venv/bin/python -m py_compile tools/audit_stt_cache_backfill_readiness.py tests/test_stt_cache_backfill_readiness.py` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_cache_backfill_readiness.py tests/test_stage_variance_summary.py` -> `7 passed`.
- `./venv/bin/python tools/audit_stt_cache_backfill_readiness.py --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260627_*/benchmark_results.json' --glob '.codex_work/benchmarks/subtitle_pipeline_variants/20260628_*/benchmark_results.json' --output-dir output/manual_verification/latest/stt_cache_backfill_readiness_20260628` -> pass.
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_recheck_service.py tests/test_media_processor_overlap.py tests/test_subtitle_engine_settings.py -k "collect_cache or macro_response_cache"` -> `4 passed, 228 deselected`.

아티팩트:
- `output/manual_verification/latest/stt_cache_backfill_readiness_20260628/stt_cache_backfill_readiness.md`
- `output/manual_verification/latest/stt_cache_backfill_readiness_20260628/stt_cache_backfill_readiness.json`
- `.agents/sentinel/handoffs/20260628-080428-watchdog-handoff-probe.md`
- `.agents/sentinel/handoffs/20260628-081500-stt-cache-readiness-support-audit.md`

덱스 확인 포인트:
- 다음 NAS-off 안전 작업은 tail-collapse-fixed synthetic collect-cache write/hit replay입니다.
- NAS가 돌아오면 HeyDealer first-180s real-media write plus cache-hit replay가 default-review 전제입니다.
- STT1/STT2 skip, word precision disable, window shrink, Fast default promotion, final gate 완화는 금지입니다.
