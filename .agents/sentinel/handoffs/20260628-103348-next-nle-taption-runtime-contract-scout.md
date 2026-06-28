DEX_READY_FOR_REVIEW
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE/Taption runtime contract scout after selection sync validation

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE project load asset relink and verification parity" (프로젝트 오픈 후 미디어 relink 시점의 NLE sequence 및 editor track metadata validation 검증 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 프로젝트 오픈 시 미디어 파일 경로가 변경되었을 때 relink 처리하는 로직이 탑재되어 있음. 그러나 미디어를 relink 할 때 NLE state 의 `Sequence`, `Clip`, `Track` 에 담긴 duration/fps 정보와 editor 의 track metadata 간에 dynamic verification parity가 틀어지거나 preview cache 가 유실될 위험이 존재함. relink 완료 후에 NLE state 와 editor track 정보가 100% 일치함을 보장하는 validation contract 가 필요함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/project_assets.py` : `resolve_project_asset_path`, `hydrate_project_text_asset_cache` (미디어 relink 및 캐시 수화 지점)
   - `core/project/project_context.py` : `project_media_files` (NLE context 투영)
4. **Focused Tests to add**:
   - `tests/test_nle_relink_verification.py` [NEW] : 미디어 파일 relink 시점 전후로 NLE sequence `Clip` 및 `Track` 의 duration/fps 가 editor state 의 track metadata 와 일관성을 유지하고, `passed=true` 상태로 verification parity가 완벽 일치하는지 assert하는 unit test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_relink_parity.py` [NEW] : static 분석을 통해 relink path 상에서 NLE state 와 editor metadata 의 정보 불일치로 인한 오작동이 없는지 정적 감사 보고서 작성.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 로딩/relink 시점의 validation 검증이므로 HeyDealer benchmark validation 이 불필요함.
7. **Rollback Risk**:
   - **리스크**: relink 검증 실패 시, 프로젝트 로드 및 미디어 교체가 실패하는 크리티컬 UI block이 발생할 리스크.
   - **대책**: relink verification failure 시 safe fallback(이전 original path 유지)으로 복구하도록 exception handler를 내장하고, validation check를 warning level 로 우회하여 rollback.
8. **Acceptance Gate**:
   - `tests/test_nle_relink_verification.py` 의 unit test `failed_count=0` 통과 및 mock trace query event 100% parity 달성.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-103348-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
