DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: fixed cut-boundary frame 2766 detector-evidence scout

findings:
1. **2766 Current Evidence (시각적 정량 지표)**:
   - **프레임 2766 (pair 2765->2766)**: score `2.059` (임계치 `40.0`), pixel_ratio `0.029392` (임계치 `0.18`), motion_jump `0.0` (임계치 `6.0`), region_hits `0` (임계치 `2`).
   - **판정**: edge_gray_fast_gate 기준 모든 씬 전환 감지 메트릭이 임계치 미달로 `candidate_detected=false` 판정.
2. **Likely Cause (원인)**:
   - 프레임 2765->2766 구간은 시각적 edge 및 contrast 변화가 매우 미미하고 모션 변화(motion_jump)가 거의 없는 static/low-contrast 컷 성격을 띰.
   - 이로 인해 씬 디텍터가 전환점으로 감지하지 못하고, 자막 timing consensus의 파괴를 방지하기 위한 `preserved_only` 우회 로직에 의존하여 `frame_preserved=true` 상태로 우회 유지됨.
3. **Safe Next Dex Slices (차기 Dex 구현 후보)**:
   - **후보 1 (추천)**: **"Fixed Cut-Boundary Frame 2766 Preserved-Only Regression Test Suite" (프레임 2766 Preserved-Only 회귀 테스트 구축)**
     - 2766 프레임이 감지 점수(score 2.059) 미달이어도, `preserved_only` 분기를 타고 최종 boundary set에 성공적으로 병합되는 비파괴 회귀 테스트(`tests/test_cut_boundary_fixture_2766_2676.py` 등) 신설.
   - **후보 2**: **"Fixed Cut-Boundary Frame 2766 Visual Contrast Analyzer Diagnostics" (프레임 2766 저대비 구간 edge_ratio 분석 진단 도구)**
     - low-contrast 구간에서 edge filter limit를 안전하게 측정하여 transition score가 drop되는 원인을 debug log에 상세히 출력하는 read-only 진단 기능 보강.
4. **Blocked Changes (차단 변경 요건)**:
   - **디렉터 core threshold 완화**: score threshold 하향(40.0 -> 2.0) 시 false positive 가 폭발하여 전체 자막 품질이 drift되므로 차단(blocked).
   - **STT/모델 변경, UI/QML, App Store 작업, persisted NLE fields 구조 변경**: 일체 Defer/Blocked.

defer:
- **실제 씬 디텍터 core의 default threshold 파라미터 일괄 하향 (score 40.0 -> 2.0 등)**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-141000-cut-boundary-2766-detector-scout.md` 파일 내용 및 index 맵핑 상태 점검.
