DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio strict synthetic collect-cache replay prep

findings:
1. **Synthetic Fixture 경로**: `test video/synthetic_voice_180s.mp4` (오디오/영상 합성 소스).
2. **Reference SRT 경로**: `dataset/synthetic_voice_180s.srt` (54개 정형 SRT 행 셋업).
3. **캐시 분리 Benchmark 명령어 (1차 Write / 2차 Hit Replay 동일 적용)**:
   - `stt_primary_collect_cache_path="output/synthetic_cache/stt1_cache.json"`
   - `stt_recheck_collect_cache_path="output/synthetic_cache/stt2_cache.json"`
   - `subtitle_llm_macro_response_cache_path="output/synthetic_cache/macro_cache.json"`
   - 각각 `--setting` 옵션을 통해 명확히 경로를 분리하여 충돌을 원천 방지함.
4. **Acceptance 검증 필수성**: `tools/evaluate_reference_benchmark_acceptance.py`를 무조건 호출하여 tail-collapse-fixed 자막의 duration-bound 및 overlap `0` 정합성을 파이프라인 레벨에서 종단 검증해야 함.
5. **엄격한 최종 게이트 조건**:
   - `final_last_end_beyond_duration_bound` 패스 (마지막 자막 종료 시간 <= 180.584s).
   - final / SRT overlap count = 0.
   - final_invalid/non-monotonic/overlap = 0/0/0.
   - 2차 Replay 런의 경과 속도가 5초 이내로 완료(provider call 0회).
