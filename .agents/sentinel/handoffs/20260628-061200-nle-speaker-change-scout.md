DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next uncovered NLE release source risk scout retry

findings (12줄 이내 요약):
1. **선정 후보**: 단순 화자 변경 (`_change_speaker_for_line`)
   - **이유**: `_on_smart_split` 은 시간 경계 분할 및 새 자막 추가 등 복잡한 timing 리스크가 크나, 화자 변경은 시간 변동 없이 메타데이터만 갱신하므로 훨씬 안전함.
2. **Owner function**: `ui/editor/editor_speaker_ops.py` 의 `_change_speaker_for_line`
3. **Release boundary 근거**: 타임라인 화자 서클 우클릭 또는 드롭다운 선택 완료를 통해 특정 line 의 화자 ID를 확정 커밋하는 시점.
4. **UI-shape/metadata 위험**: 변경된 화자 ID가 NLE State metadata에 동기화되지 않을 시 `save-project` 시점의 projection metadata drift 에러 유발.
5. **필수 guard**: 대상 line에 대응하는 canonical 자막 ID를 NLE state에서 명확히 타겟팅하여 metadata를 atomically 업데이트해야 함.
6. **추천 pytest 명령**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "speaker"`
