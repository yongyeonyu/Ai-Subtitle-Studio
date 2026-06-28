DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio direct SRT versus linked project NLE precedence scout 20260628

findings:
1. **이미 있는 coverage**:
   - `ui/editor/editor_project_open_native.py` : 직접 SRT 오픈 시 project metadata와 SRT 자막을 병합하는 `merge_srt_segments_with_project_metadata` 가 이미 구현되어 있음.
   - `core/project/project_assets.py` : 프로젝트 로드 시 외부 `.srt` 파일이 존재하면 파싱하여 editor segments 로 복원하는 `load_external_subtitle_segments` 가 기장착됨.
2. **빠진 direct SRT/NLE precedence case (정합성 위험)**:
   - **위험**: linked project 파일이 연동되어 있는 상태에서 사용자가 더블클릭 등으로 직접 SRT 파일을 강제 새로고침(refresh open)할 때, linked project 의 `NLEProjectState` 캐시 세그먼트 데이터가 우선권을 쥐고 새로 들어온 SRT 의 타이밍/텍스트를 구버전 데이터로 덮어써버려 로드 결과가 왜곡되는 리스크.
   - **해결 규약**: 직접 오픈된 SRT 의 타이밍/텍스트(`start`, `end`, `text`)가 linked project 및 NLE-derived metadata 에 대해 무조건 최우선권(direct SRT precedence)을 획득하도록 규약 강제.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `ui/editor/editor_project_open_native.py` : `merge_srt_segments_with_project_metadata` (SRT 자막의 타이밍/텍스트 불변 보존 및 project metadata 만의 우회 보완 강제)
   - `ui/editor/editor_lifecycle.py` : `_open_subtitle_segments_in_editor` (SRT 직접 오픈 시 NLE cache 우선순위 바이패스 제어)
4. **Focused test/audit 제안**:
   - `tests/test_editor_srt_open_refresh.py` [NEW] : linked project 에 다른 내용의 자막이 보관되어 있어도, 직접 SRT 로드 명령을 수행하면 최신 SRT 디스크 파일의 타이밍/텍스트가 최종 editor 와 NLE state 에 정상 반영 및 덮어쓰기 완료되는지 검증하는 integration test.
   - `tools/audit_editor_srt_open_precedence.py` [NEW] : static 분석을 통해 metadata merge helper가 srt segments의 timing/text keys(`start`, `end`, `text`)를 linked project 데이터로 덮어쓰지 않고 preserve하는지 감사하는 스크립트.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 UI/Editor 로딩 타임의 파일 오픈 우선순위 제어 로직이므로 HeyDealer benchmark validation 이 불필요함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-090453-srt-precedence-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_CLASSIFICATION:
- verdict: ACCEPTED
- accepted scope: direct SRT open must keep SRT timing/text as the source of truth over linked project or runtime NLE-derived subtitle rows.
- implemented owner path: `ui/editor/editor_project_open_native.py::open_project_segments_in_editor` now syncs runtime `NLEProjectState` from the exact direct SRT editor rows with `last_editor_sync_source=direct_srt_open` and `direct_srt_precedence_contract=srt_timing_text_wins`.
- evidence: `output/manual_verification/latest/direct_srt_precedence_contract_20260628/direct_srt_precedence_contract.md`; NAS current-head regression `output/manual_verification/latest/direct_srt_precedence_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`
- deferred scope: UI/layout behavior, persisted NLE disk fields, STT/generation policy, App Store packaging, DMG behavior, and per-pixel NLE writes remain unchanged.
