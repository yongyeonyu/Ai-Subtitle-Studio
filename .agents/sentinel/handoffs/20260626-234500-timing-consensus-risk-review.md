DEX_REVIEW_READY
역할: 잼민이
범위: VAD/STT timing consensus support review
읽은 파일:
- core/subtitle_quality/vad_alignment_checker.py
- tests/test_subtitle_quality_models.py
결론: VAD/STT1/STT2 2-of-3 timing consensus(합의 정책) 도입 시 발생할 수 있는 hidden risk 3개와 focused pytest gap 3개를 도출하여 정리를 완료했습니다.
findings:
1. **Hidden Risk 3개**:
   - **리스크 A (VAD 누락으로 인한 2-of-3 합의 오작동 및 False-Negative)**: VAD가 미세 음성을 놓쳐 무음(silence)으로 처리한 경우, STT1/STT2가 모두 해당 발화를 정상 인식했음에도 2-of-3 합의 요건을 채우지 못해 멀쩡한 자막 타이밍이 유실되거나 배제되는 false-negative 리스크가 큽니다.
   - **리스크 B (STT1 vs STT2 세그먼트 경계 불일치 및 텍스트 오염)**: STT1과 STT2가 문장을 분할하는 경계(boundary segment count)와 단어 타임스탬프가 서로 다를 때, 2-of-3 매칭을 위한 강제 스냅 과정에서 텍스트 토큰의 오정렬(alignment mismatch) 및 자막 타이밍이 1~2초 수준으로 엇갈리는 drift가 발생할 위험이 있습니다.
   - **리스크 C (소수점 드롭프레임 환경에서의 1프레임 미세 Jitter)**: 29.97/59.94fps 등 NTSC 소수점 프레임 환경에서 타임스탬프 사상 시 발생하는 미세 지터(16.7ms~33.3ms)로 인해, 합의 오차 허용 윈도우(tolerance window) 밖으로 튕겨 나가 판정이 불안정하게 요동칠 리스크가 존재합니다.
2. **Focused Pytest Gap 3개**:
   - **갭 A (VAD Zero-overlap 시 예외 복구 테스트 부재)**: VAD가 0s 영역을 나타내더라도 STT1과 STT2의 상호 일치도가 높을 경우, 자막 타이밍이 안전하게 보존되고 lock되는지 검증하는 VAD 누락 시나리오 유닛 테스트 공백.
   - **갭 B (비대칭 STT1/STT2 세그먼트 스티칭 테스트 공백)**: STT1은 1개 세그먼트, STT2는 2개 세그먼트로 비대칭 쪼개진 상태에서 2-of-3 합의 알고리즘이 개별 시간 블록을 정확히 분할 결합해 내는지 단언하는 결합 테스트 부재.
   - **갭 C (59.94fps 드롭프레임 시간 정밀도 Jitter 테스트 공백)**: 드롭프레임 환경의 미세 소수점 타임스탬프 오차 하에서도 2-of-3 합의 판정이 왜곡되지 않고 일관되게 단언되는지 검증하는 프레임 변환 안정성 테스트 스위트 부재.
defer: 없음
덱스 확인 포인트: 본 분석 자료는 덱스(Codex) 측에서 VAD/STT1/STT2 2-of-3 합의 스냅 로직을 설계할 때, VAD 오감지 예외 처리 및 소수점 프레임 지터로 인한 판정 불안정을 방지하기 위한 가이드로 회수 및 참조될 수 있습니다.
