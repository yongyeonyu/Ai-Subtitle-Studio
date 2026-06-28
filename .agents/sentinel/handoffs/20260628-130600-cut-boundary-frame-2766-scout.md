DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio fixed cut-boundary frame 2766 detector-evidence scout

findings:
1. **프레임 2766 preserved_only 통과 원인 규명**:
   - **현황**: target frame `2766` 은 `pixel_ratio=0.029392` (threshold: `0.18`), `score=2.059` (threshold: `40.0`)으로 현 씬 전환 감지기의 임계 기준치에 도달하지 못해 `candidate_detected=false` 로 판단됨.
   - **결과**: `verify_cut_boundary_source_fps_scout.py` 에 기재된 `edge_gray_fast_gate` 의 default strict threshold 조건 하에서 감지(detected)에 실패하고, 오직 historical alignment 상의 `preserved_only` 우회 룰에 의해서만 보존(preserved)됨.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame 2766 Detector-Evidence Robustness Validation" (프레임 2766 디텍터 감지력 향상을 위한 mock 검증기 수립)**
3. **진단 대상 파일 (Owner Functions)**:
   - `core/visual_cut_jump.py` : edge ratio 산출 및 canny filter (`_safe_canny` 등)에서 contrast가 낮은 2766 프레임 구간에 dynamic edge gradient offset을 보정하여 transition score를 안전하게 견인하는 helper 로직 검사.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_fixture_2766_2676.py` [NEW] : 2766 metrics(score 2.059)가 target tuning parameter 하에서 씬 전환(`detected=true`)으로 완벽히 정합 판정되는지 mocking 통합 테스트 구축.
5. **추천 문서 (Documents)**:
   - `docs/VALIDATION.md` 에 low-contrast target 2766 의 detector tuning 방법 설명 보강.

defer:
- **실제 씬 디텍터 core의 default threshold 파라미터 일괄 하향 (score 40.0 -> 2.0 등)**: false positive 자막 split 오작동이 다량 발생하므로 Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
