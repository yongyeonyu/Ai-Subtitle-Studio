DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE/Taption runtime contract scout after roughcut sidecar

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE selection sync and edit state validation parity" (NLE sequence segment 선택/동기화 시점에, core editor 와 NLE state 간 edit lock 상태 및 sync sequence 무결성을 진단하는 검증 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 에디터가 자막 행을 reload 할 때 NLE state 의 active index 와 legacy editor 의 QTextCursor focus-block 간의 selection sync(선택 동기화)가 일어남. 그러나 dynamic validation lock이 걸려있거나 merge/split 연산 수행 직후 selection sync가 틀어져 엉뚱한 자막 행이 활성화되는 씽크 불일치 에러를 방지하기 위해, reload 완료 시점에 NLE state와 editor state 간 selection index parity(동기화 정합성)를 단언하고 assert하는 안전한 validation contract 가 필요함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `ui/editor/editor_segments_reload.py` : `_reload_segments_apply_rows` (에디터 reload 및 selection 복구 지점)
   - `core/project/project_context.py` : `project_segments_to_editor` (NLE state segments 투영)
4. **Focused Tests to add**:
   - `tests/test_nle_selection_sync_validation.py` [NEW] : NLE active sequence segment index 와 editor block select sync 완료 후, 양방향 index mapping 이 `passed=true` 상태로 완벽 일치하는지 assert하는 unit test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_selection_sync.py` [NEW] : static 분석을 통해 selection sync event path 상에서 validation error 나 sync loop recursion (무한 루프) 부작용이 없는지 정적 감사 보고서 작성.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 로딩/동기화 시점의 selection index mapping 검증이므로 HeyDealer benchmark validation 이 불필요함.
7. **Rollback Risk**:
   - **리스크**: index mapping mismatch 발생 시, UI block 이나 index out-of-range crash 가 날 리스크.
   - **대책**: validation assertion은 `ValueError` 를 catch 하여 safe fallback index 0으로 복구하도록 exception handler를 내장하고, 최악의 경우 sync lock logic을 disable 상태로 rollback.
8. **Acceptance Gate**:
   - `tests/test_nle_selection_sync_validation.py` 의 unit test `failed_count=0` 통과 및 mock trace query event 100% parity 달성.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-101805-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
