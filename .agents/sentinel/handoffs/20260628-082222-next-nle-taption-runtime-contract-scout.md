DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after projection metadata preservation 20260628

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE confirmed cut marker point-evidence projection to legacy editor context" (NLE 확정 컷 경계 포인트를 레거시 에디터의 clip-span mapping 없이 안전하게 1-point evidence로 투영 및 보존)**
2. **NLE/Taption 발전 기여 이유**:
   - 컷 편집 경계를 legacy structure에 투영할 때 복잡한 clip-span 간의 offset 계산을 타지 않고, 단일 absolute frame position evidence 로 통일시켜 dual-write 및 projection의 속도와 정합성을 비약적으로 높이고 edit flow의 무결성을 수호함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/project_context.py` : `project_cut_boundary_provisional_segments`, `_shadow_project_with_rows_and_provisional_markers` 등 (cut boundary 투영부)
   - `core/project/nle_dual_write.py` : `_shadow_project_with_rows_and_provisional_markers` (NLE state 투영)
4. **Focused Tests to add**:
   - `tests/test_nle_cut_boundary_projection_isolation.py` [NEW] : NLE edit dual-write 발생 시 provisional cut boundaries(프레임 2766, 2676 등)가 legacy clip-span mapping의 갱신/왜곡 없이 absolute point-evidence 로 투영되는지 확인하는 integration test.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 자막 segments representation의 metadata mapping 변경이 수반되므로, HeyDealer first-180s benchmark (`heydealer_first_180s.mp4`) 기반 quality/segment-count regression validation 이 반드시 수행되어야 함.
6. **Rollback Risk**:
   - **리스크**: point-evidence 투영 시 레거시 playhead-fit logic 이 frame boundary 를 drop 하여 playhead jump 가 어긋날 위험.
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
- `.agents/sentinel/handoffs/20260628-082222-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_ACCEPTED_WITH_CORRECTION
- 채택 slice: `NLE confirmed cut marker point-evidence projection to legacy editor context`.
- 교정: scout의 `2677` 언급은 최신 AI Subtitle Studio 고정 기준과 맞지 않아 `2676`으로 정정한다. 이번 구현/감사는 `2766,2676`만 target frame으로 사용한다.
- 적용 범위: `core/project/nle_dual_write.py` marker projection sanitizer, focused dual-write regression, `tools/audit_nle_cut_marker_point_projection.py`.
- 유지 guardrail: persisted NLE disk fields, per-pixel writes, UI/QML/GPU, STT/default cache, visual threshold relaxation, App Store packaging은 이번 slice 밖이다.
