# Performance Ideas

## 2026-05-20 Scope
- 대상 미디어: 마카오 `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4`, X5 `test video/X5_시승기_후반.MP4`
- 실행 방식: `./venv/bin/python tools/verify_full_media_pipeline.py --mode fast --repeat 10`
- 품질 기준: `final_segment_count`, `raw_segment_count`, `variant_score.score`, `llm_rollback_count`
- 반복 최적화 사이클: 3회

## 현재 채택 후보
- 채택 후보: `candidate1`
- 유지 코드: [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:537)
- 유지 이유: 자막 품질은 유지하면서 X5 평균 시간이 가장 좋았고, 폐기 후보 2개보다 전체 균형이 안정적이었다.

## 기준값

### 이전 기준 참고값
- 마카오 baseline: avg `6.680` / min `6.583` / max `6.845`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_baseline/baseline_current_macao`
- X5 baseline(canonical): avg `61.750` / min `61.193` / max `62.571`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_baseline/baseline_current_x5_canon`

### 이번 작업의 현재 기준값
- 현재 HEAD baseline은 `candidate1` 결과를 사용한다.
- 마카오 current: avg `6.770` / min `6.604` / max `7.240`
- X5 current: avg `61.252` / min `60.705` / max `62.201`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_candidate1`

## 3회 반복 결과

### 1차 채택: checkpoint cleanup 완화
- 변경 포인트:
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:537),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:728),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:991),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:1080)
- 요약: `audio_extract_done`, `stt_transcribe_done`, `stt_optimizer_threads_done`, `save_export_done`에서 평시 강제 cleanup/trim 호출을 줄이고, `critical`일 때만 MemoryGuard 자동 정리에 더 의존하도록 조정.
- 결과:
  마카오 avg `6.770` (`+1.35%` vs 이전 baseline)
  X5 avg `61.252` (`-0.81%` vs 이전 baseline)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 현재 채택

### 2차 폐기: `cut_prescan_done` cleanup 제거
- 변경 시도: `cut_prescan_done`의 `cleanup=True` 제거
- 가설: prescan 직후 trim이 불필요한 no-op 비용일 수 있다.
- 결과:
  마카오 avg `7.474` (`+10.40%` vs current)
  X5 avg `64.709` (`+5.64%` vs current)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 폐기
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate2`

