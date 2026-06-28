DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE/Taption runtime owner safe slice scout

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE roughcut sidecar file write compatibility check and validation parity" (러프컷 내보내기 시점의 sidecar metadata.json/txt 파일 쓰기가 NLE sequence state 와 dual-write projection validation을 방해하지 않고 비파괴적 병행 보존되는 호환성 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 러프컷 편집 시 metadata.json 등의 sidecar 파일들을 디스크에 write 하는 로직이 존재함. 그러나 NLE runtime active 상태에서 이 sidecar 파일들을 쓰거나 읽을 때, NLE state 의 sequence layout 과 legacy target metadata 간에 dynamic projection validation parity가 오작동하여 edit flow 가 중단될 정합성 위협이 존재함. sidecar write 가 NLE 정합성을 침해하지 않도록 보장하는 비파괴 호환성 규약(contract) 수립을 제안함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/roughcut.py` : `build_edit_decisions`, `retime_subtitles_for_edl` (roughcut retiming 및 sidecar 생성부)
   - `core/project/nle_snapshot.py` : `build_concat_render_plan_from_snapshot` (NLE 스냅샷 연동)
4. **Focused Tests to add**:
   - `tests/test_nle_roughcut_sidecar_write_compat.py` [NEW] : NLE active sequence 에서 roughcut sidecar (`edl_to_dict`) 내보내기를 수행했을 때, NLEState의 undo snapshot sequence가 깨지지 않고 legacy sidecar metadata 가 perfect roundtrip parity 를 유지함을 증명하는 integration test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_roughcut_sidecar_compat.py` [NEW] : static 분석을 통해 roughcut sidecar write 로직이 NLE state 를 overwrite 하거나 validation error 를 발생시키는 flow 를 차단하고 있는지 정적 검증하고 `passed=true` 보고서 작성.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 러프컷 파일 쓰기 호환성 검증 규약이므로 HeyDealer benchmark validation 이 불필요함.
7. **Rollback Risk**:
   - **리스크**: sidecar JSON 파싱 에러 발생 시, NLE runtime engine 이 crash 될 리스크.
   - **대책**: JSON parsing 은 항상 `try-except` fallback(legacy default dictionary)으로 방어하며, sidecar matching 오작동 감지 시 NLE state snap을 disabled 상태로 즉시 rollback.
8. **Acceptance Gate**:
   - `tests/test_nle_roughcut_sidecar_write_compat.py` 의 unit test `failed_count=0` 통과 및 mock trace query event 100% parity 달성.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-093842-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
