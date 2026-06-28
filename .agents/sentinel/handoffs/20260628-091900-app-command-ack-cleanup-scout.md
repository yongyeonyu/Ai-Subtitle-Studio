DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio app command acknowledgement cleanup scout

findings:
1. **Shortlist 1: `ui/main/app_command_bridge_handlers.py`**
   - **설명**: `guided-subtitle-run` 및 `capture-snapshot` 실행 시, snapshot 큐 상태(`queued=True/False`) 및 started 타임스탬프 응답 메타데이터를 추가로 보강하는 지점.
   - **역할**: 비동기 snapshot 파일 저장 지연 시 client timeout이 터지지 않게 started/queued 상태 전송 보장.
2. **Shortlist 2: `ui/main/app_command_bridge.py`**
   - **설명**: status/ping 응답 조립기. redundant 리스트 데이터를 정제하여 UDP 65KB 패킷 제한 내로 압축 전송 처리하여 패킷 silent drop 리스크 방어.
3. **Shortlist 3: `tests/test_app_command_bridge.py`**
   - **설명**: `test_guided_subtitle_run_acks_started` 및 `test_capture_snapshot_respects_async_queued` 등의 focused tests를 밀어넣어 response ack 무결성 증명.
4. **Shortlist 4: `tests/test_remote_verify_actions.py`**
   - **설명**: `remote_verify capture` 통신 중 socket timeout 발생 시 client-side socket handling 복구 시나리오 테스트.
5. **결론**: App Store/NLE/UI 변경 없이 오직 socket response packet size 및 timing ack 정보만 개선하는 **app command ack cleanup 비파괴 슬라이스로서 매우 안전(Accept 권장)**.
6. **추천 테스트**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py` (bridge cmd 78개 통과 검증)
7. **수정 불가 경계**:
   - 에디터 state machine의 transition, subtitle generation pipeline 핵심 로직, `.aissproj` 저장 스키마.