### 3차 폐기: `subtitle_optimize_done` warning-stage GPU trim 축소
- 변경 시도: `subtitle_optimize_done`의 `include_gpu=True` 제거
- 가설: 청크 후처리마다 warning-stage GPU trim이 반복되며 X5 누적 비용을 키울 수 있다.
- 결과:
  마카오 avg `6.682` (`-1.30%` vs current)
  X5 avg `63.007` (`+2.87%` vs current)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 폐기
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate3`

## 관찰 정리
- `cut_prescan_done` cleanup 제거는 메모리를 남겨서 빨라지기보다, 오히려 X5에서 이후 STT/후처리 구간 비용을 키웠다.
- `subtitle_optimize_done` warning-stage GPU trim 제거도 마카오 단건은 약간 좋아졌지만, X5 반복 평균과 분산을 개선하지 못했다.
- 채택 후보와 폐기 후보 모두 마카오/X5의 `final_segment_count`, `raw_segment_count`, `variant_score`, `rollback`은 동일했다.
- X5 run_10 기준 `process_snapshot_after.total_matched=2`로 남는 프로세스는 `ollama serve`와 `ollama runner`뿐이었다.

## 다음 아이디어
1. `SubtitleGenerationMemoryGuard`에 stage별 trim 실행 횟수와 wall time을 기록해서, 느려지는 구간을 로그로 바로 상관관계 분석한다.
2. `core/runtime/memory_manager.py`의 디스크 캐시 사용량 스캔 TTL/루트 인덱스 TTL을 벤치 대상으로 올린다.
3. `core/native_swift_runtime_cache.py` 호출 수와 native bridge elapsed를 함께 기록해서, 정리 호출 빈도보다 bridge 비용이 더 큰지 확인한다.
4. `core/audio/media_processor_transcribe.py`의 STT release 경로에서 warning 단계 `clear_audio_model_memory_caches(include_gpu=False)` 호출량을 계수화한다.
5. Ollama `serve/runner` 상주 시간이 반복 생성 평균에 미치는 영향을 분리 측정한다.
6. 품질 불변 hot path가 확인되면 `stt_lattice`, `subtitle_timing`, `word_resegmenter` 같은 결정적 루프를 native 후보로 올린다.

## 결론
- 이번 3회 반복에서 가장 좋은 후보는 `candidate1`이다.
- 현재 기준으로는 "cleanup을 더 넓게 줄이는 것"보다 "어느 trim이 실제로 느리게 만드는지 stage별 비용을 먼저 계측하는 것"이 다음 최적화의 우선순위다.

## 2026-05-20 공격적 Apple Silicon 가속 아이디어

목표: 자막 품질을 유지하면서 CPU/GPU/NPU/ANE를 더 꽉 쓰는 구조로 바꾼다. 모델 크기 축소, LLM 생략, STT2 생략, word timestamp 축소처럼 품질을 바꿀 수 있는 최적화는 기본 후보에서 제외한다. 단, 같은 품질 산출물을 보장하는 병렬화, 캐시, 선행 실행, 네이티브화, 배치화는 공격적으로 검토한다.

참고 근거:
- Argmax OSS/WhisperKit: Apple Silicon용 on-device speech package이며 WhisperKit/SpeakerKit을 Swift Package로 제공한다. `large-v3-v20240930_626MB`는 최대 다국어 정확도용 모델로 권장된다. https://github.com/argmaxinc/argmax-oss-swift
- MLX: Apple Silicon unified memory를 전제로 CPU/GPU가 같은 배열을 복사 없이 다룰 수 있고, Python/C++/Swift/C API를 제공한다. https://github.com/ml-explore/mlx, https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html
- mlx-whisper: `mlx_whisper.transcribe(..., word_timestamps=True)`를 지원하고 pre-converted MLX Whisper 모델을 쓸 수 있다. https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md
- whisper.cpp: Core ML encoder와 Metal backend 조합을 지원하며, Core ML/Metal 사용 여부를 분리해 벤치할 수 있다. https://github.com/ggml-org/whisper.cpp/discussions/1722
- PyTorch MPS: MPS는 Metal GPU에 연산을 올릴 수 있지만, 현재 앱에서 `metal gpu stream` crash가 재현됐으므로 torch/MPS는 품질 경로가 아니라 실험/검증 격리 경로로만 둔다. https://developer.apple.com/metal/pytorch/
- Core ML / ONNX Runtime CoreML EP: Core ML은 CPU/GPU/Neural Engine을 활용할 수 있고, ONNX Runtime CoreML EP는 `MLComputeUnits=ALL`, `CPUAndNeuralEngine`, `CPUAndGPU`, `ModelCacheDirectory`, `ProfileComputePlan` 등을 제공한다. https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- Ollama: `keep_alive`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`가 병렬성과 메모리 사용량을 직접 바꾼다. `OLLAMA_NUM_PARALLEL * OLLAMA_CONTEXT_LENGTH`만큼 메모리가 증가한다. https://docs.ollama.com/faq
- llama.cpp: Apple Silicon은 ARM NEON/Accelerate/Metal 최적화 대상이고, GGUF/quantized model 및 Metal backend를 지원한다. https://github.com/ggml-org/llama.cpp

### A. 가장 큰 후보: 파이프라인을 stage DAG로 바꾸기

현재 병목 가설:
- 리소스가 남는데 느린 이유는 한 stage가 끝나야 다음 stage가 시작되는 구간이 많기 때문이다.
- 실제로는 컷 탐색, 오디오 추출, VAD, STT chunk, STT2/recheck, 후보 scoring, LoRA/Deep/LLM 후처리, 미리보기 렌더링이 독립 가능한 구간을 가진다.

