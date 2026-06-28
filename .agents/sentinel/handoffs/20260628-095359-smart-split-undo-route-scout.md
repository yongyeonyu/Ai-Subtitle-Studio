DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio smart split undo route scout

findings:
1. **문제 정의 (Smart Split Undo 우회 에러)**:
   - `tests/test_editor_split_undo.py` 내의 `test_smart_split_undo_and_redo_follow_snapshot_history_with_text_focus` 테스트 실행 시, `editor._on_smart_split` 이 호출된 직후 `_route_undo` 에서 snapshot undo route 매칭에 실패하고 QTextEdit 의 raw `undo`가 호출되는 문제 발생.
2. **원인 분석 (Revision Drift)**:
   - `_on_smart_split` 은 `self._arm_gap_snapshot_undo_routing()` 을 호출하는데, 이는 인자값 없이 `self._arm_snapshot_undo_routing(allow_revision_drift=False)` 로 동작함.
   - smart split 중 block 조작 및 cursor 포커스 제어로 인해 QTextDocument 의 내부 `revision` 에 변동(drift)이 발생하며, 이로 인해 `undo_route_matches` 판정 시 `revision == current_revision` 이 깨져 `False` 가 반환됨.
   - 그 결과, `QApplication.focusWidget().undo()` 가 실행되어 구조적인 세그먼트 스냅샷 복원이 아니라 QTextEdit 자체의 로컬 텍스트 타이핑 undo 가 타버려 테스트 단언이 실패함.
3. **최소 오너 파일 및 경로 (Owner Files/Functions)**:
   - `ui/editor/ux/editor_timeline_gap_split.py` : `_arm_gap_snapshot_undo_routing`
   - `ui/editor/editor_multiclip_context.py` : `_arm_snapshot_undo_routing` 및 `_route_undo`
4. **안전한 Fix 후보 1개 (Safe Fix Candidate)**:
   - **조치**: `ui/editor/ux/editor_timeline_gap_split.py` 의 `_arm_gap_snapshot_undo_routing` 에서 `self._arm_snapshot_undo_routing(allow_revision_drift=True)` 와 같이 `allow_revision_drift=True` 옵션을 부여하여 revision 이 어긋나더라도 text document snapshot의 structure signature 가 동일하다면 snapshot undo route 를 타도록 정상 유도함.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 알고리즘이나 음성/텍스트 모델과 무관한 순수 에디터 Undo/Redo 라우팅 정합성 수정이므로 HeyDealer benchmark validation 이 불필요함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-095359-smart-split-undo-route-scout.md` 파일 내용 및 index 맵핑 상태 점검.
