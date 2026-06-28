DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after gap-delete policy 20260628

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE-to-legacy projection metadata preservation on dual-write operations" (NLE에서 레거시 자막 구조로 projection 할 때의 metadata 유실 차단 및 정합성 보존)**
2. **NLE/Taption 발전 기여 이유**:
   - NLE 의 target sequence level 에서 연산(merge/split/move)이 발생하더라도, 자막에 부착되어 있던 legacy metadata(스타일링 설정, 화자 레이블 등)가 훼손되지 않도록 strict metadata preservation rule 을 runtime dual-write core 에 장착하여 legacy 자막 툴셋과의 완벽한 양방향 호환을 완성시킴.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/nle_dual_write.py` : `_shadow_project_with_rows_and_provisional_markers`, `_retime_row` 등 (projection 및 legacy row metadata mapping 지점)
   - `core/project/nle_projection_parity.py` : `ProjectionParityReport` (프로젝션 정합성 수호)
4. **Focused Tests to add**:
   - `tests/test_nle_projection_metadata_preservation.py` [NEW] : caption move / merge / split 수행 전후로 editor row 내 `metadata` dictionary (e.g., `font_size`, `style`) 값이 그대로 복제 및 보존되는지 검증하는 integration test.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 자막 segments representation의 metadata mapping 변경이 수반되므로, HeyDealer first-180s benchmark (`heydealer_first_180s.mp4`) 기반 quality/segment-count regression validation 이 반드시 수행되어야 함.
6. **Rollback Risk**:
   - **리스크**: metadata deepcopy 누락으로 인해 style dictionary 의 runtime reference 가 공유되어 side-effect 가 나거나 parity check 가 어긋나는 리스크.
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
- `.agents/sentinel/handoffs/20260628-080426-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_CLASSIFICATION:
- status: accepted_with_scope_narrowed
- decision: Adopted the recommended AI Subtitle Studio slice as `NLE projection metadata preservation`.
- implementation_scope: deep-copy runtime dual-write projection row construction and prove existing product metadata preservation for caption move / merge / split.
- accepted_owner_files: `core/project/nle_dual_write.py`, `core/project/nle_operations.py`, `tests/test_project_nle_dual_write.py`, `tools/audit_nle_projection_metadata_preservation.py`, `tests/test_nle_projection_metadata_preservation_audit.py`.
- scope_narrowing: Did not add arbitrary legacy custom schema expansion, persisted NLE disk fields, UI/QML changes, STT/default-cache changes, App Store packaging, per-pixel NLE writes, or runtime undo/redo UI.
- proof_anchor: `output/manual_verification/latest/nle_projection_metadata_preservation_20260628/nle_projection_metadata_preservation.md`.
