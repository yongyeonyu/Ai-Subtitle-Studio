DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NAS-on STT regression gate scout 20260628

findings:
1. **HeyDealer 180s Real-Media Benchmark 핵심 검증 필드**:
   - **Acceptance 필드 (품질/정합성)**:
     - `accepted` (최종 합치Verdict: bool)
     - `quality_score` (품질 점수), `text_similarity` (텍스트 유사도), `timing_drift_sec` (시간 편차)
     - `final_last_end` 대 `media_duration` (영상 길이 초과 예외 감지: `final_last_end_beyond_duration_bound` 여부)
   - **Latency 필드 (성능/오버헤드)**:
     - STT1 / STT2 / Word Precision / Subtitle Postprocess 각 단계별 `elapsed_sec`
     - `pipeline_elapsed_sec` (전체 파이프라인 누적 실행 시간)
   - **Stability 필드 (자원/무결성)**:
     - `peak_rss_bytes` (최고 메모리 점유량)
     - `final_invalid_count` / `final_non_monotonic_count` / `final_overlap_count` (반드시 모두 `0`이어야 함)
2. **Owner Review Gate & Decision Criteria (오너 판정 기준)**:
   - **Accepted 판정**: `evaluate_reference_benchmark_acceptance.py` 실행 결과 최종 `accepted=true` 이고, 180초 영상 기준 자막 무결성(`0/0/0`)과 duration bound 초과가 전혀 없는 상태에서만 릴리즈 promotion 준비로 판정.
   - **Blocked 판정**: `accepted=false` 이거나, `final_last_end` 초과(duration bound failure), 혹은 sub-0.3s 자막 행 누락 등 strict acceptance rules 중 하나라도 실패할 경우 Blocked 판정.
   - **Cache Default Promotion 규칙**: `stt_primary_collect_cache_enabled` 및 `stt_recheck_collect_cache_enabled` 는 오너의 명시적 승인 전까지 default True로 promotion하지 않고 `false`(opt-in) 상태를 철저히 유지함.

defer:
- **STT 캐시의 default promotion (True 설정)**: Defer 함.
- **자막 품질 게이트의 수치적 완화**: Defer 함.
- **QML/UI 변경 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-151600-stt-nas-on-regression-gate.md` 파일 내용 및 index 맵핑 상태 점검.
