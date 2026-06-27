DEX_REVIEW_READY
역할: 서린 (strict QE)
범위: STT latency NAS-off scheduling/memory variance review
읽은 파일:
- `ACTION_ITEMS.md` ([ACTION_ITEMS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ACTION_ITEMS.md))
- `docs/HANDOFF.md` ([docs/HANDOFF.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/docs/HANDOFF.md))
- `waste_action_item.md` ([waste_action_item.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/waste_action_item.md))
- `lesson_n_learned.md` ([lesson_n_learned.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/lesson_n_learned.md))
- `tools/benchmark_subtitle_pipeline_variants.py` ([tools/benchmark_subtitle_pipeline_variants.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tools/benchmark_subtitle_pipeline_variants.py))
- `tools/verify_full_media_pipeline.py` ([tools/verify_full_media_pipeline.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tools/verify_full_media_pipeline.py))
- `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md` ([output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md))
- `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md` ([output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md))

결론: NAS-off 상태에서 품질 하락(regression)을 방지하고 무결성을 유지하며 진행 가능한 안전 최적화 조각과 절대 건드리지 말아야 할 후보를 분류하고 HOLD 판정을 내렸습니다.

findings:
1) **진행 가능한 안전 조각**:
   - **LLM macro warmup skip / Defer resolution**: `llm_rows > 0`일 때만 Ollama model을 준비하도록 lazy init를 유지하고 캐시 히트 시 Ollama warmup을 완전히 스킵하는 로직 (안전성 기확보).
   - **STT/word precision collect replay cache**: 캐시된 원시 collect 출력을 재사용하는 방법. 단, default는 `false`로 유지.
   - **Memory pressure 및 Worker restart variance 모니터링**: 성능 측정을 진행할 때 `runtime_monitor`와 peak RSS bytes 계측을 병행하여, latency variance의 근본 원인이 memory pressure에 의한 STT persistent worker 기동 실패인지 파악하는 추적 분석.

2) **하지 말아야 할 후보 (품질 저하 / 버그 유발)**:
   - **STT1/STT2 full-parallel을 High 기본값으로 승격하는 것**: X5 60초 기준 속도는 빠르나 final segment count 및 reference quality 하락 유발 (금지).
   - **STT2/단어 정밀도의 count 필드만 보고 applied_count=1 범위 자체를 강제로 생략/삭제하는 것**: missing voice 구조 실패를 초래하므로 금지.
   - **VAD consensus에서 전체 파일급 VAD span을 단일 자막에 병합(union)하는 행위**: tail collapse 유발로 인해 절대 금지 (similar vad/stt1 span consensus 유지 필수).
   - **동일한 prompt/모델 호출에 대해 decision-equivalent parity guard가 증명되지 않은 채로 High 문맥 경계 LLM pair 검수를 batching하는 것**: 품질 및 text MAE 점수 회귀를 유발하므로 금지.
   - **STT1/STT2, Word Precision collect 캐시(`stt_primary_collect_cache_enabled`, `stt_recheck_collect_cache_enabled`)를 기본적으로 active/true로 활성화하는 것**: NAS-off 상태에서는 synthetic fixture만 확인 가능하므로, 실제 미디어 백필 테스트를 통한 parity proof가 없으면 default true 활성화 금지.

3) **필요한 검증 명령**:
   - VAD consensus 및 STT/boundary timing focused tests:
     `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_quality_models.py -k "vad_voice_start_priority or vad_stt_timing_consensus"`
   - NAS HeyDealer 180s reference benchmark (NAS 마운트 시에만 사용):
     `./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high --media "/Volumes/photo/.../헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/.../헤이딜러_최종.srt" --start-sec 0 --duration-sec 180 --keep-artifacts`
   - NAS-off generated video validation:
     `./venv/bin/python tools/verify_full_media_pipeline.py --media output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.mp4 --reference-srt output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.srt --mode high`
   - QA quick suite run:
     `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick`

4) **accept/hold verdict**:
   - **VERDICT: HOLD**
   - 사유: NAS가 꺼져 있는 환경(NAS-off)에서는 HeyDealer 180s 실제 동영상 미디어를 이용한 품질 저하(semantic / timing MAE regression) 검증을 동적으로 수행할 수 없습니다. 따라서 NAS 복구 전까지는 비동작 변경이 없는 계측 및 캐시 세부 key 정규화 등에 한해서만 작업을 제안하며, 알고리즘 변경 및 STT/LLM trim 작업은 모두 hold 상태로 유지해야 합니다.

defer: (none)
덱스 확인 포인트:
- NAS-off 상황에서 synthetic fixture와 real media(HeyDealer 180s) 간의 검증 신뢰도 갭을 고려하여, 캐시 및 warmup-skip 이외의 실질적인 latency-trim 알고리즘 수정은 NAS 복구 이후로 스케줄링을 유예할 것을 동의하는지 확인.
