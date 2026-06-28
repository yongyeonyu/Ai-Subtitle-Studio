DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after cut marker point-evidence projection 20260628

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE missing media relink and proxy switch cache metadata non-destructive contract" (미디어 파일 링크 손실/재지정 및 프록시 전환 시 NLE 캐시 메타데이터의 소거 없는 영구 보존 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 사용자가 작업 중 미디어 디스크 위치를 옮겨 relink 하거나 proxy 영상으로 전환하는 시나리오에서도, 기존에 생성되었던 초고속 비디오 preview frame cache 썸네일을 유실 없이 즉시 재활용할 수 있게 하여 Taption NLE 스크러빙 성능의 연속성(continuity)을 완벽하게 수호함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/project/project_io.py` : `_attach_project_path`, `attach_project_nle_state` (relink 및 path binding 지점)
   - `core/runtime/preview_frame_cache.py` : `preview_frame_cache_dir`, `preview_frame_cache_path` (미디어 path 의 short-hash 기반 캐시 path 매핑 제공)
4. **Focused Tests to add**:
   - `tests/test_nle_relink_cache_metadata_preservation.py` [NEW] : 프로젝트 파일 내 미디어 절대 경로(`media_files` path)를 인위적으로 변경(relink mock trigger)한 전후로, `preview_frame_cache` 디렉터리가 동일 content signature 조건 하에서 drop 되지 않고 그대로 승계 보존되는지 검증하는 integration test.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 미디어 바인딩 및 캐시 메타데이터 변경을 수집하므로, HeyDealer first-180s benchmark (`heydealer_first_180s.mp4`) 기반 quality/segment-count regression validation 이 반드시 수행되어야 함.
6. **Rollback Risk**:
   - **리스크**: proxy 영상과 원본 영상의 프레임레이트(FPS) 불일치 시, caching metadata 가 어긋나 재생헤드가 부정확해질 리스크.
   - **대책**: validation failure 또는 FPS mismatch 감지 시, dynamic proxy metadata mapping 을 즉시 차단하고 기존 default non-proxy metadata 상태로 rollback.
7. **Acceptance Gate**:
   - HeyDealer 180s benchmark 실행 결과 `accepted=true`, `final_last_end_beyond_duration_bound=false`, SRT rows 의 타이밍 overlap 및 monotonic 정합성 깨짐 0건 통과.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-083937-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_ACCEPTED_20260628
- 채택 범위: AI Subtitle Studio lane의 preview/skimming frame cache relink reuse contract.
- 구현 보정: persisted project fields나 UI relink flow는 건드리지 않고, `core/runtime/preview_frame_cache.py`에 path-independent media identity manifest와 bounded relink scan을 추가했다.
- Proxy 보정: proxy/transcoded file은 같은 source identity가 아니면 cache reuse를 차단하고, 기존 proxy switch가 original source path를 유지하는 경우만 안전한 것으로 문서화했다.
- 증거: `output/manual_verification/latest/nle_relink_preview_cache_contract_20260628/nle_relink_preview_cache_contract.md`.
- NAS 증거: `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_174547/benchmark_results.json`, acceptance `output/manual_verification/latest/nle_relink_preview_cache_nas_heydealer_20260628/acceptance/reference_benchmark_acceptance.md`, timeout audit `output/manual_verification/latest/stt_worker_timeout_compare_nle_relink_preview_cache_nas_20260628/stt_worker_timeout_audit.md`.
