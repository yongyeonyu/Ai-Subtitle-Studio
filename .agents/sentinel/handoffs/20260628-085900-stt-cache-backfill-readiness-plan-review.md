DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio STT cache backfill readiness plan review

findings:
1. **분석 제안 검토**: NAS-off 상태에서 `stt_cache_backfill_readiness` 리포트에 `next-run command plan`, `forbidden substitute`, `owner review gate` 가이드라인 명세를 추가하는 보강 방향 검토 결과.
2. **Next-run command plan**:
   - **충돌 여부**: 없음. NAS가 온라인 상태로 복구되는 즉시 덱스가 사용할 수 있는 HeyDealer 180s 명령(write/hit replay) 템플릿을 추가하는 것은 실무 latency trim 로드맵과 완벽하게 정렬됨.
3. **Forbidden substitute**:
   - **충돌 여부**: 없음. STT2 생략, LLM 축소 등 품질 훼손 최적화 기법을 금지(forbidden)하는 Hard Rule 경고 문구를 진단서 상에 명문화하여 가이드라인 강화.
4. **Owner review gate**:
   - **충돌 여부**: 없음. 캐시 100% hit 여부와 별개로 `evaluate_reference_benchmark_acceptance.py` 의 strict duration-bound/overlap 0 통과 검증이 선행되어야 함을 가드로 각인.
5. **결론**: 제안된 3대 강화 요건은 active queue 및 hard rules와 전혀 충돌하지 않으므로 **차기 비파괴 진단 보강 슬라이스로 적극 Accept 권장**.
6. **추천 테스트**:
   - `tests/test_stt_cache_backfill_readiness.py` (readiness schema 검증)
7. **수정 불가 경계**:
   - `core/audio/media_processor_transcribe.py` 내 캐시 기본값(False 유지).
   - 실제 미디어 파일이 확보되기 전까지 STT 캐시 promotion 금지 경계 유지.
