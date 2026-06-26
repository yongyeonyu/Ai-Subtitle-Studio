DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: X5 source-app proof fixture blocker review (NLE baseline QA gate)
읽은 파일:
- `tools/qa_suite_runner.py`
- `output/manual_verification/latest/qa_suite_full_20260626_083038/suite_result.md`
- `output/manual_verification/latest/qa_suite_full_20260626_083038/x5_high_rolling_180s/fixture_blocker.md`

결론:
현재 `qa_suite_full_20260626_083038`에서 발생한 `x5_high_rolling_180s` 시나리오 실패는 오디오 스트림이 부재한 `X5_시승기_후반_자막소스.mov` 미디어가 선택되었기 때문(`empty_subtitle_output:raw_segments_zero`)입니다. 오디오 트랙이 없는 미디어 파일은 STT/VAD/LLM 핵심 자막 생성 파이프라인 자체를 구동할 수 없으므로, 이를 성공 proof로 대체하거나 QA 통과 기준으로 삼는 것은 **절대 불인정(Reject)**합니다.

findings:

1. 오디오 없는 `_자막소스.mov` 성공 대체 가능성 판정: **절대 불인정 (Reject)**
- **이유**:
  - `ffprobe` 검사 결과 `X5_시승기_후반_자막소스.mov` 파일은 Prores 비디오 스트림만 존재할 뿐 오디오 스트림이 누락되어 있습니다.
  - 이 상태에서 STT 파이프라인을 타게 되면 VAD/STT 엔진이 입력 오디오 신호 부재로 0개의 자막 세그먼트를 추출하고, 결국 `raw_segments_zero` 예외를 발생시키며 테스트 전체를 즉시 중단(Crash)시킵니다.
  - 비디오 스트림만 검증용으로 사용하기 위해 dummy 오디오를 무단 합성해 강제 패스시키는 꼼수는 실제 STT 가속 및 ANE/GPU 메모리 정합성을 오염시키고 실질적인 타이밍 오차 감지를 차단하므로 QE 관점에서 승인할 수 없습니다.

2. 충분한 증거와 Missing 증거 구분 (4개)
- **충분한 증거 1 (오버라이드 오디오 단독 패스)**:
  - 이전에 별도로 수동 오버라이드한 wav 오디오 피드(`/Users/u_mo_c/Music/.../X5_시승기_편집중_raw.wav`)를 통해 STT2가 52개 자막을 정확히 생성하여 모델 추론 및 text parsing, 소요 시간(`41.282s`), 메모리(`725MB`) 부하 정합성은 이미 정상 검증 완료되었습니다.
- **충분한 증거 2 (Macau 비디오 UI 인터랙션)**:
  - 실제 비디오 피드를 가진 Macau 시나리오 (`editor_compact_macau`, `video_menu_macau` 등) 8개 항목이 모두 `ok`로 정상 통과되어, 비디오 화면 렌더링 및 Seek, 컷 정렬 GUI 기능은 baseline 수준에서 충분히 동작함이 입증되었습니다.
- **Missing 증거 1 (비디오와 오디오가 결합된 실질적 X5 렌더링 검증)**:
  - X5 비디오와 오디오가 동시 복원되어 타임라인에 안착하고, 이 비디오 트랙을 기반으로 자막 합성(burn-in) 비디오 내보내기(`roughcut-render-video` 등)가 프레임 밀림 없이 ffmpeg concat을 완수하는지의 증거는 X5 MP4의 부재로 인해 완전히 유실(Missing)되었습니다.
- **Missing 증거 2 (VFR 미디어 디코딩 락 감지)**:
  - 순수 오디오 피드로는 HEVC/H.264 등 비디오 디코딩 시 유발될 수 있는 ANE/GPU 락 현상을 포착할 수 없습니다.

defer:
- 런타임 수선 및 fixture MP4 획득은 본 QE review 단계에서는 일체 수행하지 않으며, 덱스(Codex) 구현 세션으로 위임합니다.

덱스 확인 포인트:
1. `X5_시승기_후반.MP4` 소스 미디어가 대표님 환경에 부재하므로, 덱스 측에서는 오디오와 비디오가 모두 포함된 10~15초 수준의 초경량 X5 mock 미디어(X5_mock.mp4, AAC 오디오 포함)를 새 fixture로 리포지토리에 동반 탑재하여 `empty_subtitle_output`을 우회하는 방안을 채택해야 합니다.
2. X5 검증에서 오디오 없는 mov 파일이 로드되었을 때는 `empty_subtitle_output` 크래시를 내지 않고 'skipped: audio_stream_missing' 경고를 출력하도록 `verify_full_media_pipeline.py`에 가드 처리를 추가할지 판단해야 합니다.
