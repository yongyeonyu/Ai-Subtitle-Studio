DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after duration-bound 20260628

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE Gap delete dual-write sequence representation correction and parity check" (자막 간 빈 공간 삭제 dual-write 시 sequence list 동기화 정합성 및 parity 보정)**
2. **NLE/Taption 발전 기여 이유**:
   - gap delete 연산은 자막 타임라인을 당겨서(ripple) 공백을 없애는 핵심 NLE 편집 로직임. 이 슬라이스를 통해 dual-write projection parity가 gap 삭제 시에도 완벽하게 일치함을 검증하고 parity check error를 원천 차단하여 Taption style NLE editing의 신뢰도를 한 단계 도약시킴.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/nle_dual_write.py` : `apply_gap_delete_dual_write_pilot` (gap 삭제 연산 파일럿 처리부)
   - `core/project/nle_projection_parity.py` : `build_project_nle_projection_parity_report` (정합성 보고서 생성기)
4. **Focused Tests to add**:
   - `tests/test_nle_gap_delete_projection_parity.py` [NEW] : gap delete 발생 시 `NLEProjectState`와 legacy editor sequence segments 가 100% 동기화되고 `ProjectionParityReport`가 `ok=true` 임을 검증하는 integration test.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 자막들의 start, end 시각을 강제로 당기는(ripple) 편집 연산이므로, HeyDealer first-180s benchmark (`heydealer_first_180s.mp4`) 기반 quality/segment-count regression validation 이 반드시 수행되어야 함.
6. **Rollback Risk**:
   - **리스크**: gap delete 후 overlapping segment 나 invalid duration segment 가 잘못 발생하여 validation failure 가 일어나는 리스크.
   - **대책**: validation check failure 시 dual-write transaction 을 즉시 취소하고 `NLEUndoSnapshot`을 이용해 연산 이전의 NLE state 로 즉시 rollback.
7. **Acceptance Gate**:
   - HeyDealer 180s benchmark 실행 결과 `accepted=true`, `final_last_end_beyond_duration_bound=false`, SRT rows 의 타이밍 overlap 및 monotonic 정합성 깨짐 0건 통과.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-074703-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

Dex review:
- Accepted the owner path focus on `apply_gap_delete_dual_write_pilot`.
- Rejected the ripple premise: current AI Subtitle Studio gap delete removes the explicit gap row and preserves adjacent caption timing unless a separate owner-approved absorb/ripple operation is introduced.
- Implemented the narrower runtime contract as `remove_gap_row_no_ripple`, with operation/state/undo metadata, focused tests, audit evidence, and NAS HeyDealer first-180s regression proof.
