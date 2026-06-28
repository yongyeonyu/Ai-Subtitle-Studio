DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio fixed cut-boundary fixture proof scout

findings:
1. **fixed fixture 명령 실행 가능 여부 검토**:
   - **현재 상태**: iCloud 동기화 여부나 NAS 상태에 따라 `/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4` 물리 파일이 다운로드되지 않은 누락(missing) 상태일 위험이 매우 큼.
   - **결과**: preflight 단계에서 `verify_cut_boundary_source_fps_scout.py` 가 missing file 에러로 차단될 우려가 있음.
2. **테스트 부재 검토**:
   - 컷 경계 `2766` 및 `2677` 프레임 스플릿/스냅 무결성을 regression guard하기 위한 `tests/test_cut_boundary_fixture_2766_2677.py` 가 아예 부재(missing) 상태임.
3. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame 2766/2677 Mock integration Test Suite 신설"**
4. **선정 사유 및 안전성**:
   - **안전성**: 실제 디바이스 상의 대용량 비디오 파일 유무에 종속되지 않고, Mock FPS `60000/1001` 및 target frames `2766/2677` 부근의 timing boundaries 계산 정합성 및 split/snap 분기 처리를 에뮬레이션하여 검증하는 비파괴 테스트 스위트이므로 오너 승인 없이 매우 안전하게 수행 가능.
5. **focused tests**:
   - `tests/test_cut_boundary_fixture_2766_2677.py` [NEW]
   - `tools/verify_cut_boundary_source_fps_scout.py` (mock test run 옵션 보강)

defer:
- **실제 FFmpeg/OpenCV scene change detection 파라미터 값 변경**: Defer 함.
- **QML/UI 전환 시도**: 일체 Defer 함.
