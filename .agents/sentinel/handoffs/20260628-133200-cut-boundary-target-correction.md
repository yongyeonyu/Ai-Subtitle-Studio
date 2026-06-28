DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio fixed cut-boundary target correction scout

findings:
1. **Target Correction 타당성 검토**:
   - **시각적 증거**: expected `2676 -> 2677` (mean delta `2.38`) 대비 neighbor `2675 -> 2676` (mean delta `72.84`)가 30배 이상 강력한 scene change를 보임.
   - **결정**: QA target 기준점을 `2677`에서 `2676`으로 정정(correct)하는 것이 frame-semantics 정합성 및 시각적 진실에 부합함.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Target Correction to Frame 2676 Implementation" (컷 경계 타겟 프레임 2676 정정 구현)**
3. **진단 대상 파일 (Owner Files & Functions)**:
   - `tools/audit_cut_boundary_fixture_convention.py` : 기대 target frame 목록 상수 및 reference mapping에서 `2677`을 `2676`으로 정정.
   - `core/cut_boundary.py` (또는 `core/cut_boundary_auto_scan.py`): target correction 보정 offset logic을 check-in.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_fixture_2766_2676.py` [NEW] : 기존 부재했던 2677 fixture test 신설 안을 보정된 프레임 `2676` 기준으로 명세하여 생성 및 regression guard 수립.
   - `tests/test_cut_boundary_visual_window_audit.py` : expected target 2676 검증 업데이트.
5. **추천 문서 업데이트 (Documents)**:
   - `NLE_Action.md`, `test_case.md`, `docs/VALIDATION.md` 의 fixed target 지칭부를 `2677` -> `2676` 으로 일괄 정정 기술.

defer:
- **실제 씬 디텍터 threshold 값 임의 완화**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
