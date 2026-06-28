DEX_READY_FOR_REVIEW
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next non-duplicate NLE/Taption segment-editing scout

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE subtitle neighbor collision resolution and boundary clip validation" (자막 경계 조절/이동 시 인접 자막과의 collision(충돌)을 방지하고 boundary clip validity를 진단하는 검증 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 자막 세그먼트의 start/end 경계를 조작(resize)할 때, 인접한(neighboring) 자막 영역을 침범하여 overlapping이 생기는 collision 정합성 오류가 발생할 수 있음. NLE state 레벨에서 이 collision 상황을 사전에 감지하고, boundary limit을 dynamic clamping하여 user edit flow가 validation fail 상태로 빠지지 않도록 방어하는 validation contract 가 필요함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/nle_project_state.py` : `validate_segments` (NLE state collision validation)
   - `ui/editor/ux/editor_timeline_segment_merge.py` : `_on_segment_resize` (또는 timeline boundary 조작 시점)
4. **Focused Tests to add**:
   - `tests/test_nle_neighbor_collision_validation.py` [NEW] : 자막의 start/end를 인접 자막 너머로 과도하게 드래그하거나 연산했을 때, NLE state 의 dynamic boundary check가 collision을 방지하고 `passed=true` 상태로 validation parity가 완벽 일치하는지 assert하는 unit test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_neighbor_collision.py` [NEW] : static 분석을 통해 boundary resize flow 내에서 neighbor collision 검사가 정상 작동하여 overlap error가 철저히 사전 차단되어 있는지 정적 감사 보고서 작성.
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
- `.agents/sentinel/handoffs/20260628-110359-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
