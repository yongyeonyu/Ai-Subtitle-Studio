DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio roughcut sidecar NLE compatibility scout

findings:
1. **문제 정의 (러프컷 사이드카 NLE 호환성 계약)**:
   - 러프컷 내보내기 및 비디오 렌더링 시 생성되는 sidecar 파일(`_render_plan.json`, `_edl.json` 등)의 write/load 동작이, active NLE sequence state 와 `nle_render_export_parity` 의 구조적 검증을 방해하지 않고 비파괴적으로 병행 동작하도록 호환성 확보 필요.
2. **오너 파일 (Owner Files)**:
   - `ui/roughcut/roughcut_export.py` : `_nle_project_payload_for_render_plan` (NLE roughcut render payload 빌더)
   - `core/project/nle_render_export_parity.py` : `assert_project_nle_render_export_parity` (NLE와 sidecar 간 export parity 검증)
3. **Focused Tests to add**:
   - `tests/test_roughcut_sidecar_nle_compatibility.py` [NEW] : NLE active sequence 로부터 러프컷 sidecar를 내보낸 직후, 내보낸 `_render_plan.json` 의 stitched cut boundaries 구조가 NLE snapshot 의 cut boundaries와 오차 없이 일치하며 `assert_project_nle_render_export_parity` 를 정상 패스함을 단언하는 integration test.
4. **Audit Artifact Path**:
   - `tools/audit_nle_roughcut_sidecar_isolation.py` [NEW] : static 분석을 통해 roughcut sidecar write 로직이 runtime NLE memory 의 undo stack 이나 active state 를 임의로 훼손하지 않고 project asset file storage 에만 non-destructive 하게 기록되는지 검증하고 `passed=true` 보고서 작성.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 알고리즘이나 음성/텍스트 모델과 무관한 러프컷 내보내기/렌더링 시의 sidecar 정합성/격리 규약이므로 HeyDealer benchmark validation 이 불필요함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-100359-roughcut-sidecar-nle-compatibility-scout.md` 파일 내용 및 index 맵핑 상태 점검.