아이디어:
1. `single_pipeline`을 `stage queue + dependency graph`로 쪼갠다.
2. CPU worker: ffmpeg decode/proxy/cut-boundary frame read, C++ overlap, JSON shaping, candidate scoring.
3. GPU/ANE worker: WhisperKit/CoreML STT1, optional whisper.cpp CoreML/Metal STT2, CoreML/ONNX VAD.
4. LLM worker: subtitle chunk cleanup/rerank only when STT chunk N의 후보가 충분히 모였을 때 선행 실행.
5. Editor preview worker: raw STT preview는 즉시, high-quality final은 commit barrier 뒤에만 반영.

품질 보존 조건:
- 최종 `final.srt`, `raw_segment_count`, `final_segment_count`, `variant_score`, rollback count가 기존과 같거나 더 좋아야 한다.
- 병렬 실행은 순서만 바꾸고 후보 점수/정렬/LLM prompt input은 기존과 byte-level 동등하게 만든다.

검증:
- 마카오 fast 10회, X5 canonical 10회, Tinyping 60s fast/auto/high.
- 각 run에 `stage_wait_ms`, `worker_busy_ms`, `cpu/gpu/ane_active_ms`, `queue_depth`를 기록한다.

### B. STT1/STT2를 서로 다른 가속기로 고정 배치

아이디어:
1. STT1은 현재 기본인 WhisperKit/CoreML persistent worker 유지.
2. STT2는 같은 GPU/ANE를 경쟁하지 않도록 MLX 또는 whisper.cpp Metal/CoreML 중 빠른 쪽으로 분리 벤치한다.
3. CPU가 남으면 whisper.cpp CPU/Accelerate quantized path도 STT2 후보로 병렬 벤치한다.
4. STT2는 품질 보강용이므로 STT1과 같은 모델 계열을 GPU에서 동시에 돌리는 것보다, 서로 다른 runtime과 accelerator로 분산하는 편이 더 안전하다.

실험 후보:
- `WhisperKit STT1 + MLX STT2`
- `WhisperKit STT1 + whisper.cpp Metal STT2`
- `WhisperKit STT1 + whisper.cpp CoreML encoder + Metal decoder STT2`
- `WhisperKit STT1 + whisper.cpp CPU/Accelerate STT2`

품질 보존 조건:
- STT 후보 lattice에 들어가는 text/timing evidence를 기존 STT2와 비교한다.
- X5 `.srt` truth 기준으로 WER/CER와 boundary drift가 나빠지면 폐기한다.

### C. VAD와 화자 분리를 torch/MPS에서 Core ML/ONNX/Swift로 격리

현재 관찰:
- 최근 `metal gpu stream` crash는 PyTorch MPS의 `relu`/`conv1d` 계열에서 재현됐다.
- 품질 경로에서 torch/MPS를 계속 쓰면 속도 이전에 안정성이 흔들린다.

아이디어:
1. Silero VAD는 ONNX Runtime CoreML EP 또는 Swift/CoreML 변환 후보로 옮긴다.
2. `MLComputeUnits=CPUAndNeuralEngine` 또는 `ALL`을 벤치해 GPU를 STT에 남기고 ANE를 VAD/diarization에 배정한다.
3. CoreML EP `ModelCacheDirectory`를 켜서 첫 변환/컴파일 비용을 반복 run에서 제거한다.
4. `ProfileComputePlan`으로 실제 ANE/GPU/CPU 배치가 맞는지 기록한다.
5. SpeechBrain 화자 분리는 현재처럼 CPU 고정이 안정 기본값이고, 대체 후보는 Argmax `SpeakerKit` 또는 ONNX/CoreML pyannote 계열로 별도 검증한다.

품질 보존 조건:
- VAD segment count, start/end drift, STT post-align 결과가 기존과 같아야 한다.
- speaker diarization은 단일 화자/다중 화자 fixture를 나눠 검증한다.

