DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio STT cache readiness audit support

findings:
1. **캐시 기본값 상태**: `stt_primary_collect_cache_enabled` 와 `stt_recheck_collect_cache_enabled` 의 프로덕션 기본값은 `False` 로 완벽하게 유지되어 있으며, 현재는 opt-in 구조로만 동작함.
2. **NAS-off 상황의 제약**: NAS가 비활성 상태이므로 HeyDealer 180s 실제 미디어 백필과 WhisperKit persistent 모델의 실시간 디코더 ANE 가속/오류 정합성 검증이 불가능함.
3. **Promotion 리스크**: 실제 파형의 dynamic variance 검증이 생략된 채 synthetic fixture의 cache hit만 보고 기본값을 `True` 로 promotion하는 것은 Parity 깨짐 위험이 대단히 큼.
4. **결론**: **STT cache 기본값 promotion 슬라이스는 즉각 보류(HOLD) 권장**.
5. **대안 슬라이스 제안**: promotion 대신 settings load/parse 정합성 unit test를 강화하거나, `summarize_stage_variance.py` 를 활용한 memory-pressure/RSS stage variance의 dry-run 분석 도구를 보완하는 비파괴(read-only) 슬라이스 진행 추천.
6. **focused tests**: `tests/test_stage_variance_summary.py` 실행을 통한 로컬 통계 덤프 검증.
