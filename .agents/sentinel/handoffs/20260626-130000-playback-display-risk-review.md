DEX_REVIEW_READY
역할: 유진
범위: Playback frame/time display risk review
읽은 파일:
- ui/editor/video_player_widget.py
- ui/editor/video_player_transport.py
- tests/test_video_player_widget.py
결론: 재생화면 Taption식 프레임/시간 정보 표시 추가와 관련하여 UI layout drift, quick QML bar sync, frame_time_map 오차, 59.94fps 누적 드리프트 리스크 및 검증 숏리스트를 요약했습니다.
findings:
1. **기존 UI layout drift 리스크**: 비디오 컨트롤러 하단 가로폭이 좁아지는 환경(예: 창 크기 축소 시)에서 신규 프레임/시간 라벨의 너비 배분이 고정되지 않으면, 기존 재생/정지 버튼이나 파일명 표시 배지와 겹치거나 밀리는 레이아웃 깨짐 현상이 발생할 수 있습니다. 위젯 고정폭 및 stretch 배율의 한계 검증이 선행되어야 합니다.
2. **quick QML bar sync 리스크**: 재생 중 매 프레임마다 PyQt 시그널을 통해 `_sync_quick_control_bar`를 호출하여 QML/외부 오버레이 계층에 문자열을 전달할 경우, 60fps 비디오 등 고주파 갱신 환경에서 스레드간 오버헤드로 인해 재생 끊김 및 UI 스레드 교착(lock)이 발생할 수 있습니다. UI 갱신 타이머 주기에 맞춘 스로틀링(throttling) 처리가 필수적입니다.
3. **frame_time_map 기준 시간 산출**: 가변 프레임 레이트(VFR) 혹은 변칙 인코딩 비디오에서의 오차 누적을 방지하기 위해, 모든 프레임 <-> 시간 변환은 단순 수학적 나눗셈이 아닌 플레이어의 `self.frame_time_map` 객체의 메소드를 엄격하게 통과하도록 강제해야 합니다.
4. **59.94fps 표시 및 누적 드리프트 리스크**: NTSC 59.94fps 비디오 환경에서 드롭프레임 보정 없이 표시할 경우, 재생 시간이 길어질수록 렌더링 프레임 카운트와 실제 플레이어의 timeline_sec 간에 누적 시간 편차가 벌어집니다. 소수점 정밀도를 보존하는 타임코드 렌더링 검증이 필요합니다.
5. **Focused Validation Shortlist**:
   - **59.94fps/VFR 맵 정확도 단언**: 모의 프레임 맵을 생성하여 프레임 인덱스에 따른 변환 오차가 1ms 이하로 수렴함을 단언하는 테스트 수립.
   - **오버레이 갱신 시그널 스로틀링 검증**: 재생 시그널이 폭주하더라도 QML 갱신 함수 호출 빈도가 제한되도록 보장하는 모의 호출 주기 테스트 추가.
   - **최소 창 크기 지오메트리 테스트**: offscreen 환경에서 위젯 너비를 260px로 설정했을 때 텍스트 라벨 잘림/숨김 동작 무결성 확인.
defer: 없음
덱스 확인 포인트: 본 리스크 리뷰 문서는 덱스(Codex) 측에서 재생화면 타임코드 및 프레임 표시 기능을 구현할 때 레이아웃 충돌 및 VFR/드롭프레임 정밀도 손실을 방지하기 위한 가이드로 회수 및 참조될 수 있습니다.
