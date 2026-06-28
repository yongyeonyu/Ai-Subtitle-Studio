DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio cut-boundary fixture convention contact-sheet scout

findings:
1. **Frame Transition Contact-Sheet 현황**:
   - **현재 상태**: 2676/2677 mismatch 판단(neighbor conflict) 근거가 문자와 JSON 데이터로만 존재하여, 시각적 flow/edge 변화를 직관적으로 비교할 수 있는 썸네일 그리드 밀집 대비표(contact-sheet) 생성이 어려움.
   - **안전성 판정**: **안전함 (Accept 권장)**. 씬 디텍터 코어 및 실시간 비디오 재생 루프(UI)와 격리된 read-only 분석 CLI 도구 상의 리포트 생성 보강이며, 미디어 디코딩을 수행하지 않고 기존의 cached frame thumbnail 디렉토리에서 path만을 mapping해 덤프하므로 Deadlock/I/O 병목 위험이 전혀 없음.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame Transition Grid Contact-Sheet Generator" (컷 전환 프레임 그리드 밀집 대비표 생성기)**
3. **진단 대상 파일 (Owner Functions)**:
   - `tools/audit_cut_boundary_frame_semantics.py` : visual window JSON의 raw edge ratio 및 motion score를 HTML/Markdown grid contact-sheet layout으로 컴파일해 report artifact에 덤프하는 read-only output generator 함수 추가.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_frame_semantics_audit.py` : Contact-sheet Markdown table 빌드 시 syntax regex 및 image link file path mapping의 무결성 검사 테스트.
5. **추천 문서 (Documents)**:
   - `docs/VALIDATION.md` 에 이 contact-sheet 리포트 생성 및 target boundary visual alignment 수동 점검 방법 가이드라인 추가.

defer:
- **실제 컷 경계 preserved 알고리즘이나 오프셋 판별 tolerance 조정**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
