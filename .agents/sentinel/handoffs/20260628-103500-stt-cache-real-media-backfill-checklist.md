DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio STT cache real-media backfill checklist

findings:
1. **HeyDealer 180s 캐시 백필 검증 절차 명세**: NAS 온라인 복구에 따라 덱스가 STT collect-cache write/hit benchmark 실행 시 반드시 충족해야 할 acceptance checklist 명문화.
2. **1단계: preflight 검증**:
   - `verify_reference_fixture_availability.py` 패스 필수 (`clipped_segment_count > 0`).
3. **2단계: cache_write 및 cache_hit 런 실행**:
   - 동일한 캐시 파일 경로(`stt_primary_collect.json`, `stt_recheck_collect.json`, `macro_response.json`)를 대상으로 1차 write 런 및 2차 hit 런을 동일 매개변수로 구동.
4. **3단계: Scored Acceptance Gate (최종 승인)**:
   - `evaluate_reference_benchmark_acceptance.py`를 실행하여 두 런 모두 `accepted=true` 획득 필수.
5. **4단계: Strict Subtitle Quality Gates (하드 가드)**:
   - `invalid_duration_count = 0` (0.3초 미만 / 비정상 자막 없음)
   - `non_monotonic_count = 0` (자막 시간 역전 없음)
   - `overlap_count = 0` (자막 시간 겹침 없음)
   - `last_end_within_duration_bound = true` (자막 끝이 영상 duration 180s 이내로 완벽히 바인딩됨)
6. **5단계: Cache Hit Efficiency Verification**:
   - Hit replay 런 메트릭에서 STT1/STT2/word collect cache 의 `provider_called`가 모두 `false`이고 `hit`가 `true`인지 검증.
   - `macro_response` 캐시의 `provider_call` 그룹 횟수가 `0` 인지 확인.
   - Concurrency `global_max_active <= 1` 유지.
7. **결론**: 위 5개 대분류 checklist를 100% 충족한 경우에만 collect-cache default promotion을 오너 리뷰 테이블에 상정할 수 있음.