### D. LLM 후처리 병렬화와 local server 교체 벤치

아이디어:
1. Ollama는 `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_FLASH_ATTENTION=1`, 제한된 `OLLAMA_CONTEXT_LENGTH`로 chunk cleanup/rerank 병렬성을 실험한다.
2. 16GB base Mac에서는 `OLLAMA_NUM_PARALLEL=4`는 context cache가 커져 memory pressure를 만들 가능성이 크므로 2부터 시작한다.
3. 품질을 유지하려면 모델/프롬프트/temperature를 바꾸지 말고, 같은 모델의 병렬 처리/keep_alive/context/cache 정책만 벤치한다.
4. llama.cpp Metal server 또는 MLX 기반 OpenAI-compatible server를 shadow backend로 붙여 동일 prompt/result parity를 측정한다.
5. 동일 결과가 나오는 fixed-temperature cleanup prompt만 batch/parallel 처리하고, 품질 판단 prompt는 기존 순서를 유지한다.

실험 후보:
- Ollama current + `keep_alive` stage-aware: generation 중 유지, editor idle에서 unload.
- Ollama `NUM_PARALLEL=2` + chunk cleanup concurrent.
- llama.cpp Metal server + same GGUF model.
- MLX LLM server + same or parity-approved model only.

품질 보존 조건:
- LLM output diff가 subtitle final에 영향을 주면 폐기한다.
- prompt/result cache key를 만들어 같은 input은 재호출하지 않는다.

### E. 후보 scoring / timing / word resegmenter를 native batch kernel로 이동

아이디어:
1. `stt_candidate_scorer`, `stt_lattice`, `subtitle_timing`, `word_resegmenter`를 하나의 batch payload로 묶는다.
2. Python에서 segment마다 함수를 오가는 대신 Swift/C++에서 전체 chunk 후보를 한 번에 scoring한다.
3. Swift는 Apple-platform 재사용, C++은 numeric loop와 overlap/timing reduction에 사용한다.
4. JSON bridge 비용이 크면 MessagePack/CBOR 또는 mmap-backed binary table을 실험한다.

우선순위:
- 1순위: overlap / interval / boundary clamp / score reduce처럼 deterministic numeric loop.
- 2순위: candidate lattice dedupe / sorting / group smoothing.
- 3순위: word timestamp resegment.

품질 보존 조건:
- Python fallback과 native 결과가 row 단위로 동일해야 한다.
- floating drift는 frame 기준 epsilon으로만 허용한다.

### F. FFmpeg/audio/video IO를 더 과감하게 선행 실행

아이디어:
1. 오디오 추출이 끝나기 전에 다음 stage가 요구하는 chunk metadata/proxy/cache key를 미리 만든다.
2. Tinyping 같은 long media는 전체 decode를 기다리지 말고 rolling chunk로 STT를 시작한다.
3. FFmpeg filter graph는 한 번에 fused하고, `filter_threads`와 process count를 Apple Silicon topology에 맞춰 autotune한다.
4. preview proxy, cut-boundary frame cache, waveform/minimap cache를 동일 decode 결과에서 공유한다.

품질 보존 조건:
- 오디오 samples, chunk boundaries, FPS/frame mapping이 기존과 동일해야 한다.
- chunk overlap/hysteresis는 기존 High/Fast policy와 동일하게 유지한다.

### G. 리소스 스케줄러를 “남는 리소스” 기준으로 실시간 조정

아이디어:
1. `RuntimeResourceCoordinator`가 CPU/GPU/ANE/Memory를 보고 stage별 worker slots를 동적으로 조절한다.
2. CPU 여유가 크면 candidate scoring, cut-boundary, JSON shaping worker를 늘린다.
3. GPU 여유가 크고 memory pressure가 normal이면 STT2/word timestamp recheck를 더 빨리 선행 실행한다.
4. memory pressure가 warning 이상이면 LLM keep_alive와 STT worker warm 정책을 조절하되, 현재 chunk 품질 작업은 끊지 않는다.
5. `active_labels`에 `stt1`, `stt2`, `vad`, `llm`, `cut`, `score`, `render`를 분리 기록한다.

