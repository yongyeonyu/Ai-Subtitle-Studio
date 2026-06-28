DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio preserved marker policy scout 20260628

findings:
1. **Preserved Marker Policy 검증 현황**:
   - **프레임 2766**: `detected_any_mode=false` 및 `classification="weak_visual_change_not_threshold_candidate"`.
   - **분석**: 어떤 씬 검출 모드(fast4, cross5, full9)와 해상도(320~1920)를 조합해도 transition score 최고점(`3.812`)이 임계치(`40.0`)에 닿지 못하므로, 2766은 detector threshold 완화 튜닝 대상이 아님을 증명함.
   - **결론**: 프레임 2766은 씬 디텍터 튜닝이 아닌, `preserved frame-grid/marker evidence` (고정 마커/그리드) 정책으로 안전하게 박제(lock)하는 것이 유일하고 타당함.
2. **입력 Artifact 확인 정책 필드**:
   - `runtime_change_allowed`: `false` (디텍터 런타임 변수 변경 불허)
   - `threshold_relaxation_allowed`: `false` (디텍터 임계치 완화 불허)
   - `classification`: `weak_visual_change_not_threshold_candidate` (2766에 해당)
   - `visual_candidate_status`: `preserved_only` (우회 보존 정책 대상 필드)
3. **차단 변경 요건 (Blocked Changes)**:
   - **감지기 임계치 일괄 하향 (Relaxation)**: false positive 자막 갈라짐 오작동을 유발하므로 철저히 차단(blocked).
   - **persisted NLE disk fields (.aissproj 스키마 개조)**: Defer/Blocked.
   - **STT/모델 변경, UI/QML 개조, App Store 관련 빌드**: Defer/Blocked.
4. **테스트 소유자 경로 (Test Owner Paths)**:
   - `tests/test_project_nle_snapshot.py` : `NLEProjectState` 와 `NLESnapshot` 간의 marker preservation 및 Rational frames timing 정합성 검증.
   - `tests/test_cut_boundary_fixture_2766_2676.py` [NEW] : 2766 preserved_only marker 가 segment merge/split 과정에서 탈락(drop)되지 않고 정상 병합되는지 통합 검증.

defer:
- **실제 씬 디텍터 core의 default threshold 파라미터 일괄 하향**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-152200-nle-preserved-marker-policy.md` 파일 내용 및 index 맵핑 상태 점검.
