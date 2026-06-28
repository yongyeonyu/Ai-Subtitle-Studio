DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE dual-write duration-bound trim enforcement scout 20260628

findings:
1. **Trim Helper public/private 선택**:
   - **선택**: `core/project/project_context.py` 의 private `_trim_segments_to_project_duration` 을 public API 인 `project_trim_segments_to_duration` 으로 명명/승격하여 외부 노출함.
2. **Owner Functions (적용 대상 함수)**:
   - `core/project/nle_dual_write.py` : `apply_caption_move_dual_write_pilot`, `apply_caption_split_dual_write_pilot` 등. projected_rows 를 생성하여 legacy segment list 및 NLE state 로 돌려주기 전 최종 filter 지점.
3. **Actual Behavior Delta (구현 면적)**:
   - `projected_rows` 덤프 직전 `projected_rows = project_trim_segments_to_duration(projected_rows, project, primary_fps=fps)` 처리를 적용하여 미디어 길이 밖으로 밀려난 자막의 tail clamp 와 drop 을 즉각 강제.
4. **Focused Tests to add**:
   - `tests/test_nle_dual_write_duration_trim.py` [NEW] : caption move / split 연산 후 end bounds 가 duration-sec (`180.584s` 등)을 넘을 때, tail collapse 나 validation error 없이 안전하게 trim 됨을 검증하는 integration test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_dual_write_duration_trim.py` [NEW] : static code 분석을 통해 trim helper 가 float rounding error 및 sequence hash parity 에 영향을 주지 않고 안전하게 clean storage 로 빠지는지 검증하는 정적/동적 감사 스크립트.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 자막의 end-bounds 와 segment duration 변동을 초래하는 편집 연산이므로, HeyDealer first-180s real-media fixture (`heydealer_first_180s.mp4`)를 이용한 end-bound 및 SRT generation parity 검증이 필수적임.
7. **Rollback Risk**:
   - **리스크**: trim helper 적용 시, segment boundary rounding 차이에 의해 end boundary가 미세하게 잘려서 float 오차가 생기거나 sequence hash parity 가 어긋나는 리스크.
   - **대책**: audit script `tools/audit_nle_dual_write_duration_trim.py` 로 test fixture save/reopen 의 hash parity 정합성을 검사하여 parity 가 맞지 않을 경우 dual-write 내 duration trim 부분을 bypass(disabled wrapper) 상태로 즉각 롤백.
8. **Acceptance Gate**:
   - HeyDealer 180s benchmark 실행 결과 `accepted=true`, `final_last_end_beyond_duration_bound=false`, SRT rows 의 타이밍 overlap 및 monotonic 정합성 깨짐 0건 통과.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-073009-nle-dual-write-duration-trim-prep.md` 파일 내용 및 index 맵핑 상태 점검.
