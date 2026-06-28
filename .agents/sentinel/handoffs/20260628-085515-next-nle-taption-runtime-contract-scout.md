DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after relink preview cache contract 20260628

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"Save/export projection NLE trace event contract validation" (프로젝트 저장/내보내기 시점의 NLE state 역투영(projection) trace events 검증 도구 및 테스트 보강)**
2. **NLE/Taption 발전 기여 이유**:
   - 디스크 세이브 및 SRT 내보내기 시점에 NLE memory state의 소거 및 legacy target metadata 보존 이력이 trace logger를 통해 완벽히 투명하게 모니터링/기록됨을 보장하여, 협업 NLE 파이프라인에서 데이터 정합성 충돌의 원인 분석을 100% 추적 가능하게 도약시킴.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/project_io.py` : `_project_payload_for_disk` (저장 시 strip 및 serialization 지점)
   - `core/runtime/trace_logger.py` (비동기 trace event 로깅 엔진)
4. **Focused Tests to add**:
   - `tests/test_project_io_write_trace_validation.py` [NEW] : `project_io.write` 실행 시, `strip_unapproved_nle_persistence_fields` 가 event log `"project_io_write"` 와 함께 `stripped_runtime_key_count` 정보를 trace logger 에 남기는지 mock trace queue assertion으로 증명.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 비파괴 로깅/진단 검증 작업이므로 HeyDealer benchmark validation 이 불필요함.
6. **Rollback Risk**:
   - **리스크**: trace log 기록 실패 시, 핵심 비즈니스 로직(save)에 thread block 이나 crash side-effect 를 전파할 리스크.
   - **대책**: trace event 로깅은 항상 `try-except` wrapper 로 감싸 best-effort 로 동작하게 보장하며, 로깅 실패가 save process 에 미세한 영향이라도 줄 경우 로깅 wrapper를 bypass(disabled) 상태로 즉시 rollback.
7. **Acceptance Gate**:
   - `tests/test_project_io_write_trace_validation.py` 의 unit test `failed_count=0` 통과 및 mock trace query event 100% parity 달성.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-085515-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_CLASSIFICATION:
- verdict: DEFER
- reason: 대표님이 NAS를 켜셨다고 알려 주신 직후라, 다음 실제 작업은 AI Subtitle Studio active gate의 HeyDealer 180s NAS 실매체 preflight/benchmark/acceptance/timeout refresh가 우선입니다. 제안된 save/export projection trace contract는 다음 NLE/Taption runtime slice 후보로 유지하되, 이번 커밋에는 적용하지 않습니다.
- accepted_scope_now: physical handoff reviewed, project label verified as AI Subtitle Studio, stale watchdog probe index cleanup required.
