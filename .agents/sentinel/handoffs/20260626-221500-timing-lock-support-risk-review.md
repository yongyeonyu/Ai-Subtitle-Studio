DEX_REVIEW_READY
역할: 잼민이
범위: 최종 자막 timing lock support review
읽은 파일:
- core/engine/subtitle_engine.py
- core/engine/subtitle_final_integrity.py
- core/subtitle_quality/vad_alignment_checker.py
- core/audio/media_processor_transcribe_windowed.py
결론: 최종 자막 타이밍 락(Timing Lock) 도입과 관련하여, 기존 AI 파이프라인(VAD/Windowed STT/Integrity)과의 충돌에 따른 hidden compatibility risk 3개와 focused pytest gap 3개를 도출하였습니다.
findings:
1. **Hidden Compatibility Risk 3개**:
   - **리스크 A (Timing Lock vs VAD Edge-padding 충돌)**: 사용자가 수동 고정한 자막 타이밍(timing lock) 구간에 대해 `vad_alignment_checker.py` 및 `adjust_timing`이 VAD 음성 경계 패딩(edge pad)을 적용하려고 시도할 때, 수동 락을 우회하지 못하고 미세 시간 드리프트(timing drift)를 발생시켜 사용자 의도를 훼손할 위험이 있습니다.
   - **리스크 B (Windowed Overlap stitching 경계 왜곡)**: `media_processor_transcribe_windowed.py`에서 윈도우 간 겹침(overlap) 경계선 상에 사용자가 타이밍 락을 적용할 경우, 중복 제거(dedup) 및 정합(stitching) 로직이 락 영역을 비정상적인 중복 세그먼트로 인식하여 텍스트를 유실시키거나 중복 자막을 복제할 위험이 있습니다.
   - **리스크 C (Filler/어미 정제 클린업에 의한 사용자 편집 무시)**: `subtitle_final_integrity.py` 내의 `_FINAL_FILLER_FRAGMENTS`(네, 어, 아 등) 및 어미 정제 로직이 타이밍 락이 걸린 세그먼트를 평가할 때, 사용자가 명시적으로 입력한 감탄사나 발화 꼬리를 "중복/불필요 문구"로 오인하여 강제로 합치거나 삭제하는 정합성 모순 리스크가 있습니다.
2. **Focused Pytest Gap 3개**:
   - **갭 A (Locked Segment VAD Deactivation 테스트 부재)**: `locked=True` 또는 `_timing_lock=True` 속성을 가진 세그먼트가 입력되었을 때, VAD 정렬 보정기가 해당 자막의 시작/종료 시간을 0ms 단위로 완벽하게 bypass하는지 검증하는 유닛 테스트 공백.
   - **갭 B (Window Overlap Boundary Lock 스트레스 테스트 공백)**: 윈도우 스티칭 구간(예: 24s, 48s)에 걸쳐진 수동 락 자막에 대해, windowed transcriber가 자막을 분할하거나 유실시키지 않음을 검증하는 한계 조건(boundary edge case) 테스트 부재.
   - **갭 C (화자 구분선[-] 보존 무결성 테스트 공백)**: 타이밍 락 및 줄바꿈 병합이 복합 수행될 때, `enforce_final_subtitle_text_policy`가 사용자 입력 화자 표시 기호(`-`)를 소실시키지 않고 안전하게 양측 모두 유지하는지 보장하는 전용 단언 테스트 누락.
defer: 없음
덱스 확인 포인트: 본 분석 문서는 덱스(Codex) 측에서 최종 자막 타이밍 락 설계를 구체화할 때, VAD/STT/Integrity 레이어에서 락 플래그를 예외 없이 bypass하기 위한 아키텍처 제약 사항으로 참조 및 회수될 수 있습니다.
