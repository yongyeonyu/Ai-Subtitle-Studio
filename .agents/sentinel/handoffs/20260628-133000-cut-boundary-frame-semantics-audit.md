DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio cut-boundary frame-semantics audit scout

findings:
1. **2676/2677 Frame Semantics Mismatch 현황**:
   - **프레임 2677**: preserved 컷 경계 (score `1.997`, edge_ratio `0.046615`)
   - **인접 프레임 2676**: detected 컷 경계 (score `71.932`, edge_ratio `0.58431`)
   - **분석**: 실제 강한 시각 전환은 `2676`에서 발생했으나, `2677`이 preserved로 고정되어 미세한 시간 차(mismatch)가 보존됨.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Fixed Cut-Boundary Frame-Semantics Mismatch Audit Artifact Freeze" (프레임 2676/2677 시각적 컷 불합치 진단 아티팩트 고정)**
3. **진단 대상 파일 (Owner Functions)**:
   - `tools/audit_cut_boundary_visual_window.py` : transition score 및 edge ratio의 semantic disparity 정량 분석(SSD delta 등) 결과를 markdown report artifact에 static template 분석 필드로 박제하는 보강.
4. **추천 테스트 (Tests)**:
   - `tests/test_cut_boundary_visual_window_audit.py` : `test_verify_semantics_mismatch_static_fixtures` 를 추가하여 mock 데이터 상의 2676 vs 2677의 ssim/motion 점수 격차가 정상 판단(rank 및 score parity)을 이끌어내는지 회귀 검증.
5. **추천 문서 (Documents)**:
   - `docs/VALIDATION.md` 에 해당 audit tool의 2676/2677 mismatch 검증 예시 및 커맨드 명세를 고정 기술.

defer:
- **실제 컷 경계 preserved 알고리즘이나 오프셋 판별 tolerance 조정**: 자막 timing consensus의 regression 위험이 매우 크므로 Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.
