DEX_READY_FOR_REVIEW
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio neighbor collision validation scout

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE segment resize and move neighbor overlap prevention guard parity" (자막 세그먼트의 resize(크기조절) 및 move(이동) 이벤트 시점에 인접 자막과의 micro-overlap collision을 방지하는 dynamic clamping 검증 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - timeline segment 의 경계를 마우스로 드래그하여 조절할 때, 인접(neighboring) 자막 카드를 침범하여 overlapping이 발생하는 collision 정합성 오류가 존재할 수 있음. NLE state 레벨에서 이 드래그 완료(commit) 시점 뿐 아니라 드래그 진행 중에도 boundary limit을 dynamic clamping하여, duplicate key 및 validation fail 오류가 나지 않도록 엄격하게 방어하는 validation contract 가 필요함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/nle_project_state.py` : `validate_segments` (NLE state dynamic boundary check)
   - `ui/editor/ux/timeline_canvas_editing.py` (또는 timeline drag-resize 믹스인)
4. **Focused Tests to add**:
   - `tests/test_nle_neighbor_collision_validation.py` [NEW] : timeline resize 및 move 드래그 완료 시점에 start/end 가 인접 자막의 영역을 1ms라도 침범(overlap)하지 않고, dynamic boundary clamp 가 올바르게 작동하여 `passed=true` 상태로 validation parity가 완벽 일치하는지 assert하는 unit test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_neighbor_collision.py` [NEW] : static 분석을 통해 timeline segment drag-resize/move flow 내에서 neighbor collision dynamic clamping이 정상 작동하여 overlap error가 철저히 사전 차단되어 있는지 정적 감사 보고서 작성.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 UI 에디터 조작 시점의 boundary collision 검증이므로 HeyDealer benchmark validation 이 불필요함.
7. **Rollback Risk**:
   - **리스크**: collision 감지 실패로 인해 자막 timing overlap이 디스크에 세이브되어 추후 load/export 시점에 fatal project crash 가 발생할 리스크.
   - **대책**: collision 이 감지될 경우 start/end 값을 강제로 이전 valid state 로 rollback하고, metadata check validation을 warning level 로 우회하여 방어.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-112236-neighbor-collision-validation-scout.md` 파일 내용 및 index 맵핑 상태 점검.