성공 기준:
- 리소스가 남는 구간의 `worker_idle_ms`가 줄어야 한다.
- `critical`로 떨어지는 run은 오히려 줄어야 한다.

### H. Node.js / Java / Rust 활용 판단

Node.js:
- hot path 자체는 Node로 옮길 이유가 작다.
- 단, `node-llama-cpp`는 Apple Silicon에서 Metal-enabled prebuilt/runtime이 있어 LLM shadow server 실험 후보가 될 수 있다.

Java:
- CoreML/ONNX Runtime Java binding을 쓸 수는 있지만, 이 앱의 Python/Swift 경계와 맞지 않아 1차 후보는 아니다.
- JVM warmup과 packaging 비용이 커서 subtitle hot path에는 낮은 우선순위.

Rust:
- Candle은 Whisper/LLM 모델을 포함하고 Rust-only 배포 장점이 있지만, Mac GPU hot path는 현재 앱의 Swift/MLX/CoreML/whisper.cpp 후보보다 우선순위가 낮다.
- Rust는 추후 binary table parser, interval scoring, subtitle diff/quality oracle 같은 CPU deterministic tool에는 좋다.

Metal 직접 구현:
- 바로 Whisper/LLM 전체를 직접 Metal로 짜는 것은 비효율적이다.
- 먼저 tiny kernels: interval overlap, vector score reduce, waveform/minimap reduction, frame-delta scoring부터 Metal/C++로 검증한다.

### I. 바로 해볼 5개 실험 순서

1. Stage DAG 계측 먼저 추가:
   `stage_wait_ms`, `worker_busy_ms`, `worker_idle_ms`, `cpu/gpu/ane slot`, `queue_depth`를 `repeat_summary.json`에 기록.
2. STT runtime matrix:
   `WhisperKit + MLX`, `WhisperKit + whisper.cpp Metal`, `WhisperKit + whisper.cpp CoreML+Metal`을 X5 3분 truth로 벤치.
3. VAD CoreML/ONNX prototype:
   Silero ONNX를 CoreML EP `CPUAndNeuralEngine`/`ALL`로 돌려 torch/MPS를 완전히 제거.
4. LLM parallel-safe benchmark:
   Ollama `NUM_PARALLEL=2`, Flash Attention, keep_alive stage policy를 동일 prompt/output parity로 측정.
5. Native scoring batch:
   `stt_lattice + candidate_scorer + subtitle_timing`을 Swift/C++ batch bridge로 묶고, Python fallback과 row parity 테스트.

### J. 폐기 기준

- 최종 자막 text/timing이 baseline보다 나빠지면 즉시 폐기.
- X5 truth 기준 WER/CER 또는 boundary drift가 나빠지면 폐기.
- 평균은 빨라도 p95/p99가 나빠져 사용자가 느리게 느끼면 폐기.
- `pressure_stage=critical` 빈도가 늘면 폐기.
- native bridge payload가 작아서 Python보다 느리면 폐기.
- MPS crash 가능성이 있는 torch path는 production default로 채택하지 않는다.

### K. 가장 유망한 결론

가장 큰 속도 개선은 “모델을 줄이는 것”이 아니라 “동일 모델/동일 품질을 유지한 채 stage를 겹쳐 실행하는 것”에서 나올 가능성이 높다. 다음 구현 후보는 다음 조합이 가장 현실적이다.

1. `single_pipeline` stage DAG + worker slot 계측
2. STT1 WhisperKit 유지, STT2를 MLX/whisper.cpp로 분산
3. VAD/diarization torch/MPS 제거, CoreML/ANE 또는 CPU 안정 경로로 격리
4. LLM cleanup chunk 병렬화는 동일 prompt/output parity가 증명되는 구간부터 적용
5. 후보 scoring/timing deterministic loop를 Swift/C++ batch native로 이동
