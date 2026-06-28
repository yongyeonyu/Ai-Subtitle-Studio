DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio playhead dirty-rect parked candidate scout

findings:
1. **최적화 안전성 검토**: 'Playhead-only dirty-rect repaint'를 활성화하여 플레이헤드 수직 영역만 제한적으로 다시 그리게 할 경우, 플레이헤드가 waveform이나 자막 박스를 지날 때 잔상(ghosting)이 남거나 waveform 드로잉 갱신 누락이 발생하는 Macau visual regression 리스크가 매우 큼.
2. **Macau visual smoke 전의 유지 원칙**: Macau visual smoke(PyQt 스크린샷 무결성 검증) 패스가 확실히 구축·검증되기 전까지는 **기존의 full canvas repaint 및 QWidget viewport clipping 정책을 100% 그대로 유지하는 것이 타당함 (최적화 도입 Reject/HOLD 권장)**.
3. **필요한 테스트 및 감사 Artifact**:
   - **감사 스크립트**: `tools/audit_editor_rendering_ownership.py`를 실행하여 QPainter paint passes 소유권 무결성 진단.
   - **focused tests**:
     - `tests/test_editor_rendering_ownership_audit.py` (렌더링 소유권/bounds 체크)
     - `tests/test_timeline_playhead_fit.py` (플레이헤드 재생 스냅 및 update 호출 bounds 매칭)
4. **결론**: UI 잔상 리스크가 크므로 playhead dirty-rect 최적화는 **보류(Defer/Reject)**하고, 안전한 비파괴 렌더 소유권 진단 및 fit tests 만 강화할 것을 추천.
