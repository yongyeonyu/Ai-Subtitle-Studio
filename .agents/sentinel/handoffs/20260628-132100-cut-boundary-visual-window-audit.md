DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio cut-boundary visual window audit scout

findings:
1. **fixed fixture +/-N window visual transition 랭킹 진단 제안**:
   - **현재 상태**: 2766/2677 프레임 주변에서 시각적 scene change가 가장 강하게 발생했는지를 정량 평가하기 위한 윈도우 스캔 랭킹 도구가 부재함.
   - **안전성 판정**: **안전함 (Accept 권장)**. 자막 생성 코어나 UI 렌더링에 일체 간섭하지 않는 read-only 진단 CLI 도구 및 단위 테스트이므로 오너 승인 없이 안전하게 진행 가능.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame 2766/2677 Visual Transition Window Audit Tooling" (프레임 2766/2677 시각 전환 윈도우 진단 도구)**
3. **진단 대상 파일 (Owner Functions)**:
   - `tools/verify_cut_boundary_source_fps_scout.py` : `--window-size N` 매개변수와 지정 프레임들을 기반으로 주변 프레임들의 `pixel_ratio`, `edge_ratio` delta score를 랭킹하여 Markdown/JSON 파일로 덤프하는 read-only report generator 함수 추가.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_fixture_2766_2677.py` : Mock window score list를 활용해 target 프레임이 최상위(Rank 1) transition으로 올바르게 랭크되는지 로직 검증.
5. **추천 문서 증거 (Documents)**:
   - `docs/VALIDATION.md` 에 `verify_cut_boundary_source_fps_scout.py` 의 윈도우 랭킹 덤프 명령 및 사용 예시 명세 추가.

defer:
- **실제 cut-boundary score threshold 값의 완화/조정**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
