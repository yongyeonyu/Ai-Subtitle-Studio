DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio roughcut_range_edit NLE owner-map scout 20260628

findings:
1. **commit boundary vs per-pixel write 위험 검토**:
   - **결과**: `roughcut_range_edit`는 UI 마우스 드래그에 따른 per-pixel (실시간 밀리초 단위) write가 아닌, 러프컷 순서 변경/트림 확정 시점에 작동하는 **release commit boundary**에 속함. 따라서 I/O 폭발이나 실시간 timeline stuttering 위험이 전혀 없음.
2. **final subtitle overlay / global canvas 영향 검토**:
   - **결과**: roughcut output sequence 에 한정되는 output-domain 연산이므로, 원본 시퀀스 정보인 final subtitle overlay 및 global timeline canvas의 렌더링에 일체 영향(side-effect)을 주지 않고 완벽히 격리됨.
3. **저장 payload NLE journal/schema 유출 차단 gate**:
   - **결과**: `project_io.py` 의 `strip_unapproved_nle_persistence_fields`가 save 시 runtime keys 및 NLE state를 .aissproj 파일에서 완전 소거(strip)하므로 디스크 파일에 정보가 새어나가지 않음.
4. **추천 다음 슬라이스**:
   - **추천 항목**: **"roughcut_range_edit NLE Undo Journal & Runtime Owner-Map integration" (roughcut_range_edit NLE 저널 및 오너맵 연동)**
5. **focused tests 및 audit evidence**:
   - `tests/test_project_nle_operations.py` : `roughcut_range_edit` operation의 스키마 정합성 유닛 테스트.
   - `tests/test_roughcut_v2_output_compat.py` : NLE undo snapshot capturing 시 hash parity 일치 여부 검증.
   - `tools/audit_nle_runtime_owner_map.py` : `OWNER_EVIDENCE`에 `roughcut_range_edit` 의 code evidence mapping 행 추가 보강.

defer:
- **실제 roughcut UI/UX 디자인 변경, 뷰어 개조**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **QML/UI 및 App Store 관련 작업**: Defer 함.
- **aissproj 디스크 파일 포맷 내 persisted NLE fields 구조 변경**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-153300-nle-roughcut-range-edit-owner-map.md` 파일 내용 및 index 맵핑 상태 점검.
