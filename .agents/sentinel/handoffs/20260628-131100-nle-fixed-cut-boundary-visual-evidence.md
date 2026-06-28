DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio fixed cut-boundary visual evidence scout

findings:
1. **fixed fixture 2766/2677 Visual Evidence 현황**:
   - **프레임 2766**: pixel_ratio `0.029392`, edge_ratio `0.048021`, score `2.059`
   - **프레임 2677**: pixel_ratio `0.029288`, edge_ratio `0.046615`, score `1.997`
   - **결과**: `candidate_detected`는 `false`이나, fast gate 기준 score와 ratios가 임계 수준에 도달하여 `frame_preserved=true` 및 `pair_passed=true` (basis: `"preserved"`) 처리가 보장되는 구조.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame 2766/2677 Visual Evidence Checker Integration" (프레임 2766/2677 시각 메트릭 조건 통합 검사기)**
3. **진단 대상 파일 (Owner Functions)**:
   - `core/cut_boundary_auto_utils.py` 및 `core/visual_cut_jump.py` : `score_visual_cut_pair` 함수 내 visual transition delta 메트릭 산출 및 `frame_preserved` 판별 분기.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_fixture_2766_2677.py` : `source_fps_scout.json` 의 metrics 데이터를 mock payload로 활용하여 비파괴 regression test 및 Parity 수립.
5. **아티팩트 (Artifacts)**:
   - `output/manual_verification/latest/nle_slice2_source_fps_scout_20260627/source_fps_scout.json` (Parity 검증용 static fixture)

defer:
- **실제 FFmpeg/OpenCV scene change detection 파라미터 값 변경**: Defer 함.
- **STT2/word precision skip, 모델 다운그레이드**: Defer 함.
- **QML/UI 및 App Store 관련 빌드 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
